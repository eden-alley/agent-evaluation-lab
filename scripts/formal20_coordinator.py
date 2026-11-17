"""Single-process budget and request-permission owner. No SDK or scorer imports."""
from collections import deque
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from uuid import uuid4


class CoordinatorError(RuntimeError):
    pass


def _decimal(value, name):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be a finite nonnegative number") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return result


def _json_copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


class Coordinator:
    """Owned by one event loop; callers enqueue and poll dispatch without blocking."""

    def __init__(self, run_dir, *, budget_limit="10", max_requests=1200,
                 max_requests_per_case=60, max_inflight_requests=2,
                 min_request_interval=0, clock=time.monotonic,
                 prompt_price_per_million="2", output_price_per_million="8",
                 resume=False, currency="SIM", binding=None):
        for name, value in (("max_requests", max_requests),
                            ("max_requests_per_case", max_requests_per_case),
                            ("max_inflight_requests", max_inflight_requests)):
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if (isinstance(min_request_interval, bool) or
                not isinstance(min_request_interval, (float, int)) or
                not math.isfinite(min_request_interval) or min_request_interval < 0):
            raise ValueError("min_request_interval must be finite and nonnegative")
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / "budget.json"
        self.journal_path = self.run_dir / "request-ledger.jsonl"
        if not isinstance(currency, str) or not currency.strip():
            raise ValueError("currency must identify the accounting currency")
        if not resume and any(path.exists() for path in
                              (self.path, self.journal_path, self.run_dir / "requests.jsonl")):
            raise FileExistsError(f"Existing budget cannot be overwritten: {self.path}")
        self.budget_limit = _decimal(budget_limit, "budget_limit")
        self.prompt_price = _decimal(prompt_price_per_million, "prompt_price_per_million")
        self.output_price = _decimal(output_price_per_million, "output_price_per_million")
        self.max_requests = max_requests
        self.max_requests_per_case = max_requests_per_case
        self.max_inflight_requests = max_inflight_requests
        self.min_request_interval = float(min_request_interval)
        self.clock = clock
        self._last_grant = None
        self._pending = deque()
        self._attempts = {}
        self._records = {}
        self._next_attempt = {}
        self._journal_sequence = 0
        self._resume_validated = False
        self._binding = {
            "budget_limit": str(self.budget_limit.normalize()),
            "prompt_price_per_million": str(self.prompt_price.normalize()),
            "output_price_per_million": str(self.output_price.normalize()),
            "max_requests": max_requests, "max_requests_per_case": max_requests_per_case,
            "max_inflight_requests": max_inflight_requests,
            "min_request_interval": self.min_request_interval, "currency": currency,
            "execution": _json_copy(binding),
        }
        self._state = {
            "schema_version": 1, "currency": currency, "requests": 0, "per_case": {},
            "prompt_tokens": 0, "completion_tokens": 0, "estimated_cost_at_peak": "0",
            "halt": None, "halt_at": None, "response_count": 0,
            "max_observed_inflight": 0,
        }
        if resume:
            self._restore()
            self._resume_validated = True
        else:
            self._save("created")

    def snapshot(self):
        state = deepcopy(self._state)
        state["inflight_requests"] = {
            key: self._public_record(record) for key, record in self._records.items()
            if record["status"] == "granted"
        }
        state["unknown_requests"] = {
            key: self._public_record(record) for key, record in self._records.items()
            if record["status"] == "unknown_usage"
        }
        state["reserved_total"] = str(sum(
            (record["reserve"] for record in self._records.values()
             if record["status"] in ("granted", "unknown_usage")), Decimal(0)))
        state["pending_count"] = len(self._pending)
        state["inflight_count"] = len(state["inflight_requests"])
        state["unknown_count"] = len(state["unknown_requests"])
        state["known_count"] = sum(record["status"] == "settled" for record in self._records.values())
        state["needs_recovery"] = bool(state["unknown_requests"])
        state["recovery_status"] = "needs_recovery" if state["needs_recovery"] else "ready"
        state["journal_sequence"] = self._journal_sequence
        return state

    @staticmethod
    def _public_record(record):
        return {"case": record["case_id"], "case_id": record["case_id"],
                "attempt_id": record["attempt_id"], "number": record["number"],
                "reserve": str(record["reserve"]), "status": record["status"],
                "granted_at": record["granted_at"], "reason": record.get("reason"),
                "payload_sha256": record.get("payload_sha256"),
                "consumed": record.get("consumed", False),
                "exception_metadata": deepcopy(record.get("exception_metadata", {}))}

    @staticmethod
    def _encode_item(item):
        value = deepcopy(item)
        value["reserve"] = str(value["reserve"])
        return value

    @staticmethod
    def _decode_item(item):
        value = deepcopy(item)
        value["reserve"] = _decimal(value["reserve"], "reserve")
        return value

    def _journal(self, kind):
        """The fsynced event is authoritative; budget.json is a replaceable view."""
        sequence = self._journal_sequence + 1
        value = {
            "schema_version": 1, "sequence": sequence, "kind": kind,
            "binding": self._binding, "state": self._state,
            "pending": list(self._pending), "next_attempt": self._next_attempt,
            "attempts": [self._encode_item(item) for item in self._attempts.values()],
            "records": [self._encode_item(item) for item in self._records.values()],
        }
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n"
        with self.journal_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        self._journal_sequence = sequence

    def _restore(self):
        if not self.journal_path.is_file():
            raise CoordinatorError("Cannot resume without an authoritative request journal")
        raw = self.journal_path.read_bytes()
        if not raw or not raw.endswith(b"\n"):
            raise CoordinatorError("Cannot resume a partial or empty request journal")
        last = None
        try:
            for sequence, line in enumerate(raw.decode("utf-8").splitlines(), 1):
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("invalid journal event")
                if event.get("schema_version") != 1 or event.get("sequence") != sequence:
                    raise ValueError("invalid journal sequence")
                if event.get("binding") != self._binding:
                    raise CoordinatorError("Cannot resume: accounting or execution binding changed")
                last = event
            self._state = last["state"]
            self._attempts = {(item["case_id"], item["attempt_id"]): self._decode_item(item)
                              for item in last["attempts"]}
            self._records = {item["request_id"]: self._decode_item(item) for item in last["records"]}
            self._pending = deque(tuple(key) for key in last["pending"])
            self._next_attempt = last["next_attempt"]
            self._journal_sequence = last["sequence"]
            if any(key not in self._attempts for key in self._pending):
                raise ValueError("journal pending request is missing")
            if self._state["requests"] != len(self._records):
                raise ValueError("journal request count is inconsistent")
        except (KeyError, TypeError, ValueError, UnicodeError) as error:
            raise CoordinatorError("Cannot resume malformed request journal") from error
        # A monotonic timestamp from another process/boot is not a safe rate-limit clock.
        self._last_grant = self.clock() if self._state["requests"] else None
        for request_id, record in self._records.items():
            if record["status"] == "granted" and record.get("response_recorded"):
                self.settle(request_id, record["response_usage"], record["response_metadata"])
        unconfirmed = [r for r in self._records.values() if r["status"] == "granted"]
        for record in unconfirmed:
            record["status"] = "unknown_usage"
            record["reason"] = "unconfirmed_permit"
            item = self._attempts[(record["case_id"], record["attempt_id"])]
            item["permit"] = {"case_id": record["case_id"], "attempt_id": record["attempt_id"],
                              "request_id": record["request_id"], "status": "unknown_usage",
                              "reason": "unconfirmed_permit"}
        if any(record["status"] == "unknown_usage" for record in self._records.values()):
            self.stop("needs_recovery")
        self._save("restored")

    def _persist(self):
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(self.snapshot(), stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def _save(self, kind="state"):
        try:
            self._journal(kind)
            self._persist()
        except OSError as error:
            self._state["halt"] = self._state["halt"] or "ledger_write_failure"
            self._state["halt_at"] = self._state["halt_at"] if self._state["halt_at"] is not None else self.clock()
            raise CoordinatorError("Unable to persist budget; no new permission may be issued") from error

    def _log(self, record, kind, **details):
        value = {"case": record["case_id"], "number": record["number"],
                 "request_id": record["request_id"], "kind": kind, "time": time.time(),
                 "monotonic_time": self.clock(), **details}
        try:
            with (self.run_dir / "requests.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            self._state["halt"] = self._state["halt"] or "ledger_write_failure"
            self._state["halt_at"] = self._state["halt_at"] if self._state["halt_at"] is not None else self.clock()
            if record["status"] == "granted":
                record["status"] = "unknown_usage"
                record["reason"] = "ledger_write_failure"
            self._save("log_failure")
            raise CoordinatorError("Unable to persist request log") from error

    def stop(self, reason):
        changed = bool(self._pending) or not self._state["halt"]
        if not self._state["halt"]:
            self._state["halt"] = str(reason)
            self._state["halt_at"] = self.clock()
        while self._pending:
            item = self._attempts[self._pending.popleft()]
            item["permit"] = {"case_id": item["case_id"], "attempt_id": item["attempt_id"],
                              "status": "halted", "reason": self._state["halt"]}
        if changed:
            self._save("stopped")
        return {"status": "halted", "reason": self._state["halt"]}

    def next_attempt(self, case_id):
        """Allocate a durable per-case physical attempt, including unused allocations."""
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("case_id must identify one case")
        if self._state["halt"]:
            raise CoordinatorError("Cannot allocate an attempt after the batch stopped")
        number = self._next_attempt.get(case_id, 0) + 1
        self._next_attempt[case_id] = number
        self._save("attempt_allocated")
        return number

    def resume_checkpoint_pause(self):
        """Reopen only a controlled native-checkpoint pause after binding validation."""
        if (not self._resume_validated or self._state["halt"] != "checkpoint_paused" or
                any(record["status"] in ("granted", "unknown_usage")
                    for record in self._records.values())):
            raise CoordinatorError("Cannot resume: only a validated checkpoint pause without unresolved requests is recoverable")
        self._state["halt"] = None
        self._state["halt_at"] = None
        self._save("checkpoint_resumed")
        return {"status": "ready", "previous_halt": "checkpoint_paused"}

    def replay_response(self, case_id, attempt_id, payload_sha256):
        item = self._attempts.get((case_id, attempt_id))
        if item is None:
            return None
        if item.get("payload_sha256") != payload_sha256:
            raise CoordinatorError("Cannot replay a response with a different payload fingerprint")
        permit = item.get("permit") or {}
        record = self._records.get(permit.get("request_id"))
        if record is None or record["status"] != "settled":
            raise CoordinatorError("Only a settled response can be replayed")
        if record.get("consumed"):
            return None
        metadata = record["response_metadata"]
        return deepcopy(metadata.get("body", metadata))

    def register_consumed(self, request_id):
        record = self._records.get(request_id)
        if record is None or record["status"] != "settled":
            raise CoordinatorError("Only a settled response can be consumed")
        if not record.get("consumed"):
            record["consumed"] = True
            self._save("response_consumed")
        return {"status": "consumed", "request_id": request_id}

    def acquire(self, case_id, attempt_id, reserve_cost, prompt_metadata):
        if not isinstance(case_id, str) or not case_id or isinstance(attempt_id, (dict, list)):
            raise ValueError("case_id and attempt_id must identify one request")
        reserve = _decimal(reserve_cost, "reserve_cost")
        metadata = _json_copy(prompt_metadata)
        key = (case_id, attempt_id)
        fingerprint = json.dumps([str(reserve), metadata], sort_keys=True, ensure_ascii=False)
        previous = self._attempts.get(key)
        if previous:
            if previous["fingerprint"] != fingerprint:
                self.stop("conflicting_request")
                raise CoordinatorError("Same attempt has different request data")
            permit = previous.get("permit") or {}
            record = self._records.get(permit.get("request_id"))
            if record is not None and record["status"] == "unknown_usage":
                return {**deepcopy(permit), "status": "unknown_usage", "reason": record.get("reason")}
            return deepcopy(previous.get("permit"))
        if self._state["halt"]:
            return {"case_id": case_id, "attempt_id": attempt_id,
                    "status": "halted", "reason": self._state["halt"]}
        item = {"case_id": case_id, "attempt_id": attempt_id, "reserve": reserve,
                "metadata": metadata, "fingerprint": fingerprint,
                "payload_sha256": metadata.get("payload_sha256") or hashlib.sha256(json.dumps(
                    metadata.get("payload", metadata), ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()}
        self._attempts[key] = item
        self._pending.append(key)
        if type(attempt_id) is int:
            self._next_attempt[case_id] = max(self._next_attempt.get(case_id, 0), attempt_id)
        self._save("request_queued")
        return None

    def dispatch(self):
        grants = []
        while self._pending and not self._state["halt"]:
            key = self._pending[0]
            item = self._attempts[key]
            cid = item["case_id"]
            if self._state["per_case"].get(cid, 0) >= self.max_requests_per_case:
                self._pending.popleft()
                permit = {"case_id": cid, "attempt_id": item["attempt_id"], "status": "case_limit"}
                item["permit"] = permit
                self._save("case_limit")
                grants.append(deepcopy(permit))
                continue
            if self._state["requests"] >= self.max_requests:
                self.stop("batch_request_limit")
                break
            inflight = [r for r in self._records.values() if r["status"] == "granted"]
            if len(inflight) >= self.max_inflight_requests:
                break
            if any(r["case_id"] == cid for r in inflight):
                break
            now = self.clock()
            if self._last_grant is not None and now - self._last_grant < self.min_request_interval:
                break
            reserved = Decimal(self.snapshot()["reserved_total"])
            if Decimal(self._state["estimated_cost_at_peak"]) + reserved + item["reserve"] > self.budget_limit:
                if not inflight:
                    self.stop("budget_limit")
                break
            number = self._state["requests"] + 1
            request_id = f"request-{number:06d}"
            record = {**item, "request_id": request_id, "number": number,
                      "status": "granted", "granted_at": now}
            self._records[request_id] = record
            self._state["requests"] = number
            self._state["per_case"][cid] = self._state["per_case"].get(cid, 0) + 1
            self._state["max_observed_inflight"] = max(self._state["max_observed_inflight"], len(inflight) + 1)
            self._pending.popleft()
            permit = {"case_id": cid, "attempt_id": item["attempt_id"], "status": "granted",
                      "request_id": request_id, "number": number, "granted_at": now}
            item["permit"] = permit
            self._save("request_granted")  # Reservation and stable identity precede permission.
            self._log(record, "request", payload=item["metadata"].get("payload", item["metadata"]))
            self._last_grant = self.clock()
            grants.append(deepcopy(permit))
        return grants

    def settle(self, request_id, usage, response_metadata):
        record = self._records.get(request_id)
        if record is None:
            self.stop("unknown_request")
            raise CoordinatorError("Unknown request_id")
        metadata = _json_copy(response_metadata)
        signature = json.dumps([usage, metadata], sort_keys=True, ensure_ascii=False, allow_nan=False)
        if "settlement_signature" in record:
            if record["settlement_signature"] != signature:
                self.stop("conflicting_settlement")
                raise CoordinatorError("Same request has conflicting settlements")
            return deepcopy(record["settlement_result"])
        if record["status"] != "granted":
            self.stop("settlement_after_unknown")
            raise CoordinatorError("Cannot settle an unknown request automatically")
        if not record.get("response_recorded"):
            record["response_usage"] = _json_copy(usage)
            record["response_metadata"] = metadata
            record["response_recorded"] = True
            self._state["response_count"] += 1
            self._save("response_recorded")  # The raw SDK body survives a crash before settlement.
            self._log(record, "response", body=metadata.get("body", metadata))
        elif (record["response_usage"] != usage or record["response_metadata"] != metadata):
            self.stop("conflicting_settlement")
            raise CoordinatorError("Durable response conflicts with settlement")
        valid = isinstance(usage, dict) and all(
            type(usage.get(name)) is int and usage[name] >= 0
            for name in ("prompt_tokens", "completion_tokens")
        )
        if not valid:
            record["status"] = "unknown_usage"
            record["reason"] = "unknown_usage"
            result = {"status": "unknown_usage", "request_id": request_id}
            record["settlement_signature"] = signature
            record["settlement_result"] = result
            self.stop("unknown_usage")
            self._save("unknown_usage")
            return result
        prompt, completion = usage["prompt_tokens"], usage["completion_tokens"]
        amount = (Decimal(prompt) * self.prompt_price + Decimal(completion) * self.output_price) / 1_000_000
        self._state["prompt_tokens"] += prompt
        self._state["completion_tokens"] += completion
        self._state["estimated_cost_at_peak"] = str(Decimal(self._state["estimated_cost_at_peak"]) + amount)
        record["status"] = "settled"
        result = {"status": "settled", "request_id": request_id, "cost": str(amount)}
        record["settlement_signature"] = signature
        record["settlement_result"] = result
        if Decimal(self._state["estimated_cost_at_peak"]) + Decimal(self.snapshot()["reserved_total"]) > self.budget_limit:
            self.stop("actual_budget_limit")
        self._save("request_settled")
        return deepcopy(result)

    def mark_unknown(self, request_id, reason, metadata=None, *, stop=True):
        """stop=False is reserved for a frozen retry policy enforced by the parent."""
        if type(stop) is not bool:
            raise ValueError("stop must be a boolean")
        reason = str(reason)
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", reason):
            reason = "api_error"
        record = self._records.get(request_id)
        if record is None:
            self.stop("unknown_request")
            raise CoordinatorError("Unknown request_id")
        if record["status"] == "settled":
            self.stop("conflicting_settlement")
            raise CoordinatorError("A settled request cannot become unknown")
        if record["status"] != "unknown_usage":
            record["status"] = "unknown_usage"
            record["reason"] = reason
            record["exception_metadata"] = self._exception_metadata(metadata)
            self._save("request_unknown")
            self._log(record, "exception", error_type=reason, **record["exception_metadata"])
        if stop:
            self.stop(reason)
        self._save("request_unknown" if stop else "retry_authorized")
        return {"status": "unknown_usage", "request_id": request_id, "reason": str(reason)}

    @staticmethod
    def _exception_metadata(metadata):
        """Preserve only structured provider diagnostics, never exception messages/bodies."""
        if not isinstance(metadata, dict):
            return {}
        clean = {}
        for name in ("exception_type", "provider_request_id"):
            value = metadata.get(name)
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", value):
                clean[name] = value
        status = metadata.get("status_code")
        if type(status) is int and 100 <= status <= 599:
            clean["status_code"] = status
        retry = metadata.get("retry_after")
        if ((type(retry) in (int, float) and math.isfinite(retry) and retry >= 0) or
                (isinstance(retry, str) and re.fullmatch(r"[A-Za-z0-9 ,:.-]{1,80}", retry))):
            clean["retry_after"] = retry
        return clean
