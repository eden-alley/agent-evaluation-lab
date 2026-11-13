"""Resolve analyst-friendly narrative references against pinned case materials."""
import json
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, StrictInt, model_validator
from ..datasets import QualityError
from ..evaluation_imports import read_artifact
from ..quality_schemas import Contract, Identifier, ShortText, Text
from . import materials, metrics


class ExplanationEvidence(Contract):
    side: Literal["baseline", "candidate"]
    path: Annotated[str, Field(min_length=1, max_length=1000)]
    event_id: Annotated[StrictInt, Field(ge=1)] | None = None
    check_id: Identifier | None = None
    start_line: Annotated[StrictInt, Field(ge=1)] = 1
    line_count: Annotated[StrictInt, Field(ge=1, le=200)] = 40

    @model_validator(mode="after")
    def one_locator(self):
        if self.event_id is not None and self.check_id is not None:
            raise ValueError("同一引用使用事件编号或检查项编号，不能混用。")
        return self


class ExplanationParagraph(Contract):
    text: Text
    evidence: list[ExplanationEvidence] = Field(min_length=1, max_length=6)


class ExplanationStage(ExplanationParagraph):
    title: ShortText


class CaseExplanation(Contract):
    case_id: Identifier
    focus: Literal["baseline", "candidate", "comparison"]
    background: Text
    stages: list[ExplanationStage] = Field(min_length=1, max_length=8)
    result: ExplanationParagraph
    limitations: list[ShortText] = Field(default_factory=list, max_length=8)


def locate(snapshot, cid, side, path):
    entry = (snapshot.get(side) or {}).get("cases", {}).get(cid)
    catalog = (entry or {}).get("materials", [])
    matches = [m for m in catalog if m["path"] == path]
    if not matches and "/" not in path and "\\" not in path and path not in (".", ".."):
        matches = [m for m in catalog if PurePosixPath(m["path"]).name == path]
    if len(matches) != 1:
        raise QualityError("REVIEW_MATERIAL_NOT_FOUND", "文件不存在或名称不唯一，请使用材料包中的完整路径。", 404)
    return matches[0]


def event_preview(event):
    parts = []
    for key in ("event_id", "type", "tool", "ok", "exit_code", "code", "message", "stop_reason", "data", "text"):
        if key in event:
            parts.append(f"{key}: {str(event[key])[:6000]}")
    args = event.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            pass
    if isinstance(args, dict):
        ordered = sorted(args, key=lambda k: (k not in ("path", "command", "cmd"), k))
        parts.extend(f"{key}: {str(args[key])[:2000]}" for key in ordered[:12])
    elif args:
        parts.append("arguments: " + str(args)[:3000])
    return "\n".join(parts)[:12000]


def resolve_reference(request, snapshot, cid, pointer, cache):
    try:
        material = locate(snapshot, cid, pointer.side, pointer.path)
    except QualityError as exc:
        raise QualityError("EXPLANATION_EVIDENCE_NOT_FOUND", exc.message, 422) from exc
    start, count = pointer.start_line, pointer.line_count
    selected_event = None
    if pointer.event_id is not None:
        if material["id"] not in cache:
            if material["kind"] != "archive" or not material["path"].endswith(".jsonl"):
                raise QualityError("EXPLANATION_EVENT_NOT_FOUND", "事件引用必须指向本题已归档的JSONL记录。", 422)
            source = snapshot[pointer.side]
            folder = Path(request.app.state.db_path).parent / "evaluation-runs" / source["run_id"]
            _, _, raw = read_artifact(folder.resolve(), material["path"], max_bytes=32 * 1024 * 1024)
            if materials.sha(raw) != material["sha256"]:
                raise QualityError("EVIDENCE_CHANGED", "事件原件与固定快照不同。", 409)
            try:
                indexed = {}
                for n, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        continue
                    event.pop("files", None)  # The raw, hashed excerpt remains available separately.
                    identity = event.get("event_id")
                    if type(identity) is int:
                        indexed.setdefault(identity, []).append((n, event))
                cache[material["id"]] = indexed
            except (ValueError, UnicodeDecodeError) as exc:
                raise QualityError("INVALID_EXPLANATION_EVENTS", "事件记录无法解析，请核对原件。", 422) from exc
        matches = cache[material["id"]].get(pointer.event_id, [])
        if len(matches) != 1:
            raise QualityError("EXPLANATION_EVENT_NOT_FOUND", "事件编号不存在或重复，不能作为明确依据。", 422)
        start, selected_event = matches[0]
        count = 1
    elif pointer.check_id is not None:
        if material["kind"] != "case_record":
            raise QualityError("EXPLANATION_CHECK_NOT_FOUND", "检查项引用须使用本题的case-record.json。", 422)
        entry = snapshot[pointer.side]["cases"][cid]
        matches = [c for c in entry["case"].get("checks", []) if c.get("id") == pointer.check_id]
        if len(matches) != 1:
            raise QualityError("EXPLANATION_CHECK_NOT_FOUND", "检查项编号不存在或重复。", 422)
        location = metrics.section_ref(material, check_id=pointer.check_id)
        start, count = location["start_line"], location["line_count"]
    found = materials.excerpt(request, snapshot, cid, material["id"], start, count)
    if pointer.event_id is not None:
        found.update(event_id=pointer.event_id, display_excerpt=event_preview(selected_event))
    if pointer.check_id is not None:
        found["check_id"] = pointer.check_id
    return found


def resolve_all(request, snapshot, items):
    resolved, cache = {}, {}
    for explanation in items:
        cid = explanation.case_id
        if cid not in snapshot["case_ids"]:
            raise QualityError("EXPLANATION_CASE_NOT_FOUND", "讲解题目不在本次比较清单内。", 422)
        allowed = {"baseline", "candidate"} if explanation.focus == "comparison" else {explanation.focus}
        if any(cid not in (snapshot.get(side) or {}).get("cases", {}) for side in allowed):
            raise QualityError("EXPLANATION_SOURCE_NOT_FOUND", "讲解指定的A/B运行不存在。", 422)
        value = explanation.model_dump()
        sources = set()
        for index, paragraph in enumerate([*explanation.stages, explanation.result]):
            refs = []
            for pointer in paragraph.evidence:
                if pointer.side not in allowed:
                    raise QualityError("EXPLANATION_FOCUS_MISMATCH", "依据来源与本题讲解的A/B范围不一致。", 422)
                sources.add(pointer.side)
                refs.append(resolve_reference(request, snapshot, cid, pointer, cache))
            target = value["stages"][index] if index < len(explanation.stages) else value["result"]
            target["evidence"] = refs
        if sources != allowed:
            raise QualityError("EXPLANATION_SOURCE_NOT_FOUND", "对照讲解需要同时提供A和B的依据。", 422)
        resolved[cid] = value
    return resolved
