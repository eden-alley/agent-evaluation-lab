"""Small analyst document, with a separate program-owned transport envelope."""
from typing import Literal
from pydantic import Field, StrictInt, model_validator
from ..quality_schemas import Contract, Identifier, ShortText, Text, SkillReference
from .schemas import Digest
from .explanations import CaseExplanation, ExplanationEvidence


class AdviceEvidence(ExplanationEvidence):
    case_id: Identifier


class ReviewPreparation(Contract):
    explain_case_ids: list[Identifier] | None = Field(default=None, min_length=1, max_length=100)
    review_scope: Literal['focused', 'formal_batch'] = 'focused'


class Advice(Contract):
    title: ShortText
    metric_id: Identifier
    case_ids: list[Identifier] = Field(min_length=1, max_length=100)
    known_mechanism: Text = '尚未核查已有机制。'
    gap: Text
    cause_status: Literal["hypothesis", "unresolved"] = "unresolved"
    cause: Text = '原因尚未确定。'
    action: Text
    priority_reason: Text | None = None
    validation: Text
    success_signals: Text = '未单独提供；以验证方案为准。'
    guardrails: Text = '未单独提供。'
    evidence: list[AdviceEvidence] = Field(default_factory=list, max_length=30)


class Analysis(Contract):
    summary: Text
    recommendations: list[Advice] = Field(default_factory=list, max_length=3, description='仅正式整批评测可附有据建议；小范围验证省略或为空。没有建议不要求解释原因。')
    limitations: list[ShortText] = Field(default_factory=list, max_length=12)
    case_explanations: list[CaseExplanation] = Field(default_factory=list, max_length=100)
    no_recommendation_reason: ShortText | None = Field(default=None, description='兼容旧输入的可选说明，不是提交要求。')

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
    delivery_id: Identifier | None = None
    origin: Literal["external_agent", "manual", "offline_program"]
    analysis: Analysis
