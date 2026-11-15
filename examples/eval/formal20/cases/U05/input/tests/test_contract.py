from contextlib import redirect_stdout
from decimal import Decimal
from io import StringIO
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cli
from context import SessionStore
from permissions import Workspace


class InteractiveLimits(unittest.TestCase):
    def session(self, settings, prompts=("/limits", "exit"), changed_after_start=None):
        requests = []

        def create(**payload):
            requests.append(payload["messages"][-1]["content"])
            response = {
                "choices": [{"message": {"role": "assistant", "content": "offline reply"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 3, "total_tokens": 53},
            }
            return SimpleNamespace(model_dump=lambda **kw: response)

        fake_sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        real_get_model = cli.models.get_model
        state = {"DEEPSEEK_API_KEY": "offline-test-only", **settings}
        with TemporaryDirectory() as temp, patch.dict(os.environ, state, clear=True), patch.object(
            cli.models, "get_model", side_effect=lambda config, **kw: real_get_model(config, client=fake_sdk)
        ):
            workspace = Workspace(temp)
            agent = cli.create_agent(workspace=workspace)
            store = SessionStore(Path(temp) / "state")
            if changed_after_start:
                os.environ.update(changed_after_start)
            output = StringIO()
            with patch("builtins.input", side_effect=prompts), redirect_stdout(output):
                cli.interact(agent, store)
            limits = (agent.max_steps, agent.token_limit, agent.wall_time_limit_seconds)
            saved = store.load("default")
        return output.getvalue(), requests, limits, saved

    def assert_lines(self, output, expected):
        for line in expected:
            key, required = line.split("=", 1)
            candidates = [item.split("=", 1)[1] for item in output.splitlines()
                          if item.startswith(key + "=")]
            self.assertEqual(len(candidates), 1, output)
            if required == "off":
                self.assertEqual(candidates[0], required)
                continue
            value, origin = required.split(" ", 1)
            matched = re.fullmatch(r"([^\s]+)\s+(\((?:default|custom)\))", candidates[0])
            self.assertIsNotNone(matched, output)
            self.assertEqual(matched.group(2), origin)
            self.assertEqual(Decimal(matched.group(1)), Decimal(value))

    def test_default_limits_are_read_only(self):
        output, requests, limits, saved = self.session({})
        self.assert_lines(output, ["steps=30 (default)", "tokens=off", "time_seconds=off"])
        self.assertEqual(limits, (30, 0, 0))
        self.assertEqual(requests, [])
        self.assertIsNone(saved)

