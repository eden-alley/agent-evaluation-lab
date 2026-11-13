"""Small analyst document, with a separate program-owned transport envelope."""
from typing import Literal
from pydantic import Field, StrictInt
from ..quality_schemas import Contract, Identifier, ShortText, Text, SkillReference
from .schemas import Digest


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


class ReviewSubmission(Contract):
    request_id: Identifier
    packet_hash: Digest
    base_report_id: Identifier | None = None
    case_revisions: dict[Identifier, StrictInt]
    workflow: SkillReference
    origin: Literal["external_agent", "manual", "offline_program"]
    analysis: Analysis
