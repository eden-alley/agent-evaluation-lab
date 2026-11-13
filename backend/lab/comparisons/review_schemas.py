"""Small analyst document, with a separate program-owned transport envelope."""
from typing import Literal
from pydantic import Field, StrictInt, model_validator
from ..quality_schemas import Contract, Identifier, ShortText, Text, SkillReference
from .schemas import Digest
from .explanations import CaseExplanation


class Advice(Contract):
    title: ShortText
    metric_id: Identifier
    case_ids: list[Identifier] = Field(min_length=1, max_length=100)
    known_mechanism: Text
    gap: Text
    cause_status: Literal["hypothesis", "unresolved"] = "hypothesis"
    cause: Text
    action: Text
    validation: Text
    success_signals: Text
    guardrails: Text


class Analysis(Contract):
    summary: Text
    recommendations: list[Advice] = Field(default_factory=list, max_length=3)
    limitations: list[ShortText] = Field(default_factory=list, max_length=12)
    case_explanations: list[CaseExplanation] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_explanations(self):
        if len({e.case_id for e in self.case_explanations}) != len(self.case_explanations):
            raise ValueError("同一份报告不能重复讲解同一道题。")
        return self


class ReviewSubmission(Contract):
    request_id: Identifier
    packet_hash: Digest
    base_report_id: Identifier | None = None
    case_revisions: dict[Identifier, StrictInt]
    workflow: SkillReference
    origin: Literal["external_agent", "manual", "offline_program"]
    analysis: Analysis
