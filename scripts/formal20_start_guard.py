"""Durable one-start reservations shared by daily, CLI and direct batch entrypoints."""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import threading

_HELD_LOCKS = threading.local()


def validate_run_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value):
        raise ValueError('Invalid run_id')
    if os.name == 'nt':
        reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
                    *(f'LPT{i}' for i in range(1, 10))}
        if value.endswith('.') or value.split('.')[0].upper() in reserved:
            raise ValueError('run_id must be an unambiguous usable Windows directory name')


@contextmanager
def execution_lock(out):
    """Hold one nonblocking OS lock through inspection, ledger open and execution.

    Same-thread nesting lets resume_run call run_batch without releasing the lock.
    The file may remain after a crash; the OS releases ownership on process exit.
    """
    out = Path(out).resolve(); key = os.path.normcase(str(out))
    held = getattr(_HELD_LOCKS, 'paths', None)
    if held is None: held = _HELD_LOCKS.paths = set()
    if key in held:
        yield
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    path = out.parent / ('.formal20-' + sha256(key.encode()).hexdigest()[:24] + '.lock')
    stream = path.open('a+b'); locked = False
    try:
        try:
            if os.name == 'nt':
                import msvcrt
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            raise PermissionError('This run is already executing or resuming; keep the original process') from None
        held.add(key)
        yield
    finally:
        held.discard(key)
        try:
            if locked:
                if os.name == 'nt':
                    stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()


def _identity(config, out, provider):
    delivery = config.get('delivery') or {}
    for key in config.keys() & delivery.keys():
        if config[key] != delivery[key]: raise ValueError('Execution/delivery configuration differs: ' + key)
    cfg = {**config, **delivery}
    if not all(cfg.get(key) for key in ('data_root', 'archive_root', 'run_id')):
        raise ValueError('Start requires explicit data_root, archive_root and run_id')
    validate_run_id(cfg['run_id'])
    approved = config.get('approved_plan_sha256') if provider else None
    if provider:
        plan = Path(config.get('plan_file', ''))
        if (not isinstance(approved, str) or not re.fullmatch(r'[0-9a-f]{64}', approved) or
                not plan.is_file() or sha256(plan.read_bytes()).hexdigest() != approved):
            raise PermissionError('批准计划指纹不一致')
    directory = Path(cfg['data_root']).resolve() / 'execution-approvals'
    filename = approved or sha256(('validation:' + cfg['run_id']).encode()).hexdigest()
    record = {'schema_version': 1, 'plan_sha256': approved,
        'plan_file': str(Path(config['plan_file']).resolve()) if config.get('plan_file') else None,
        'run_id': cfg['run_id'], 'out': str(Path(out).resolve()),
        'archive_root': str(Path(cfg['archive_root']).resolve())}
    return cfg, directory, directory / (filename + '.json'), record


def claim_start(config, out, *, provider=None):
    """Reserve run_id and (for paid runs) approval in one SQLite transaction.

    JSON receipts remain readable by older callers. A crash during receipt/commit
    fails closed: an existing receipt or reservation is never silently replaced.
    """
    provider = config.get('transport') == 'provider_api' if provider is None else provider
    if not provider and not config.get('delivery'): return None
    cfg, directory, path, record = _identity(config, out, provider)
    if Path(out).exists(): raise FileExistsError('Output directory already exists; use the original continuation')
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / 'start-reservations.sqlite3', timeout=30)
    try:
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('CREATE TABLE IF NOT EXISTS starts '
            '(run_id TEXT PRIMARY KEY, plan_sha256 TEXT UNIQUE, record TEXT NOT NULL, started INTEGER NOT NULL DEFAULT 0)')
        if os.name == 'nt':
            try:
                connection.execute('CREATE UNIQUE INDEX IF NOT EXISTS starts_windows_run_id ON starts(lower(run_id))')
            except sqlite3.IntegrityError:
                raise PermissionError('Existing start reservations contain conflicting Windows run IDs; preserve them for recovery') from None
        for folder in (Path(cfg['archive_root']) / cfg['run_id'],
                       Path(cfg['data_root']) / 'evaluation-runs' / cfg['run_id']):
            if folder.exists(): raise PermissionError('run_id already exists; preserve the original run')
        # Include pre-guard approval receipts; an upgrade must not release a used
        # approval or an existing run identity just because it has no SQLite row.
        for receipt in directory.glob('*.json'):
            previous = json.loads(receipt.read_text(encoding='utf-8'))
            previous_id = previous.get('run_id', '')
            same_run = (previous_id.rstrip('. ').casefold() == cfg['run_id'].casefold() if os.name == 'nt'
                        and isinstance(previous_id, str) else previous_id == cfg['run_id'])
            if (receipt == path or same_run or
                    (record['plan_sha256'] and previous.get('plan_sha256') == record['plan_sha256'])):
                raise PermissionError('本轮批准或run_id已用于启动。保留原现场并使用continue；新一轮需要新的计划及批准。')
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True)
        try:
            connection.execute('INSERT INTO starts (run_id, plan_sha256, record) VALUES (?, ?, ?)',
                (record['run_id'], record['plan_sha256'], encoded))
        except sqlite3.IntegrityError:
            raise PermissionError('本轮批准或run_id已用于启动。保留原现场并使用continue。') from None
        with path.open('x', encoding='utf-8') as stream:
            stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
        connection.commit()
    finally:
        connection.close()
    return str(path)


