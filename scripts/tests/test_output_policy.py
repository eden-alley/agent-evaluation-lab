"""Opt-in output capacity for the existing daily evaluation entry, offline only."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import formal20_runtime as runtime

POLICY = {'max_tokens': 16384, 'timeout': 180, 'output_truncation_recovery': 1}


class OutputPolicyTests(unittest.TestCase):
    def config(self, **changes):
        return {**runtime.default_binding(), **changes}

    def test_old_plans_keep_exact_effective_parameters(self):
        effective = runtime.effective_parameters(self.config())
        self.assertEqual(effective['max_tokens'], 4096)
        self.assertEqual(effective['timeout'], 90)
        self.assertNotIn('output_truncation_recovery', effective)

    def test_explicit_policy_is_frozen_and_stale_snapshot_rejected(self):
        config = self.config(output_policy=POLICY, case_timeout=210)
        effective = runtime.effective_parameters(config)
        for key, value in POLICY.items():
            self.assertEqual(effective[key], value)
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            runtime.effective_parameters({**config, 'effective_parameters': {**effective, 'max_tokens': 4096}})

    def test_bad_policy_and_conflicting_outer_timeout_fail_before_execution(self):
        for policy in ({**POLICY, 'max_tokens': True}, {**POLICY, 'timeout': 0},
                       {**POLICY, 'output_truncation_recovery': 2}, {**POLICY, 'model': 'other'}, {}):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                runtime.effective_parameters(self.config(output_policy=policy))
        for key in ('case_timeout', 'timeout_after_ready'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'timeout'):
                runtime.effective_parameters(self.config(output_policy=POLICY, **{key: 120}))

    def test_freeze_reserves_outer_timeout_without_loading_client(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime, 'execution_files', return_value={'fixture': 'hash'}), \
                patch.object(runtime, 'load_cases', return_value=[]):
            path = Path(directory) / 'plan.json'
            runtime.freeze_plan(self.config(output_policy=POLICY, case_ids=['U05'], transport='scripted_api', validation=True), path)
            saved = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(saved['case_timeout'], 210)
        self.assertEqual(saved['effective_parameters']['max_tokens'], 16384)

    def test_agent_options_enable_new_policy_and_leave_old_constructor_compatible(self):
        self.assertEqual(runtime.output_recovery_options(SimpleNamespace(PARAMS={})), {})
        self.assertEqual(runtime.output_recovery_options(SimpleNamespace(PARAMS=POLICY)),
                         {'output_truncation_recovery': 1})

    def test_optional_recovery_cap_is_frozen_and_forwarded(self):
        policy={**POLICY,'max_tokens':512,'recovery_max_output_tokens':4096}
        effective=runtime.effective_parameters(self.config(output_policy=policy))
        self.assertEqual(effective['recovery_max_output_tokens'],4096)
        self.assertEqual(runtime.output_recovery_options(SimpleNamespace(PARAMS=effective)),
                         {'output_truncation_recovery':1,'recovery_max_output_tokens':4096})
        for value in (True,0,-1,'4096'):
            with self.assertRaises(ValueError):
                runtime.output_policy({'output_policy':{**policy,'recovery_max_output_tokens':value}})


if __name__ == '__main__':
    unittest.main()
