"""Pure accounting tests: no model, task fixture or scorer imports."""
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from formal20_coordinator import Coordinator, CoordinatorError


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="formal20-accounting-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def coordinator(self, **kwargs):
        return Coordinator(self.root, prompt_price_per_million="1000000",
                           output_price_per_million="1000000", **kwargs)

    def request(self, c, case="SIM-A", attempt=1, reserve="1"):
        c.acquire(case, attempt, reserve, {"payload": {"model": "offline"}})

    def test_two_reservations_cannot_overspend(self):
        c = self.coordinator(budget_limit="10")
        self.request(c, reserve="6")
        self.request(c, "SIM-B", reserve="6")
        first = c.dispatch()
        self.assertEqual(len(first), 1)
        self.assertEqual(c.snapshot()["reserved_total"], "6")
        self.assertIsNone(c.snapshot()["halt"])
        c.settle(first[0]["request_id"], {"prompt_tokens": 2, "completion_tokens": 0}, {})
        second = c.dispatch()
        self.assertEqual([p["case_id"] for p in second], ["SIM-B"])
        self.assertEqual(Decimal(c.snapshot()["estimated_cost_at_peak"]) +
                         Decimal(c.snapshot()["reserved_total"]), Decimal("8"))

    def test_request_and_settlement_are_idempotent(self):
        c = self.coordinator()
        self.request(c)
        self.request(c)
        permit = c.dispatch()[0]
        self.assertEqual(c.dispatch(), [])
        cached = c.acquire("SIM-A", 1, "1", {"payload": {"model": "offline"}})
        self.assertEqual(cached, permit)
        usage = {"prompt_tokens": 1, "completion_tokens": 0}
        result = c.settle(permit["request_id"], usage, {"body": {"ok": True}})
        self.assertEqual(result, c.settle(permit["request_id"], usage, {"body": {"ok": True}}))
        self.assertEqual(c.snapshot()["requests"], 1)
        self.assertEqual(c.snapshot()["response_count"], 1)
        self.assertEqual(c.snapshot()["estimated_cost_at_peak"], "1")
        lines = [json.loads(l) for l in (self.root / "requests.jsonl").read_text().splitlines()]
        self.assertEqual([r["kind"] for r in lines], ["request", "response"])

    def test_conflicting_settlement_stops_batch(self):
        c = self.coordinator()
        self.request(c)
        permit = c.dispatch()[0]
        c.settle(permit["request_id"], {"prompt_tokens": 1, "completion_tokens": 0}, {})
        with self.assertRaises(CoordinatorError):
            c.settle(permit["request_id"], {"prompt_tokens": 2, "completion_tokens": 0}, {})
        self.assertEqual(c.snapshot()["halt"], "conflicting_settlement")
        self.assertEqual(c.snapshot()["estimated_cost_at_peak"], "1")

    def test_unknown_usage_keeps_reservation_and_first_halt(self):
        c = self.coordinator()
        self.request(c, reserve="6")
        permit = c.dispatch()[0]
        c.mark_unknown(permit["request_id"], "api_error")
        c.stop("later_error")
        state = c.snapshot()
        self.assertEqual(state["reserved_total"], "6")
        self.assertEqual(len(state["unknown_requests"]), 1)
        self.assertEqual(state["halt"], "api_error")
        self.assertEqual(c.dispatch(), [])

    def test_invalid_usage_is_unknown_and_reserve_is_not_released(self):
        for value in (None, {}, {"prompt_tokens": -1, "completion_tokens": 0},
                      {"prompt_tokens": True, "completion_tokens": 0}):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temp:
                c = Coordinator(temp)
                self.request(c)
                p = c.dispatch()[0]
                result = c.settle(p["request_id"], value, {})
                self.assertEqual(result["status"], "unknown_usage")
                self.assertEqual(c.snapshot()["reserved_total"], "1")
                self.assertEqual(c.snapshot()["response_count"], 1)

    def test_global_request_interval_and_inflight_cap(self):
        for limit in (1, 2, 4, 8):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as temp:
                clock = Clock()
                c = Coordinator(temp, max_inflight_requests=limit,
                                min_request_interval=1, clock=clock)
                for i in range(limit + 1):
                    self.request(c, f"SIM-{i}")
                times = []
                for i in range(limit):
                    clock.value = float(i)
                    permit = c.dispatch()
                    self.assertEqual(len(permit), 1)
                    times.append(permit[0]["granted_at"])
                    self.assertEqual(c.dispatch(), [])
                clock.value += 1
                self.assertEqual(c.dispatch(), [])
                self.assertEqual(times, list(map(float, range(limit))))
                self.assertEqual(c.snapshot()["max_observed_inflight"], limit)

    def test_worker_count_and_request_cap_are_independent(self):
        c = self.coordinator(max_inflight_requests=2)
        for i in range(8):
            self.request(c, f"SIM-{i}")
        self.assertEqual(len(c.dispatch()), 2)
        self.assertEqual(c.snapshot()["max_observed_inflight"], 2)

    def test_persistence_delay_does_not_shorten_permission_interval(self):
        clock = Clock()
        c = self.coordinator(min_request_interval=0.015, clock=clock)
        self.request(c, "SIM-A")
        self.request(c, "SIM-B")
        original_log = c._log

        def delayed_first_log(record, kind, **details):
            if kind == "request" and record["number"] == 1:
                clock.value += 0.01
            original_log(record, kind, **details)

        with patch.object(c, "_log", side_effect=delayed_first_log):
            self.assertEqual(len(c.dispatch()), 1)
            clock.value = 0.015
            self.assertEqual(c.dispatch(), [], "next permit must wait from persisted permission time")
            clock.value = 0.025
            self.assertEqual(len(c.dispatch()), 1)
        requests = [json.loads(line) for line in (self.root / "requests.jsonl").read_text().splitlines()]
        self.assertGreaterEqual(requests[1]["monotonic_time"] - requests[0]["monotonic_time"], 0.015)

    def test_persisted_pending_count_matches_queue(self):
        c = self.coordinator(max_inflight_requests=1, max_requests_per_case=1)

        def assert_pending(expected):
            saved = json.loads((self.root / "budget.json").read_text())
            self.assertEqual(c.snapshot()["pending_count"], expected)
            self.assertEqual(saved["pending_count"], expected)

        self.request(c, "SIM-A")
        self.request(c, "SIM-B")
        assert_pending(2)
        first = c.dispatch()[0]
        assert_pending(1)
        c.settle(first["request_id"], {"prompt_tokens": 0, "completion_tokens": 0}, {})
        self.request(c, "SIM-A", attempt=2)
        assert_pending(2)
        results = c.dispatch()
        self.assertEqual([r["status"] for r in results], ["granted", "case_limit"])
        assert_pending(0)

    def test_stop_cancels_pending_and_duplicate_attempt_is_halted(self):
        c = self.coordinator()
        self.request(c)
        c.stop("api_error")
        result = c.acquire("SIM-A", 1, "1", {"payload": {"model": "offline"}})
        self.assertEqual(result["status"], "halted")
        self.assertEqual(c.snapshot()["pending_count"], 0)
        self.assertEqual(json.loads((self.root / "budget.json").read_text())["pending_count"], 0)

    def test_batch_and_case_request_limits(self):
        c = self.coordinator(max_requests=2, max_requests_per_case=1)
        self.request(c)
        p = c.dispatch()[0]
        c.settle(p["request_id"], {"prompt_tokens": 0, "completion_tokens": 0}, {})
        self.request(c, attempt=2)
        self.assertEqual(c.dispatch()[0]["status"], "case_limit")
        self.assertIsNone(c.snapshot()["halt"])
        self.request(c, "SIM-B")
        c.dispatch()
        self.request(c, "SIM-C")
        self.assertEqual(c.dispatch(), [])
        self.assertEqual(c.snapshot()["halt"], "batch_request_limit")
        self.assertEqual(c.snapshot()["requests"], 2)

    def test_budget_exhaustion_without_inflight_stops_batch(self):
        c = self.coordinator(budget_limit="1")
        self.request(c, reserve="2")
        self.assertEqual(c.dispatch(), [])
        self.assertEqual(c.snapshot()["halt"], "budget_limit")

    def test_ledger_write_failure_grants_no_permission(self):
        c = self.coordinator()
        self.request(c)
        with patch.object(c, "_persist", side_effect=OSError("write failed")):
            with self.assertRaises(CoordinatorError):
                c.dispatch()
        self.assertEqual(c.snapshot()["halt"], "ledger_write_failure")
        self.assertFalse((self.root / "requests.jsonl").exists())

    def test_acquire_after_stop_cannot_create_request(self):
        c = self.coordinator()
        c.stop("api_error")
        result = c.acquire("SIM-A", 1, "1", {})
        self.assertEqual(result["status"], "halted")
        self.assertEqual(c.snapshot()["requests"], 0)

    def test_different_payload_for_same_attempt_is_rejected(self):
        c = self.coordinator()
        self.request(c)
        with self.assertRaises(CoordinatorError):
            c.acquire("SIM-A", 1, "2", {})
        self.assertEqual(c.snapshot()["halt"], "conflicting_request")


if __name__ == "__main__":
    unittest.main()
