"""Pinned grading requests and human decisions. No model credentials."""
from typing import Annotated, Literal
from pydantic import Field, StrictInt, model_validator
from .quality_schemas import Contract, Identifier, SkillReference, Text

Value = Annotated[StrictInt, Field(ge=0, le=1)] | Literal["unknown"]


class JudgeRequest(Contract):
    request_id: Identifier
    case_ids: list[Identifier] = Field(min_length=1, max_length=100)
    mode: Literal["archive", "mock"]
    skill: SkillReference

    @model_validator(mode="after")
    def unique_cases(self):
        if len(self.case_ids) != len(set(self.case_ids)):
            raise ValueError("案例编号不能重复")
        self.case_ids = sorted(self.case_ids)
        return self


class HumanReview(Contract):
    request_id: Identifier
    case_id: Identifier
    check_id: Identifier
    value: Value
    reason: Text
    revision: Annotated[StrictInt, Field(ge=0)]

