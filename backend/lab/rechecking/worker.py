"""Independent checking jobs: verified inputs, disposable copies, append-only outputs."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from .archive import snapshot
from .checker import package, results, valid_suite, disk_content_hash
from ..db import connect
from ..evaluation_imports import read_run
from ..quality_checks import canonical

def execute(db_path, request, run_id, job_id):
    with connect(db_path) as conn:
        claimed = conn.execute("UPDATE check_runs SET status='running' WHERE id=? AND status='queued'", (job_id,)).rowcount
        if not claimed:
            return
        row = conn.execute("SELECT b.snapshot FROM check_runs j JOIN checker_bindings b ON b.id=j.binding_id WHERE j.id=?", (job_id,)).fetchone()
        bound = json.loads(row["snapshot"])
    try:
        folder, run = read_run(request, run_id)
        data = snapshot(folder, run, bound["task"]["case_id"])
        executor = request.app.state.recheck_executor
        if (data["source_hash"] != bound["source_hash"] or data["input_hash"] != bound["input_hash"]
                or package() != bound["package"] or disk_content_hash() != bound["package"]["content_hash"]
                or executor.identity() != bound["environment"]):
            raise RuntimeError("任务、输入、检查程序或执行环境发生变化，请建立新的绑定。")
        output = Path(db_path).parent / "check-runs" / job_id
        output.mkdir(parents=True, exist_ok=False)
        probes, evidence = [], []
        # Keep ephemeral paths short on Windows; persisted evidence stays beside the database.
        with tempfile.TemporaryDirectory(prefix="lab-check-") as tmp:
            for suite in ("public", "external"):
                copy = Path(tmp) / (suite + "-copy")
                copy.mkdir()
                for name, raw in data["workspace"].items():
                    target = copy / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                if (copy / ".checker").exists() or (copy / ".check-command.cmd").exists():
                    raise RuntimeError("交付物与保留的检查文件名冲突，未执行。")
                # Public tests are checker-owned; scope was evaluated from the untouched snapshot.
                tests = copy / "tests"
                if tests.exists():
                    shutil.rmtree(tests)
                probe = executor.run(copy, suite)
                valid_suite(probe, suite)
                probes.append(probe)
                path = suite + ".json"
                raw = canonical(probe).encode("utf-8")
                (output / path).write_bytes(raw)
                evidence.append({"kind": "retest", "path": path, "bytes": len(raw),
                                 "sha256": hashlib.sha256(raw).hexdigest(),
                                 "excerpt": raw.decode("utf-8")[:6000]})
        # Revalidate after execution: no success against a concurrently changed archive.
        fresh = snapshot(*read_run(request, run_id), bound["task"]["case_id"])
        if (fresh["input_hash"] != bound["input_hash"] or fresh["source_hash"] != bound["source_hash"]
                or disk_content_hash() != bound["package"]["content_hash"] or executor.identity() != bound["environment"]):
            raise RuntimeError("原归档在检查期间发生变化，未保存成绩。")
        report = results(data, probes, [ref["path"] for ref in evidence])
        report.update({"schema_version": 1, "binding": bound, "evidence": evidence,
                       "seconds": sum(p.get("seconds", 0) for p in probes)})
        with connect(db_path) as conn:
            conn.execute("UPDATE check_runs SET status='completed',report=? WHERE id=?", (canonical(report), job_id))
    except Exception as exc:
        with connect(db_path) as conn:
            conn.execute("UPDATE check_runs SET status='failed',error=? WHERE id=?",
                         (canonical({"code": "CHECK_EXECUTION_FAILED", "message": str(exc)[:800]}), job_id))
