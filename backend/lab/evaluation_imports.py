"""Read-only display of externally executed, locally imported evaluation bundles.

No runner, model client, arbitrary filesystem path or write endpoint is exposed.
The importer creates run.json and a SHA-256 manifest under the database directory.
"""
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Request
from fastapi.responses import Response
from urllib.parse import quote

from .datasets import QualityError, require_project
from .db import connect
from .evaluation_trace import explain_trace

router = APIRouter(prefix='/api/v1/evaluation-runs')


def root_for(request):
    return (Path(request.app.state.db_path).parent / 'evaluation-runs').resolve()


def read_run(request, run_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', run_id):
        raise QualityError('RUN_NOT_FOUND', '找不到真实运行。', 404)
    root = root_for(request)
    folder = (root / run_id).resolve()
    source = (folder / 'run.json').resolve()
    if folder.parent != root or source.parent != folder or not source.is_file():
        raise QualityError('RUN_NOT_FOUND', '找不到真实运行。', 404)
    data = json.loads(source.read_text(encoding='utf-8'))
    if data['id'] != run_id:
        raise QualityError('INVALID_IMPORT', '导入标识不一致。', 409)
    with connect(request.app.state.db_path) as conn:
        require_project(conn, data['project_id'])
    return folder, data


@router.get('')
def list_runs(request: Request, project_id: str | None = None):
    items = []
    for source in sorted(root_for(request).glob('*/run.json')):
        _, data = read_run(request, source.parent.name)
        if project_id is None or data['project_id'] == project_id:
            items.append({key: value for key, value in data.items() if key not in ('cases', 'files')})
    return {'items': items}


@router.get('/{run_id}')
def get_run(run_id: str, request: Request):
    _, data = read_run(request, run_id)
    return data


def read_artifact(folder, path, max_bytes=None):
    relative = PurePosixPath(path)
    if '\\' in path or ':' in path or relative.is_absolute() or '..' in relative.parts:
        raise QualityError('ARTIFACT_NOT_FOUND', '找不到该证据文件。', 404)
    manifest_path = (folder / 'manifest.json').resolve()
    if manifest_path.parent != folder:
        raise QualityError('ARTIFACT_NOT_FOUND', '找不到证据清单。', 404)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    record = next((item for item in manifest['files'] if item['path'] == path), None)
    target = (folder / path).resolve()
    if record is None or not target.is_relative_to(folder) or not target.is_file():
        raise QualityError('ARTIFACT_NOT_FOUND', '找不到该证据文件。', 404)
    if max_bytes is not None and target.stat().st_size > max_bytes:
        raise QualityError('ARTIFACT_TOO_LARGE', '轨迹文件较大，请下载原始记录。', 413)
    content = target.read_bytes()
    if len(content) != record['bytes'] or hashlib.sha256(content).hexdigest() != record['sha256']:
        raise QualityError('EVIDENCE_CHANGED', '证据文件与导入时的哈希不一致。', 409)
    return record, target, content


@router.get('/{run_id}/cases/{case_id}/trace')
def get_trace(run_id: str, case_id: str, request: Request):
    folder, run = read_run(request, run_id)
    case = next((item for item in run.get('cases', []) if item['id'] == case_id), None)
    if case is None:
        raise QualityError('CASE_NOT_FOUND', '找不到该题。', 404)
    source = next((file['path'] for file in case.get('files', [])
                   if PurePosixPath(file['path']).name == 'events.jsonl'), None)
    if source is None:
        return {'source': None, 'groups': []}
    _, _, raw = read_artifact(folder, source, max_bytes=32 * 1024 * 1024)
    try:
        groups = explain_trace(raw.decode('utf-8-sig'))
    except (ValueError, TypeError) as exc:
        raise QualityError('INVALID_TRACE', '轨迹格式无法识别，请查看原始记录。', 422) from exc
    return {'source': source, 'groups': groups}


@router.get('/{run_id}/cases/{case_id}/explanation')
def get_explanation(run_id: str, case_id: str, request: Request):
    folder, run = read_run(request, run_id)
    if not any(c['id'] == case_id for c in run.get('cases', [])):
        raise QualityError('CASE_NOT_FOUND', '找不到该题。', 404)
    from .run_explanations import for_run
    with connect(request.app.state.db_path) as conn:
        return for_run(conn, folder, run_id, case_id)


@router.get('/{run_id}/artifact')
def get_artifact(run_id: str, path: str, request: Request, download: bool = False):
    folder, _ = read_run(request, run_id)
    record, target, content = read_artifact(folder, path)
    if download:
        return Response(content, media_type='application/octet-stream', headers={
            'Content-Disposition': "attachment; filename*=UTF-8''" + quote(target.name),
            'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})
    if len(content) > 2 * 1024 * 1024:
        raise QualityError('ARTIFACT_TOO_LARGE', '此文件较大，请下载完整原件。', 413)
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise QualityError('BINARY_ARTIFACT', '二进制文件请下载原件。', 415)
    return {**record, 'content': text}
