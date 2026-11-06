"""Agent registration and configuration-only checks."""
import json
import re
import uuid
from pathlib import Path
from fastapi import APIRouter, Request
from .db import connect
from .errors import error
from .projects import find_project, now
from .schemas import AgentInput

router = APIRouter(prefix="/api/v1/projects/{project_id}/agent")


def agent_dict(row):
    result = dict(row)
    result["config"] = json.loads(result["config"])
    result["last_check"] = json.loads(result["last_check"]) if result["last_check"] else None
    return result

@router.put("")
def put_agent(project_id: str, payload: AgentInput, request: Request):
    with connect(request.app.state.db_path) as conn:
        if not find_project(conn, project_id):
            return error("PROJECT_NOT_FOUND", "找不到项目，请刷新列表后重试。", 404)
        timestamp = now()
        conn.execute("""INSERT INTO agents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(project_id) DO UPDATE SET name=excluded.name, source_path=excluded.source_path,
            python_executable=excluded.python_executable, entrypoint=excluded.entrypoint, config=excluded.config,
            updated_at=excluded.updated_at, last_check=NULL""", (str(uuid.uuid4()), project_id, payload.name, payload.source_path, payload.python_executable, payload.entrypoint, json.dumps(payload.config, ensure_ascii=False), timestamp, timestamp))
        return agent_dict(conn.execute("SELECT * FROM agents WHERE project_id=?", (project_id,)).fetchone())

@router.get("")
def get_agent(project_id: str, request: Request):
    with connect(request.app.state.db_path) as conn:
        if not find_project(conn, project_id):
            return error("PROJECT_NOT_FOUND", "找不到项目，请刷新列表后重试。", 404)
        row = conn.execute("SELECT * FROM agents WHERE project_id=?", (project_id,)).fetchone()
        return agent_dict(row) if row else error("AGENT_NOT_REGISTERED", "尚未注册智能体，请先保存注册信息。", 404)

@router.post("/check")
def check_agent(project_id: str, request: Request):
    with connect(request.app.state.db_path) as conn:
        if not find_project(conn, project_id):
            return error("PROJECT_NOT_FOUND", "找不到项目，请刷新列表后重试。", 404)
        row = conn.execute("SELECT * FROM agents WHERE project_id=?", (project_id,)).fetchone()
        if not row:
            return error("AGENT_NOT_REGISTERED", "尚未注册智能体，请先保存注册信息。", 404)
        agent = agent_dict(row)
    report = static_check(agent)
    with connect(request.app.state.db_path) as conn:
        conn.execute("UPDATE agents SET last_check=? WHERE project_id=? AND id=? AND updated_at=?", (json.dumps(report, ensure_ascii=False), project_id, agent["id"], agent["updated_at"]))
    return report


def static_check(agent):
    root = Path(agent["source_path"]).expanduser()
    interpreter = Path(agent["python_executable"]).expanduser()
    try:
        root_ok = root.is_dir()
        resolved_root = root.resolve()
        entry = (root / agent["entrypoint"]).resolve()
        entry_ok = root_ok and entry.is_relative_to(resolved_root) and entry.is_file()
        python_ok = interpreter.is_file()
    except (OSError, RuntimeError, ValueError):
        root_ok = entry_ok = python_ok = False
    checks = []
    for name, ok, success, failure in (
        ("source_path", root_ok, "源码目录存在。", "源码目录不可用，请检查路径。"),
        ("python_executable", python_ok, "Python 文件存在。", "Python 文件不可用，请检查路径。"),
        ("entrypoint", entry_ok, "入口文件存在且位于源码目录内。", "入口文件不存在或位于源码目录外，请检查路径。"),
    ):
        checks.append({"name": name, "status": "pass" if ok else "fail", "message": success if ok else failure})
    return {"configuration_status": "ready" if root_ok and python_ok and entry_ok else "unavailable", "runtime_status": "not_tested", "checked_at": now(), "checks": checks, "git_commit": git_commit(root) if root_ok else None, "git_dirty": None}


def git_commit(root):
    """Read only standard Git refs; do not invoke Git, hooks, filters or config.

    Linked worktrees and unusual/symlinked metadata return None. Dirty state is
    deliberately not checked. Limit reads and never follow metadata symlinks.
    """
    try:
        for folder in (root.resolve(), *root.resolve().parents):
            gitdir = folder / ".git"
            if gitdir.is_symlink():
                return None
            if gitdir.is_file():
                return None
            if gitdir.is_dir():
                break
        else:
            return None

        def read_metadata(path, limit):
            relative = path.relative_to(gitdir)
            parts = [gitdir.joinpath(*relative.parts[:i]) for i in range(1, len(relative.parts) + 1)]
            if any(part.is_symlink() for part in parts) or not path.resolve().is_relative_to(gitdir.resolve()):
                return None
            if not path.is_file() or path.stat().st_size > limit:
                return None
            return path.read_text(encoding="ascii")

        head = read_metadata(gitdir / "HEAD", 4096)
        if head is None:
            return None
        head = head.strip()
        if re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", head):
            return head.lower()
        if not head.startswith("ref: "):
            return None
        ref = head[5:]
        if not re.fullmatch(r"refs/[A-Za-z0-9._/-]+", ref) or ".." in ref or "//" in ref:
            return None
        loose = read_metadata(gitdir / ref, 4096)
        if loose is not None:
            value = loose.strip()
            return value.lower() if re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", value) else None
        packed = read_metadata(gitdir / "packed-refs", 4 * 1024 * 1024)
        if packed:
            for line in packed.splitlines():
                parts = line.split(" ")
                if len(parts) == 2 and parts[1] == ref and re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", parts[0]):
                    return parts[0].lower()
    except (OSError, UnicodeError, RuntimeError, ValueError):
        return None
    return None
