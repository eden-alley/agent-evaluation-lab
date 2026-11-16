"""Create a separate U04 scope review from a frozen v0.2 fixture and saved run.

This does not import submitted code, execute tests, call models, or update the Lab.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from lab.rechecking import u04_scope as rule


INPUT_SHA256 = 'd882d1956d588386b9751d344112c52bd27ce8d8647c4209e19d4615e182232a'


def hashes(root: Path) -> dict:
    """Match the frozen grader's file selection; exclude its transient outputs."""
    if not root.is_dir():
        raise ValueError(f'missing source directory: {root}')
    return {p.relative_to(root).as_posix(): rule.sha256(p.read_bytes())
            for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts
            and not p.name.startswith('.agent-command-')}


def digest_files(files: dict) -> str:
    return rule.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode())


def calibrate(fixture: Path, case_dir: Path, output: Path) -> dict:
    fixture, case_dir, output = (Path(p).resolve() for p in (fixture, case_dir, output))
    # Expected layout: <suite>/cases/U04 and <run>/<execution>/U04.
    protected_roots = [fixture.parent.parent, case_dir.parent.parent]
    if any(output.is_relative_to(root) for root in protected_roots):
        raise ValueError('output must be outside the source suite and source run')
    if output.exists():
        raise FileExistsError(f'output already exists: {output}')
    source_paths = {'task': fixture / '题面.md', 'original_test': fixture / 'input' / rule.TEST_PATH,
                    'result': case_dir / 'result.json', 'grade': case_dir / 'grade' / 'grade.json'}
    blobs = {key: path.read_bytes() for key, path in source_paths.items()}
    if rule.sha256(blobs['task']) != rule.TASK_SHA256:
        raise ValueError('U04 task version mismatch')
    if rule.sha256(blobs['original_test']) != rule.ORIGINAL_TEST_SHA256:
        raise ValueError('U04 original test version mismatch')
    initial = hashes(fixture / 'input')
    if digest_files(initial) != INPUT_SHA256:
        raise ValueError('U04 input version mismatch')
    submitted = hashes(case_dir / 'workspace')
    result = json.loads(blobs['result'])
    grade = json.loads(blobs['grade'])
    if result.get('id') != 'U04' or grade.get('id') != 'U04':
        raise ValueError('result and grade must both identify U04')
    if result.get('source_hashes') != submitted:
        raise ValueError('saved workspace does not match result source hashes')
    checks = grade.get('checks', {})
    expected_checks = {'scope', 'report', 'public', 'independent', 'agent_tested_final'}
    if set(checks) != expected_checks or any(
        not isinstance(check, dict) or check.get('value') not in (0, 1, 'unknown')
        for check in checks.values()
    ):
        raise ValueError('unexpected U04 historical grade schema')
    changed = {key for key in initial.keys() | submitted.keys() if initial.get(key) != submitted.get(key)}
    new_tests = {key for key in changed - initial.keys() if re.fullmatch(r'tests/test_[^/]+\.py', key)}
    out_of_scope = sorted(changed - rule.ALLOWED_PATHS - new_tests)
    legacy_scope = checks['scope']
    if (legacy_scope.get('evidence', {}).get('out_of_scope') != out_of_scope
            or legacy_scope['value'] != int(not out_of_scope)):
        raise ValueError('legacy scope evidence disagrees with the saved files')
    test_path = case_dir / 'workspace' / rule.TEST_PATH
    submitted_test = test_path.read_bytes() if test_path.is_file() else b''
    assessment = rule.assess_test_preservation(blobs['original_test'], submitted_test)
    calibrated = dict(assessment)
    extra = sorted(set(out_of_scope) - {rule.TEST_PATH})
    if (extra or new_tests) and calibrated['value'] != 0:
        calibrated = {'value': 'unknown', 'reason': '存在其他范围变动或新增测试文件，需要独立复核',
                      'evidence': {'other_paths': extra, 'added_test_files': sorted(new_tests),
                                   'test_preservation': assessment}}
    historical = {key: value for key, value in checks.items() if key != 'scope'}
    values = [calibrated['value']] + [check['value'] for check in historical.values()]
    verdict = 'fail' if 0 in values else ('unknown' if 'unknown' in values else 'pass')
    report = {
        'schema_version': 1, 'case_id': 'U04', 'rule_version': rule.RULE_VERSION,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'status': 'separate_offline_review', 'applied_to_official_scores': False,
        'paid_model_requests': 0, 'historical_checks_reexecuted': False,
        'basis': '题面要求保留已有测试，并允许新增回归测试；原测试文件哈希变化不单独构成失败。',
        'limitations': '仅复核 scope；历史功能、报告和最终自测判据未重跑。AST 检查不证明任意 Python 代码等价。',
        'original_grade': grade, 'calibrated_scope': calibrated,
        'historical_checks': historical, 'conditional_verdict': verdict,
        'conditional_verdict_note': '仅在沿用历史其他判据、接受本次 scope 复核时成立，不是新的真实评测成绩。',
        'changed_paths': sorted(changed), 'legacy_out_of_scope': out_of_scope,
        'inputs': {key: {'path': str(source_paths[key]), 'sha256': rule.sha256(blob)}
                   for key, blob in blobs.items()},
        'input_files': initial, 'submitted_files': submitted,
        'implementation_sha256': {'rule': rule.sha256(Path(rule.__file__).read_bytes()),
                                  'cli': rule.sha256(Path(__file__).read_bytes())},
    }
    # Exclusive creation also closes the check-then-write overwrite race.
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--case-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = calibrate(args.fixture, args.case_dir, args.output)
    print(json.dumps({'output': str(args.output.resolve()),
                      'scope': report['calibrated_scope']['value'],
                      'conditional_verdict': report['conditional_verdict']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
