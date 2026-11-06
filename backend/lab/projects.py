"""Project persistence routes."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from .db import connect
from .errors import error
from .schemas import ProjectCreate, ProjectUpdate

router = APIRouter(prefix="/api/v1/projects")

def now():
    return datetime.now(timezone.utc).isoformat()

def find_project(conn, project_id):
    return conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

@router.get("")
def list_projects(request: Request):
    with connect(request.app.state.db_path) as conn:
        return {"items": [dict(row) for row in conn.execute("SELECT * FROM projects ORDER BY created_at, id")]}

@router.post("", status_code=201)
def create_project(payload: ProjectCreate, request: Request):
    project_id, timestamp = str(uuid.uuid4()), now()
    with connect(request.app.state.db_path) as conn:
        conn.execute("INSERT INTO projects VALUES (?, ?, ?, ?, ?)", (project_id, payload.name, payload.description, timestamp, timestamp))
        return dict(find_project(conn, project_id))

@router.get("/{project_id}")
def get_project(project_id: str, request: Request):
    with connect(request.app.state.db_path) as conn:
        row = find_project(conn, project_id)
        return dict(row) if row else error("PROJECT_NOT_FOUND", "找不到项目，请刷新列表后重试。", 404)

@router.patch("/{project_id}")
def patch_project(project_id: str, payload: ProjectUpdate, request: Request):
    with connect(request.app.state.db_path) as conn:
        row = find_project(conn, project_id)
        if not row:
            return error("PROJECT_NOT_FOUND", "找不到项目，请刷新列表后重试。", 404)
        values = payload.model_dump(exclude_unset=True)
        conn.execute("UPDATE projects SET name=?, description=?, updated_at=? WHERE id=?", (values.get("name", row["name"]), values.get("description", row["description"]), now(), project_id))
        return dict(find_project(conn, project_id))