def verify_start(config, out, receipt):
    """Reuse a reservation only for its original output, including native resume."""
    provider = config.get('transport') == 'provider_api'
    _, directory, expected_path, expected = _identity(config, out, provider)
    path = Path(receipt).resolve()
    if path != expected_path or not path.is_file(): raise PermissionError('Original start reservation is required')
    record = json.loads(path.read_text(encoding='utf-8'))
    keys = ('plan_sha256', 'run_id', 'out')
    if any(record.get(key) != expected[key] for key in keys):
        raise PermissionError('Start reservation belongs to another approval, run_id or output')
    if 'archive_root' in record and record['archive_root'] != expected['archive_root']:
        raise PermissionError('Start reservation archive destination changed')
    if record.get('schema_version') == 1:
        database = directory / 'start-reservations.sqlite3'
        if not database.is_file(): raise PermissionError('Durable start reservation is missing')
        connection = sqlite3.connect(database)
        try:
            row = connection.execute('SELECT record FROM starts WHERE run_id = ?', (record['run_id'],)).fetchone()
        finally:
            connection.close()
        if not row or json.loads(row[0]) != record: raise PermissionError('Durable start reservation differs')
    return str(path)


def _activate_start(receipt, resume):
    record = json.loads(Path(receipt).read_text(encoding='utf-8'))
    if record.get('schema_version') != 1:
        if resume: return  # Existing approvals may continue their original ledger.
        raise PermissionError('An existing legacy approval cannot start a fresh run')
    connection = sqlite3.connect(Path(receipt).parent / 'start-reservations.sqlite3', timeout=30)
    try:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT started FROM starts WHERE run_id = ?', (record['run_id'],)).fetchone()
        if not row or (resume and not row[0]) or (not resume and row[0]):
            raise PermissionError('Start reservation is not valid for a new start/resume; preserve the original run')
        if not resume: connection.execute('UPDATE starts SET started = 1 WHERE run_id = ?', (record['run_id'],))
        connection.commit()
    finally:
        connection.close()


def guard_batch_start(config, out):
    """Final boundary before output creation, coordinator or worker startup."""
    if config.get('transport') != 'provider_api' and not config.get('delivery'): return config
    receipt = config.get('execution_start_record') or config.get('approval_record')
    if config.get('_resume'):
        if not receipt: raise PermissionError('Resume requires the original start reservation')
        saved = json.loads((Path(out) / 'config.json').read_text(encoding='utf-8'))
        if receipt != (saved.get('execution_start_record') or saved.get('approval_record')):
            raise PermissionError('Resume must keep the original start reservation')
    if receipt:
        receipt = verify_start(config, out, receipt)
    else:
        receipt = claim_start(config, out)
    _activate_start(receipt, bool(config.get('_resume')))
    if config.get('_resume'):
        from formal20_runtime import inspect_run
        decision = inspect_run(out)
        if decision['status'] != 'checkpoint_paused':
            raise PermissionError('Resume requires the original durable checkpoint: ' + decision.get('reason', decision['status']))
    return {**config, 'execution_start_record': receipt}
