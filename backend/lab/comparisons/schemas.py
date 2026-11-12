"""External analysis contracts, independent of task grading."""
from typing import Annotated, Literal
from pydantic import Field, StrictInt, model_validator
from ..quality_schemas import Contract, Identifier, ShortText, Text, SkillReference

Outcome = Literal["improved", "regressed", "mixed", "unchanged", "insufficient", "not_covered"]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Candidate(Contract):
    kind: Literal["run", "simulation", "missing"]
    run_id: Identifier | None = None
    fixture_id: Identifier | None = None

    @model_validator(mode="after")
    def coherent(self):
        if ((self.kind == "run") != bool(self.run_id)
                or (self.kind == "simulation") != bool(self.fixture_id)):
            raise ValueError("候选来源与编号不一致。")
        return self


class Analyst(Contract):
    kind: Literal["external_agent", "manual", "offline_fixture"]
    name: ShortText
    model: ShortText | None = None


class ComparisonInput(Contract):
    request_id: Identifier
    name: ShortText
    objective: Text
    baseline_run_id: Identifier
    candidate: Candidate
    case_ids: list[Identifier] = Field(min_length=1, max_length=100)
    workflow: SkillReference
    analyst: Analyst

    @model_validator(mode="after")
    def unique_cases(self):
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("比较案例不能重复。")
        if self.candidate.run_id == self.baseline_run_id:
            raise ValueError("前后运行不能是同一记录。")
        return self


class EvidenceReference(Contract):
    material_id: Identifier
    sha256: Digest
    start_line: Annotated[StrictInt, Field(ge=1)] = 1
    line_count: Annotated[StrictInt, Field(ge=1, le=200)] = 40


class Observation(Contract):
    id: Identifier
    dimension: ShortText
    title: ShortText
    outcome: Outcome
    before: Annotated[str, Field(max_length=2000)] | None = None
    after: Annotated[str, Field(max_length=2000)] | None = None
    reason: Text
    limits: Annotated[str, Field(max_length=4000)] = ""
    evidence: list[EvidenceReference] = Field(default_factory=list, max_length=8)


class CaseAnalysisInput(Contract):
    request_id: Identifier
    revision: Annotated[StrictInt, Field(ge=0)] = 0
    summary: Text
    observations: list[Observation] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def unique_observations(self):
        if len({o.id for o in self.observations}) != len(self.observations):
            raise ValueError("观察项编号不能重复。")
        return self


class ObservationReference(Contract):
    case_id: Identifier
    observation_id: Identifier


class Finding(Contract):
    title: ShortText
    outcome: Outcome
    explanation: Text
    refs: list[ObservationReference] = Field(min_length=1, max_length=100)


class Recommendation(Contract):
    title: ShortText
    phenomenon: Text
    cause_status: Literal["hypothesis", "supported", "unresolved"]
    cause: Text
    action: Text
    priority_reason: Text
    validation: Text
    success_signals: Text
    guardrails: Text
    refs: list[ObservationReference] = Field(min_length=1, max_length=100)


class FinalReportInput(Contract):
    request_id: Identifier
    case_report_ids: list[Identifier] = Field(min_length=1, max_length=100)
    summary: Text
    findings: list[Finding] = Field(default_factory=list, max_length=100)
    recommendations: list[Recommendation] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_reports(self):
        if len(set(self.case_report_ids)) != len(self.case_report_ids):
            raise ValueError("逐题报告不能重复引用。")
        return self


def contract():
    return {"schema_version": 1, "comparison": ComparisonInput.model_json_schema(),
            "case_analysis": CaseAnalysisInput.model_json_schema(), "final_report": FinalReportInput.model_json_schema(),
            "policy": "外部分析报告不改变原评分；模拟来源由服务端标注；提交接口不启动模型。"}
