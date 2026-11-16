"""Use synthetic archive scaffolding with pinned task/test bytes; no model/test execution."""
import json
import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'calibrate_u04_scope.py'
spec = importlib.util.spec_from_file_location('u04_calibration', SCRIPT)
calibration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calibration)
FIXTURES = Path(__file__).parent / 'fixtures' / 'u04_scope'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def archive(tmp_path, monkeypatch):
    fixture = tmp_path / 'suite' / 'cases' / 'U04'
    case = tmp_path / 'run' / 'execution' / 'U04'
    original = fixture / 'input' / 'tests' / 'test_contract.py'
    original.parent.mkdir(parents=True)
    original.write_bytes((FIXTURES / 'original.py').read_bytes())
    (fixture / '题面.md').write_bytes((FIXTURES / 'task.md').read_bytes())
    submitted = case / 'workspace' / 'tests' / 'test_contract.py'
    submitted.parent.mkdir(parents=True)
    submitted.write_bytes((FIXTURES / 'appended.py').read_bytes())
    # Only the full input-tree digest is synthetic; production constants stay pinned.
    monkeypatch.setattr(calibration, 'INPUT_SHA256', calibration.digest_files(calibration.hashes(fixture / 'input')))
    write_json(case / 'result.json', {'id': 'U04', 'source_hashes': calibration.hashes(case / 'workspace')})
    checks = {key: {'value': 1, 'evidence': 'historical'}
              for key in ['report', 'public', 'independent', 'agent_tested_final']}
    checks['scope'] = {'value': 0, 'evidence': {'out_of_scope': ['tests/test_contract.py']}}
    write_json(case / 'grade' / 'grade.json', {'id': 'U04', 'verdict': 'fail', 'checks': checks})
    return fixture, case, tmp_path / 'report.json'


def test_calibration_keeps_history_and_produces_separate_report(archive):
    fixture, case, output = archive
    before = calibration.hashes(case)
    report = calibration.calibrate(fixture, case, output)
    assert report['calibrated_scope']['value'] == 1
    assert report['original_grade']['checks']['scope']['value'] == 0
    assert report['conditional_verdict'] == 'pass'
    assert report['historical_checks_reexecuted'] is False
    assert report['paid_model_requests'] == 0
    assert json.loads(output.read_text(encoding='utf-8')) == report
    assert calibration.hashes(case) == before


@pytest.mark.parametrize('kind', ['task', 'input', 'result-id', 'grade-id', 'workspace', 'legacy-scope'])
def test_wrong_or_stale_inputs_are_rejected(archive, kind):
    fixture, case, output = archive
    if kind == 'task':
        (fixture / '题面.md').write_text('different task', encoding='utf-8')
    elif kind == 'input':
        (fixture / 'input' / 'extra.py').write_text('changed', encoding='utf-8')
    elif kind == 'workspace':
        (case / 'workspace' / 'extra.py').write_text('changed', encoding='utf-8')
    else:
        path = case / ('result.json' if kind == 'result-id' else 'grade/grade.json')
        data = json.loads(path.read_text(encoding='utf-8'))
        if kind.endswith('-id'):
            data['id'] = 'U03'
        else:
            data['checks']['scope']['evidence']['out_of_scope'] = []
        write_json(path, data)
    with pytest.raises(ValueError):
        calibration.calibrate(fixture, case, output)
    assert not output.exists()


def test_existing_output_is_never_overwritten(archive):
    fixture, case, output = archive
    output.write_text('keep', encoding='utf-8')
    with pytest.raises(FileExistsError):
        calibration.calibrate(fixture, case, output)
    assert output.read_text(encoding='utf-8') == 'keep'


@pytest.mark.parametrize('destination', ['fixture', 'case', 'run-sibling', 'suite-sibling'])
def test_output_cannot_be_written_into_sources(archive, destination):
    fixture, case, output = archive
    parent = {'fixture': fixture, 'case': case, 'run-sibling': case.parent / 'other',
              'suite-sibling': fixture.parent / 'other'}[destination]
    output = parent / 'new-report.json'
    with pytest.raises(ValueError, match='source'):
        calibration.calibrate(fixture, case, output)
    assert not output.exists()


@pytest.mark.parametrize('value,expected', [(0, 'fail'), ('unknown', 'unknown')])
def test_other_historical_failures_and_unknowns_are_preserved(archive, value, expected):
    fixture, case, output = archive
    path = case / 'grade' / 'grade.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['checks']['public']['value'] = value
    write_json(path, data)
    report = calibration.calibrate(fixture, case, output)
    assert report['conditional_verdict'] == expected
    assert report['historical_checks']['public']['value'] == value


def test_dynamic_addition_remains_unknown(archive):
    fixture, case, output = archive
    path = case / 'workspace' / 'tests' / 'test_contract.py'
    path.write_bytes(path.read_bytes() + b'\nProjectPagination.run = lambda self: None\n')
    write_json(case / 'result.json', {'id': 'U04', 'source_hashes': calibration.hashes(case / 'workspace')})
    report = calibration.calibrate(fixture, case, output)
    assert report['calibrated_scope']['value'] == 'unknown'
    assert report['conditional_verdict'] == 'unknown'


@pytest.mark.parametrize('content', [
    b'from test_contract import ProjectPagination\nProjectPagination.test_first_page_and_existing_request = lambda self: None\n',
    b'def test_simple():\n    assert 1 == 1\n',
])
def test_new_test_files_require_separate_review_even_when_legacy_allows_them(archive, content):
    fixture, case, output = archive
    (case / 'workspace' / 'tests' / 'test_aaa.py').write_bytes(content)
    write_json(case / 'result.json', {'id': 'U04', 'source_hashes': calibration.hashes(case / 'workspace')})
    report = calibration.calibrate(fixture, case, output)
    assert report['calibrated_scope']['value'] == 'unknown'
    assert report['calibrated_scope']['evidence']['added_test_files'] == ['tests/test_aaa.py']
    assert report['conditional_verdict'] == 'unknown'
