import json

from openai import AsyncOpenAI

from app.generation.schemas import GeneratedBatch, GeneratedQuestion, ValidationVerdict
from app.generation.topics import get_topic


class OpenAIResponseError(Exception):
    pass


def _parse_json_content(resp):
    content = resp.choices[0].message.content
    if not content:
        finish = getattr(resp.choices[0], "finish_reason", "unknown")
        raise OpenAIResponseError(f"empty response content (finish_reason={finish})")
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise OpenAIResponseError(f"non-JSON response: {e}") from e


def build_generation_system_prompt() -> str:
    return (
        "Ты — экзаменатор сертификации системных аналитиков IBS. "
        "Генерируй вопросы строго закрытого типа (single или multi choice) на русском языке. "
        "Требования к качеству:\n"
        "- Вопрос однозначен; для single-choice верен РОВНО ОДИН вариант.\n"
        "- 4 правдоподобных варианта; дистракторы — типичные ошибки из смежных тем, "
        "не случайный мусор.\n"
        "- Если нужен артефакт — встрой его в вопрос: код/JSON/SQL/XML как текст, "
        "диаграммы — как Mermaid-код (artifact_kind='mermaid'). Никаких внешних ресурсов.\n"
        "- К каждому вопросу — короткое объяснение, почему верный ответ верен.\n"
        "Верни СТРОГО JSON по заданной схеме."
    )


def _generation_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic_id": {"type": "string"},
                        "type": {"enum": ["single", "multi"]},
                        "stem": {"type": "string"},
                        "artifact_kind": {
                            "enum": ["none", "code", "json", "sql", "xml", "mermaid"]
                        },
                        "artifact_content": {"type": ["string", "null"]},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "key": {"type": "string"},
                                    "text": {"type": "string"},
                                },
                                "required": ["key", "text"],
                            },
                        },
                        "correct_keys": {"type": "array", "items": {"type": "string"}},
                        "explanation": {"type": "string"},
                    },
                    "required": [
                        "topic_id", "type", "stem", "artifact_kind",
                        "artifact_content", "options", "correct_keys", "explanation",
                    ],
                },
            }
        },
        "required": ["questions"],
    }


def _verdict_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "valid": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["valid", "reason"],
    }


class OpenAIClient:
    def __init__(self, api_key, gen_model, validate_model, _client=None):
        self.gen_model = gen_model
        self.validate_model = validate_model
        self._client = _client or AsyncOpenAI(api_key=api_key)

    async def generate_batch(self, level, mode, plan_slice):
        topic_lines = []
        for tid, count in plan_slice:
            t = get_topic(tid)
            topic_lines.append(
                f"- {count} вопрос(ов) по теме '{t.title}' "
                f"(подтемы: {', '.join(t.subtopics)})"
            )
        user_prompt = (
            f"Уровень: {level}. Сгенерируй вопросы:\n" + "\n".join(topic_lines)
        )
        resp = await self._client.chat.completions.create(
            model=self.gen_model,
            messages=[
                {"role": "system", "content": build_generation_system_prompt()},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "question_batch",
                    "schema": _generation_schema(),
                    "strict": False,
                },
            },
        )
        data = _parse_json_content(resp)
        return GeneratedBatch(**data)

    async def validate_question(self, q: GeneratedQuestion) -> ValidationVerdict:
        prompt = (
            "Проверь корректность тренировочного вопроса по сертификации СА. "
            "Верни valid=false, если: вопрос двусмысленный, помеченный верный ответ "
            "неверен, дистрактор тоже верен, или артефакт не соответствует вопросу.\n\n"
            f"ВОПРОС:\n{q.model_dump_json(indent=2)}"
        )
        resp = await self._client.chat.completions.create(
            model=self.validate_model,
            messages=[
                {"role": "system", "content": "Ты — строгий рецензент тестовых вопросов."},
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "verdict",
                    "schema": _verdict_schema(),
                    "strict": False,
                },
            },
        )
        data = _parse_json_content(resp)
        return ValidationVerdict(**data)
