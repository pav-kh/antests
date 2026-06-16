from typing import Literal

from pydantic import BaseModel, model_validator


class Option(BaseModel):
    key: str
    text: str


class GeneratedQuestion(BaseModel):
    topic_id: str
    type: Literal["single", "multi"]
    stem: str
    artifact_kind: Literal["none", "code", "json", "sql", "xml", "mermaid"]
    artifact_content: str | None
    options: list[Option]
    correct_keys: list[str]
    explanation: str

    @model_validator(mode="after")
    def _check(self):
        keys = {o.key for o in self.options}
        if len(self.options) < 2:
            raise ValueError("need at least 2 options")
        if len(keys) != len(self.options):
            raise ValueError("option keys must be unique")
        if not self.correct_keys:
            raise ValueError("need at least one correct key")
        if not set(self.correct_keys).issubset(keys):
            raise ValueError("correct_keys must reference existing options")
        if self.type == "single" and len(self.correct_keys) != 1:
            raise ValueError("single-choice must have exactly one correct key")
        if self.type == "multi" and len(self.correct_keys) < 2:
            raise ValueError("multi-choice must have at least 2 correct keys")
        if self.artifact_kind != "none" and not self.artifact_content:
            raise ValueError("artifact_content required when artifact_kind != none")
        return self


class GeneratedBatch(BaseModel):
    questions: list[GeneratedQuestion]


class ValidationVerdict(BaseModel):
    valid: bool
    reason: str


class OpenQuestion(BaseModel):
    stem: str
    rubric: str
    explanation: str

    @model_validator(mode="after")
    def _check(self):
        if not self.stem.strip():
            raise ValueError("stem required")
        if not self.rubric.strip():
            raise ValueError("rubric required")
        if not self.explanation.strip():
            raise ValueError("explanation required")
        return self


class OpenBatch(BaseModel):
    questions: list[OpenQuestion]
