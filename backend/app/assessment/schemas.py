from pydantic import BaseModel


class SubmitAnswerRequest(BaseModel):
    question_id: str
    selected_keys: list[str]


class TopicBreakdown(BaseModel):
    topic_id: str
    answered: int
    correct: int
    accuracy: float


class QuestionReview(BaseModel):
    id: str
    seq: int
    topic_id: str
    type: str
    stem: str
    artifact_kind: str
    artifact_content: str | None
    options: list
    correct_keys: list[str]
    selected_keys: list[str]
    is_correct: bool
    explanation: str


class ResultsResponse(BaseModel):
    session_id: str
    level: str
    mode: str
    score_percent: float
    passed: bool
    total_questions: int
    answered_count: int
    topic_breakdown: list[TopicBreakdown]
    recommendation: str
    questions: list[QuestionReview]
