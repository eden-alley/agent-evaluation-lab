"""Built-in catalog and user-authored immutable Skill versions; never execute content."""
import json
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import Field, StrictStr

from .datasets import QualityError
from .db import connect
from .projects import now
from .quality_checks import digest
from .quality_schemas import Contract, ShortText, Text

router = APIRouter(prefix="/api/v1/skills")


class SkillInput(Contract):
    name: ShortText
    description: Text
    kind: Literal["evaluation", "business"]
    tags: list[ShortText] = Field(default_factory=list, max_length=20)


class SkillContent(Contract):
    content: Annotated[StrictStr, Field(min_length=1, max_length=50000)]
    change_note: Annotated[StrictStr, Field(max_length=4000)] = ""


def skill_row(conn, identity):
    row = conn.execute("SELECT * FROM skills WHERE id=?", (identity,)).fetchone()
    if not row:
        raise QualityError("SKILL_NOT_FOUND", "找不到技能目录项。", 404)
    return row


def skill_object(conn, row, with_versions=False):
    value = dict(row)
    value["tags"] = json.loads(value["tags"])
    active = conn.execute("SELECT id,version,content_hash,published_at FROM skill_versions WHERE id=?", (row["active_version_id"],)).fetchone()
    value["active_version"] = dict(active) if active else None
    if with_versions:
        value["versions"] = [dict(v) for v in conn.execute("SELECT * FROM skill_versions WHERE skill_id=? ORDER BY version DESC", (row["id"],))]
    return value


def validate_sources(conn, source):
    seen = set()
    for reference in source.get("skills", []):
        if reference["skill_id"] in seen:
            raise QualityError("INVALID_SKILL_SOURCE", "同一产物不能同时声明同一技能的多个版本。", 422)
        seen.add(reference["skill_id"])
        row = conn.execute("SELECT * FROM skill_versions WHERE id=? AND skill_id=?", (reference["version_id"], reference["skill_id"])).fetchone()
        if not row or row["status"] != "published" or row["content_hash"] != reference["content_hash"]:
            raise QualityError("INVALID_SKILL_SOURCE", "技能来源须引用平台中已发布的版本与对应内容哈希。", 422)


@router.get("")
def list_skills(request: Request, available_only: bool = False, query: str = "", kind: str = ""):
    with connect(request.app.state.db_path) as conn:
        rows = conn.execute("SELECT * FROM skills ORDER BY created_at,id").fetchall()
        items = []
        for row in rows:
            if available_only and not row["active_version_id"]:
                continue
            if kind and row["kind"] != kind:
                continue
            if query and query.casefold() not in (row["name"] + row["description"] + row["tags"]).casefold():
                continue
            items.append(skill_object(conn, row))
        return {"items": items}


@router.post("", status_code=201)
def create_skill(payload: SkillInput, request: Request):
    with connect(request.app.state.db_path) as conn:
        identity = str(uuid.uuid4())
        conn.execute("INSERT INTO skills VALUES (?,?,?,?,?,'user',NULL,?)", (identity, payload.name, payload.description, payload.kind, json.dumps(payload.tags, ensure_ascii=False), now()))
        return skill_object(conn, skill_row(conn, identity), True)


@router.get("/{skill_id}")
def get_skill(skill_id: str, request: Request):
    with connect(request.app.state.db_path) as conn:
        return skill_object(conn, skill_row(conn, skill_id), True)


@router.get("/{skill_id}/content")
def get_published_content(skill_id: str, request: Request, version_id: str | None = None):
    with connect(request.app.state.db_path) as conn:
        skill = skill_row(conn, skill_id)
        row = conn.execute("SELECT * FROM skill_versions WHERE id=? AND skill_id=?", (version_id or skill["active_version_id"], skill_id)).fetchone()
        if not row or row["status"] != "published":
            raise QualityError("SKILL_NOT_READY", "该技能尚无可读取的已发布版本，请先共同设计并发布内容。")
        return {"skill": skill_object(conn, skill), "version": dict(row)}


@router.post("/{skill_id}/versions", status_code=201)
def save_content(skill_id: str, payload: SkillContent, request: Request):
    with connect(request.app.state.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        skill_row(conn, skill_id)
        previous = conn.execute("SELECT * FROM skill_versions WHERE skill_id=? ORDER BY version DESC LIMIT 1", (skill_id,)).fetchone()
        # A double-click with unchanged content does not create redundant drafts.
        if previous and previous["content"] == payload.content and previous["change_note"] == payload.change_note:
            return dict(previous)
        identity = str(uuid.uuid4())
        conn.execute("INSERT INTO skill_versions VALUES (?,?,?,?,?,?,'draft',?,NULL)", (identity, skill_id, previous["version"] + 1 if previous else 1,
            payload.content, digest({"content": payload.content}), payload.change_note, now()))
        return dict(conn.execute("SELECT * FROM skill_versions WHERE id=?", (identity,)).fetchone())


@router.post("/{skill_id}/versions/{version_id}/publish")
def publish_content(skill_id: str, version_id: str, request: Request):
    with connect(request.app.state.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        skill = skill_row(conn, skill_id)
        row = conn.execute("SELECT * FROM skill_versions WHERE id=? AND skill_id=?", (version_id, skill_id)).fetchone()
        if not row:
            raise QualityError("SKILL_VERSION_NOT_FOUND", "找不到技能版本。", 404)
        if row["status"] == "published":
            return skill_object(conn, skill, True)
        active = conn.execute("SELECT version FROM skill_versions WHERE id=?", (skill["active_version_id"],)).fetchone()
        if active and row["version"] <= active["version"]:
            raise QualityError("STALE_SKILL_VERSION", "已有更新的发布版本，请创建新草稿。")
        conn.execute("UPDATE skill_versions SET status='published',published_at=? WHERE id=?", (now(), version_id))
        conn.execute("UPDATE skills SET active_version_id=? WHERE id=?", (version_id, skill_id))
        return skill_object(conn, skill_row(conn, skill_id), True)
