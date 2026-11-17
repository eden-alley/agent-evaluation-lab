"""Offline journal/replay contracts; no SDK, model or original evaluation calls."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from formal20_coordinator import Coordinator, CoordinatorError


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="formal20-recovery-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = {"model": "scripted", "messages": [{"role": "user", "content": "hello"}]}
        self.payload_hash = hashlib.sha256(json.dumps(
            self.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        self.body = {"id": "response-1", "choices": [{"message": {"role": "assistant", "content": "ok"}}]}

    def coordinator(self, **kwargs):
        return Coordinator(self.root, prompt_price_per_million="1000000",
                           output_price_per_million="1000000", **kwargs)

    def grant(self, coordinator, attempt=1, case="U05"):
        coordinator.acquire(case, attempt, "2", {"payload": self.payload,
                                                 "payload_sha256": self.payload_hash})
        return coordinator.dispatch()[0]

    def settle(self, coordinator, request_id):
        return coordinator.settle(request_id, {"prompt_tokens": 1, "completion_tokens": 0},
                                  {"body": self.body})

    def test_response_durable_before_consume_is_replayed_once(self):
        c = self.coordinator(currency="USD")
        permit = self.grant(c)
        self.settle(c, permit["request_id"])
        restored = self.coordinator(resume=True, currency="USD")
        self.assertEqual(restored.replay_response("U05", 1, self.payload_hash), self.body)
        self.assertEqual(restored.snapshot()["requests"], 1)
        self.assertEqual(restored.snapshot()["estimated_cost_at_peak"], "1")
        restored.register_consumed(permit["request_id"])
        restored.register_consumed(permit["request_id"])
        again = self.coordinator(resume=True, currency="USD")
        self.assertIsNone(again.replay_response("U05", 1, self.payload_hash))
        self.assertEqual(again.snapshot()["response_count"], 1)
        self.assertEqual(again.snapshot()["reserved_total"], "0")

    def test_resume_request_ids_do_not_restart(self):
        c = self.coordinator()
        self.assertEqual(c.next_attempt("U05"), 1)
        first = self.grant(c)
        self.settle(c, first["request_id"])
        restored = self.coordinator(resume=True)
        self.assertEqual(restored.next_attempt("U05"), 2)
        second = self.grant(restored, attempt=2)
        self.assertEqual(second["request_id"], "request-000002")
        self.assertEqual(second["number"], 2)
        self.assertEqual(restored.snapshot()["per_case"], {"U05": 2})
        self.assertEqual(restored.snapshot()["requests"], 2)

    def test_allocated_attempt_survives_worker_restart_before_acquire(self):
        c = self.coordinator()
        self.assertEqual(c.next_attempt("U05"), 1)
        self.assertEqual(self.coordinator(resume=True).next_attempt("U05"), 2)

    def test_unconfirmed_grant_becomes_unknown_without_reissue(self):
        c = self.coordinator()
        permit = self.grant(c)
        restored = self.coordinator(resume=True)
        state = restored.snapshot()
        self.assertTrue(state["needs_recovery"])
        self.assertEqual(state["recovery_status"], "needs_recovery")
        self.assertEqual(state["reserved_total"], "2")
        self.assertEqual(state["unknown_count"], 1)
        self.assertEqual(state["inflight_count"], 0)
        self.assertEqual(state["requests"], 1)
        self.assertEqual(restored.dispatch(), [])
        duplicate = restored.acquire("U05", 1, "2", {"payload": self.payload,
                                                       "payload_sha256": self.payload_hash})
        self.assertEqual(duplicate["status"], "unknown_usage")
        with self.assertRaises(CoordinatorError):
            restored.replay_response("U05", 1, self.payload_hash)
        self.assertIn(permit["request_id"], state["unknown_requests"])

    def test_binding_change_refuses_resume_without_modifying_evidence(self):
        self.coordinator(binding={"plan_sha256": "a" * 64}, currency="USD")
        before = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        for options in ({"binding": {"plan_sha256": "b" * 64}, "currency": "USD"},
                        {"binding": {"plan_sha256": "a" * 64}, "currency": "EUR"},
                        {"binding": {"plan_sha256": "a" * 64}, "currency": "USD", "max_requests": 3}):
            with self.subTest(options=options), self.assertRaisesRegex(CoordinatorError, "binding"):
                self.coordinator(resume=True, **options)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()})

    def test_partial_ledger_stops_recovery(self):
        self.coordinator()
        path = self.root / "request-ledger.jsonl"
        with path.open("ab") as stream:
            stream.write(b'{"sequence":2')
        before = path.read_bytes()
        with self.assertRaisesRegex(CoordinatorError, "partial"):
            self.coordinator(resume=True)
        self.assertEqual(path.read_bytes(), before)

    def test_resume_requires_journal_and_fresh_open_cannot_reset(self):
        c = self.coordinator()
        self.grant(c)
        with self.assertRaises(FileExistsError):
            self.coordinator()
        (self.root / "request-ledger.jsonl").unlink()
        before = (self.root / "budget.json").read_bytes()
        with self.assertRaisesRegex(CoordinatorError, "journal"):
            self.coordinator(resume=True)
        self.assertEqual((self.root / "budget.json").read_bytes(), before)

    def test_durable_response_recovers_if_atomic_budget_write_failed(self):
        c = self.coordinator()
        permit = self.grant(c)
        with patch.object(c, "_persist", side_effect=OSError("injected snapshot failure")):
            with self.assertRaises(CoordinatorError):
                self.settle(c, permit["request_id"])
        restored = self.coordinator(resume=True)
        self.assertEqual(restored.replay_response("U05", 1, self.payload_hash), self.body)
        self.assertEqual(restored.snapshot()["response_count"], 1)
        self.assertEqual(restored.snapshot()["estimated_cost_at_peak"], "1")
        self.assertFalse(restored.snapshot()["needs_recovery"])

    def test_replay_checks_payload_and_does_not_release_unknown_reserve(self):
        c = self.coordinator()
        permit = self.grant(c)
        self.settle(c, permit["request_id"])
        with self.assertRaisesRegex(CoordinatorError, "fingerprint"):
            c.replay_response("U05", 1, "f" * 64)
        self.assertIsNone(c.replay_response("missing", 1, self.payload_hash))
        second = self.grant(c, 2)
        c.settle(second["request_id"], None, {"body": self.body})
        restored = self.coordinator(resume=True)
        with self.assertRaises(CoordinatorError):
            restored.replay_response("U05", 2, self.payload_hash)
        self.assertEqual(restored.snapshot()["reserved_total"], "2")
        self.assertEqual(restored.snapshot()["known_count"], 1)
        self.assertEqual(restored.snapshot()["unknown_count"], 1)

    def test_exception_metadata_is_allowlisted_and_no_sensitive_body_is_stored(self):
        c = self.coordinator()
        permit = self.grant(c)
        c.mark_unknown(permit["request_id"], "api_error", {
            "exception_type": "RateLimitError", "status_code": 429,
            "provider_request_id": "req-safe-123", "retry_after": "2",
            "body": "secret-error-body", "Authorization": "secret-authorization",
            "api_key": "secret-key", "message": "secret-message"})
        restored = self.coordinator(resume=True)
        unknown = restored.snapshot()["unknown_requests"][permit["request_id"]]
        self.assertEqual(unknown["exception_metadata"], {
            "exception_type": "RateLimitError", "status_code": 429,
            "provider_request_id": "req-safe-123", "retry_after": "2"})
        evidence = "\n".join(p.read_text(encoding="utf-8") for p in self.root.iterdir() if p.is_file())
        self.assertNotIn("secret-", evidence)
        self.assertEqual(restored.snapshot()["reserved_total"], "2")
        self.assertEqual(restored.snapshot()["halt"], "api_error")

    def test_pending_attempt_restores_and_journal_is_authoritative_over_snapshot(self):
        c = self.coordinator()
        c.acquire("U05", 7, "2", {"payload": self.payload})
        (self.root / "budget.json").write_text('{"requests":999}', encoding="utf-8")
        restored = self.coordinator(resume=True)
        self.assertEqual(restored.snapshot()["pending_count"], 1)
        self.assertEqual(restored.snapshot()["requests"], 0)
        self.assertEqual(restored.next_attempt("U05"), 8)
        self.assertEqual(restored.dispatch()[0]["request_id"], "request-000001")

    def test_consuming_unknown_request_is_rejected(self):
        c = self.coordinator()
        permit = self.grant(c)
        with self.assertRaises(CoordinatorError):
            c.register_consumed(permit["request_id"])
        self.assertEqual(c.snapshot()["reserved_total"], "2")

    def test_valid_json_with_invalid_journal_shape_is_rejected(self):
        self.coordinator()
        path = self.root / "request-ledger.jsonl"
        with path.open("ab") as stream:
            stream.write(b"[]\n")
        before = path.read_bytes()
        with self.assertRaises(CoordinatorError):
            self.coordinator(resume=True)
        self.assertEqual(path.read_bytes(), before)

    def test_failed_grant_snapshot_retains_reserve_without_granting_permission(self):
        c = self.coordinator()
        c.acquire("U05", 1, "2", {"payload": self.payload})
        with patch.object(c, "_persist", side_effect=OSError("injected snapshot failure")):
            with self.assertRaises(CoordinatorError):
                c.dispatch()
        restored = self.coordinator(resume=True)
        self.assertEqual(restored.snapshot()["requests"], 1)
        self.assertEqual(restored.snapshot()["reserved_total"], "2")
        self.assertTrue(restored.snapshot()["needs_recovery"])
        self.assertEqual(restored.dispatch(), [])

    def test_stopped_batch_drains_permitted_response_without_new_requests(self):
        c = self.coordinator(max_inflight_requests=2)
        c.acquire("U05", 1, "2", {"payload": self.payload})
        c.acquire("U06", 1, "2", {"payload": self.payload})
        first, second = c.dispatch()
        c.mark_unknown(first["request_id"], "connection_error")
        self.settle(c, second["request_id"])
        restored = self.coordinator(resume=True)
        self.assertEqual(restored.snapshot()["requests"], 2)
        self.assertEqual(restored.snapshot()["known_count"], 1)
        self.assertEqual(restored.snapshot()["unknown_count"], 1)
        self.assertEqual(restored.snapshot()["reserved_total"], "2")
        self.assertEqual(restored.replay_response("U06", 1, self.payload_hash), self.body)
        self.assertEqual(restored.dispatch(), [])

    def test_explicit_retry_keeps_unknown_reservation_and_cumulative_usage(self):
        c = self.coordinator()
        first = self.grant(c)
        c.mark_unknown(first["request_id"], "api_exception",
                       {"exception_type": "APIConnectionError"}, stop=False)
        self.assertIsNone(c.snapshot()["halt"])
        self.assertEqual(c.snapshot()["reserved_total"], "2")
        self.assertEqual(c.next_attempt("U05"), 2)
        second = self.grant(c, attempt=2)
        self.assertEqual(c.snapshot()["reserved_total"], "4")
        self.settle(c, second["request_id"])
        self.assertEqual(c.snapshot()["requests"], 2)
        self.assertEqual(c.snapshot()["estimated_cost_at_peak"], "1")
        self.assertEqual(c.snapshot()["reserved_total"], "2")
        events = [json.loads(line) for line in (self.root / "request-ledger.jsonl").read_text().splitlines()]
        self.assertIn("retry_authorized", [event["kind"] for event in events])
        restored = self.coordinator(resume=True)
        self.assertTrue(restored.snapshot()["needs_recovery"])
        self.assertEqual(restored.snapshot()["halt"], "needs_recovery")
        self.assertEqual(restored.dispatch(), [])

    def test_retry_option_does_not_clear_an_existing_stop(self):
        c = self.coordinator()
        first = self.grant(c)
        c.stop("unrelated_failure")
        c.mark_unknown(first["request_id"], "api_exception", stop=False)
        self.assertEqual(c.snapshot()["halt"], "unrelated_failure")
        self.assertEqual(c.snapshot()["reserved_total"], "2")

    def test_unknown_attempt_cannot_return_a_granted_permit(self):
        c = self.coordinator()
        first = self.grant(c)
        c.mark_unknown(first["request_id"], "api_exception", stop=False)
        duplicate = c.acquire("U05", 1, "2", {"payload": self.payload,
                                               "payload_sha256": self.payload_hash})
        self.assertEqual(duplicate["status"], "unknown_usage")

    def test_repeated_unknown_does_not_persist_sensitive_reason(self):
        c = self.coordinator()
        first = self.grant(c)
        c.mark_unknown(first["request_id"], "api_exception", stop=False)
        c.mark_unknown(first["request_id"], "secret exception body with Authorization token")
        evidence = "\n".join(p.read_text(encoding="utf-8") for p in self.root.iterdir() if p.is_file())
        self.assertNotIn("secret exception", evidence)
        self.assertEqual(c.snapshot()["halt"], "api_error")

    def test_checkpoint_pause_resumes_only_after_validated_reopen(self):
        c = self.coordinator(binding={"plan_sha256": "a" * 64})
        c.stop("checkpoint_paused")
        with self.assertRaises(CoordinatorError):
            c.resume_checkpoint_pause()
        restored = self.coordinator(resume=True, binding={"plan_sha256": "a" * 64})
        restored.resume_checkpoint_pause()
        self.assertIsNone(restored.snapshot()["halt"])
        self.assertIsNone(restored.snapshot()["halt_at"])
        events = [json.loads(line) for line in (self.root / "request-ledger.jsonl").read_text().splitlines()]
        self.assertEqual(events[-1]["kind"], "checkpoint_resumed")
        again = self.coordinator(resume=True, binding={"plan_sha256": "a" * 64})
        self.assertIsNone(again.snapshot()["halt"])
        self.assertEqual(again.next_attempt("U05"), 1)
        self.assertEqual(self.grant(again)["request_id"], "request-000001")

    def test_checkpoint_pause_method_refuses_other_stop_reasons(self):
        for reason in ("api_exception", "needs_recovery", "budget_limit", None):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temp:
                c = Coordinator(temp)
                if reason is not None:
                    c.stop(reason)
                restored = Coordinator(temp, resume=True)
                before = {p.name: p.read_bytes() for p in Path(temp).iterdir() if p.is_file()}
                with self.assertRaises(CoordinatorError):
                    restored.resume_checkpoint_pause()
                self.assertEqual(restored.snapshot()["halt"], reason)
                self.assertEqual(before, {p.name: p.read_bytes() for p in Path(temp).iterdir() if p.is_file()})

    def test_checkpoint_pause_method_refuses_unresolved_permits(self):
        for unknown in (False, True):
            with self.subTest(unknown=unknown), tempfile.TemporaryDirectory() as temp:
                Coordinator(temp)
                restored = Coordinator(temp, resume=True)
                permit = self.grant(restored)
                restored.stop("checkpoint_paused")
                if unknown:
                    restored.mark_unknown(permit["request_id"], "api_exception")
                with self.assertRaises(CoordinatorError):
                    restored.resume_checkpoint_pause()
                self.assertEqual(restored.snapshot()["halt"], "checkpoint_paused")
                self.assertEqual(restored.snapshot()["reserved_total"], "2")


if __name__ == "__main__":
    unittest.main()
