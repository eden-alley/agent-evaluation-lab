"""Data contracts for externally authored datasets and quality reports."""
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

Identifier = Annotated[StrictStr, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")]
Text = Annotated[StrictStr, Field(min_length=1, max_length=12000)]
ShortText = Annotated[StrictStr, Field(min_length=1, max_length=160)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    @model_validator(mode="after")
    def finite_json(self):
        json.dumps(self.model_dump(), ensure_ascii=False, allow_nan=False)
        return self


class SkillReference(Contract):
    skill_id: Identifier
    version_id: Identifier
    content_hash: Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]


class Source(Contract):
    client: ShortText
    skill_name: ShortText | None = None
    skill_version: ShortText | None = None
    skills: list[SkillReference] = Field(default_factory=list, max_length=20)


class Requirement(Contract):
    id: Identifier
    description: Text


class Case(Contract):
    case_id: Identifier
    title: ShortText
    input: dict[str, Any]
    expected: dict[str, Any] | None
    categories: list[ShortText] = Field(default_factory=list, max_length=30)
    requirement_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    grading_notes: Annotated[StrictStr, Field(max_length=12000)] = ""


class DraftInput(Contract):
    project_id: Identifier
    name: ShortText
    task_description: Text
    requirements: list[Requirement] = Field(min_length=1, max_length=100)
    cases: list[Case] = Field(min_length=1, max_length=500)
    source: Source
    base_version_id: Identifier | None = None
    request_id: Identifier

    @model_validator(mode="after")
    def references(self):
        requirement_ids = [r.id for r in self.requirements]
        case_ids = [c.case_id for c in self.cases]
        if len(set(requirement_ids)) != len(requirement_ids):
            raise ValueError("需求编号重复")
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("案例编号重复")
        for case in self.cases:
            if len(set(case.requirement_ids)) != len(case.requirement_ids) or not set(case.requirement_ids) <= set(requirement_ids):
                raise ValueError("案例的需求引用重复或不存在")
        return self


class Evidence(Contract):
    target_type: Literal["case", "requirement", "task"]
    target_id: Identifier | None = None
    field: Literal["input", "expected", "title", "grading_notes", "requirement_ids", "description", "task_description"]
    quote: Text


class Finding(Contract):
    id: Identifier
    severity: Literal["blocker", "warning", "info"]
    category: Literal["coverage", "ambiguity", "ground_truth", "duplication", "grading", "other"]
    case_ids: list[Identifier] = Field(default_factory=list, max_length=500)
    requirement_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    evidence: list[Evidence] = Field(min_length=1, max_length=30)
    explanation: Text
    suggestion: Text


class Coverage(Contract):
    requirement_id: Identifier
    status: Literal["covered", "partial", "missing", "not_assessed"]
    case_ids: list[Identifier] = Field(default_factory=list, max_length=500)
    reason: Text


class ReportInput(Contract):
    request_id: Identifier
    draft_hash: Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
    source: Source
    summary: Text
    reviewed_case_ids: list[Identifier] = Field(max_length=500)
    coverage: list[Coverage] = Field(min_length=1, max_length=100)
    findings: list[Finding] = Field(default_factory=list, max_length=500)


class DecisionInput(Contract):
    decision: Literal["approve", "reject"]
    report_id: Identifier | None = None
    note: Annotated[StrictStr, Field(max_length=4000)] = ""


def submission_contract():
    return {"schema_version": 1, "max_request_bytes": 2 * 1024 * 1024,
            "draft": DraftInput.model_json_schema(), "quality_report": ReportInput.model_json_schema(),
            "notes": ["外部 Agent 按需读取平台中用户共同设计并发布的 Skill；平台不自动编写方法内容。",
                      "使用过的已发布技能以 source.skills 记录 skill_id、version_id、content_hash。",
                      "报告中的证据必须引用本草案字段的原文；覆盖结论属于调用方判断。",
                      "request_id 对同一项目/草案去重；同一键不得提交不同内容。",
                      "确认版本须在网页审阅；MCP 不提供审批工具。"]}
