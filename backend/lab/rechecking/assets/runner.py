"""Trusted test harness; launched with isolated Python, never Agent temp scripts."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback
import unittest

workspace = Path.cwd()
sys.path.insert(0, str(workspace))
test_path = Path(__file__).with_name(sys.argv[1] + '.py')
spec = importlib.util.spec_from_file_location('_trusted_check_suite', test_path)
module = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(module)
except BaseException:
    traceback.print_exc()
    print('CHECK_RESULT=' + json.dumps({'tests': 0, 'failures': 0, 'errors': 1,
        'skipped': 0, 'successful': False, 'delivery_error': True, 'stage': 'delivery_import'}), flush=True)
    sys.exit(1)
suite = unittest.defaultTestLoader.loadTestsFromModule(module)
result = unittest.TextTestRunner(verbosity=2).run(suite)
print('CHECK_RESULT=' + json.dumps({'tests': result.testsRun, 'failures': len(result.failures),
    'errors': len(result.errors), 'skipped': len(result.skipped), 'successful': result.wasSuccessful()}), flush=True)
sys.exit(0 if result.wasSuccessful() else 1)
