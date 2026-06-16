import json
import re

from openai import AsyncOpenAI

from app.generation.schemas import GeneratedBatch, GeneratedQuestion, ValidationVerdict
from app.generation.topics import get_topic

# Matches a fenced code block (```lang ... ```), e.g. ```mermaid ... ``` — used
# to scrub artifact text the model sometimes duplicates into the question stem.
_FENCE_RE = re.compile(r"```[\w-]*.*?```", re.DOTALL)


def _strip_artifact_from_stem(stem: str) -> str:
    """Remove any fenced artifact block the model leaked into the stem.

    The artifact belongs only in artifact_content; if it also appears in the
    stem (raw ``` block), the user would see it twice — once as plain text and
    once rendered. Strip fenced blocks and a possible dangling fence/leftover.
    """
    cleaned = _FENCE_RE.sub("", stem)
    # Drop a leftover opening fence with no closing one (truncated leak).
    cleaned = re.sub(r"```[\w-]*.*$", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


def _stem_reveals_answer(q) -> bool:
    """Heuristic: does the stem give away the correct answer?

    A question is "self-answering" when its formulation already contains the
    correct answer text (e.g. stem says "на диаграмме последовательностей…" and
    the answer IS "Диаграмма последовательностей"). We flag conservatively to
    avoid over-dropping: only when the full answer phrase (>=8 chars) appears
    verbatim, or a distinctive 2-word head of the answer (>=8 chars) appears as
    a substring in the stem.
    """
    stem = q.stem.lower()
    for opt in q.options:
        if opt.key not in q.correct_keys:
            continue
        ans = opt.text.lower().strip()
        # full answer phrase (>=8 chars) appears verbatim in the stem
        if len(ans) >= 8 and ans in stem:
            return True
        # distinctive multi-word head (first 2 content words, >=8 chars) in stem
        words = [w for w in ans.replace("-", " ").split() if len(w) > 4]
        if len(words) >= 2:
            phrase = " ".join(words[:2])
            if len(phrase) >= 8 and phrase in stem:
                return True
    return False


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
        "- Артефакт (если он нужен) кладётся ТОЛЬКО в поле artifact_content; "
        "дублировать его в поле stem ЗАПРЕЩЕНО. stem — это лишь формулировка вопроса; "
        "он может ссылаться на артефакт словами («на диаграмме…», «в запросе ниже…»), "
        "но НЕ должен содержать сам код, разметку или ограждения ```.\n"
        "- Допустимые типы артефактов для системного аналитика: SQL-запрос "
        "(artifact_kind='sql'), JSON (json), XML (xml), диаграмма в синтаксисе "
        "Mermaid (mermaid). НЕ используй код на языках программирования "
        "(Python, JavaScript, Java и т.п.) — это тест для аналитиков, не программистов.\n"
        "- Вопрос НЕ должен содержать в формулировке (stem) сам правильный ответ "
        "или его тип. Например, если правильный ответ — «диаграмма последовательностей», "
        "то в stem НЕЛЬЗЯ писать «на диаграмме последовательностей…» — это выдаёт ответ. "
        "Описывай артефакт нейтрально («на приведённой диаграмме», «в показанном "
        "сообщении/JSON ниже»), не называя тип, который требуется определить.\n"
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

    async def generate_batch(
        self, level, mode, plan_slice, avoid_stems=None, want_artifact=False
    ):
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
        if avoid_stems:
            avoid_block = "\n".join(f"- {st}" for st in avoid_stems[:40])
            user_prompt += (
                "\n\nНЕ ПОВТОРЯЙ и не перефразируй эти уже созданные вопросы — "
                "сгенерируй ДРУГИЕ, по другим аспектам темы:\n" + avoid_block
            )
        if want_artifact:
            user_prompt += (
                "\n\nВ КАЖДОМ вопросе этого набора добавь артефакт: SQL-запрос, "
                "JSON, XML или Mermaid-диаграмму (НЕ код на языках программирования). "
                "Артефакт помещай ТОЛЬКО в поле artifact_content (artifact_kind "
                "укажи sql/json/xml/mermaid); в stem его НЕ дублируй и ограждения "
                "``` в stem не ставь.\n"
                "ГЛАВНОЕ: вопрос должен требовать АНАЛИЗА СОДЕРЖИМОГО артефакта, а не "
                "узнавания его типа. ЗАПРЕЩЕНЫ вопросы вида «что это за тип "
                "диаграммы/формата?», «в каком формате представлены данные?», «как "
                "называется эта нотация?» — ответ на них виден из самого артефакта.\n"
                "ХОРОШИЕ вопросы заставляют РАЗОБРАТЬСЯ в артефакте, например: найти "
                "ошибку или проблему в SQL-запросе; определить, что вернёт запрос; "
                "понять связь/кратность/поток на диаграмме; найти или "
                "проинтерпретировать конкретное поле во вложенном JSON/XML; выбрать "
                "корректное изменение артефакта. Чтобы ответить, нужно прочитать и "
                "понять содержимое, а не просто взглянуть на форму.\n"
                "Тип выбирай по теме: данные — SQL, интеграции — JSON/XML, "
                "моделирование/процессы — Mermaid-диаграмма.\n"
                "Для Mermaid соблюдай синтаксис строго, иначе диаграмма не "
                "отрисуется: идентификаторы узлов — латиницей (A, B, Step1); "
                "русский текст — только ВНУТРИ подписи; если в подписи есть скобки, "
                "кавычки, запятые или двоеточия — бери подпись в кавычки, напр. "
                "A[\"Проверка (условий)\"]. Используй простые проверенные типы: "
                "flowchart TD/LR, sequenceDiagram, classDiagram, stateDiagram-v2. "
                "Не используй экзотические возможности и не оставляй незакрытых "
                "скобок."
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
        batch = GeneratedBatch(**data)
        # Defensive: strip any artifact text the model leaked into the stem so it
        # is never shown twice (raw in the question + rendered as the artifact).
        for q in batch.questions:
            q.stem = _strip_artifact_from_stem(q.stem)
        # Drop self-answering questions (stem reveals the answer). The generator
        # regenerates to refill the count, so dropping a few here is safe.
        batch.questions = [q for q in batch.questions if not _stem_reveals_answer(q)]
        return batch

    async def validate_question(self, q: GeneratedQuestion) -> ValidationVerdict:
        prompt = (
            "Оцени, ПРИГОДЕН ЛИ вопрос для тренировочного теста по сертификации СА. "
            "По умолчанию вопрос ПРИГОДЕН (valid=true). Верни valid=false ТОЛЬКО при "
            "явном, фактическом дефекте:\n"
            "- помеченный верный ответ фактически НЕВЕРЕН; или\n"
            "- дистрактор НА САМОМ ДЕЛЕ является полностью правильным ответом "
            "(не «может показаться», не «при некоторой трактовке», а объективно верен); или\n"
            "- формулировка вопроса (stem) уже содержит правильный ответ или прямо "
            "называет его тип, так что отвечать не нужно (вопрос «сам себя выдаёт»); или\n"
            "- к вопросу приложен артефакт (SQL/JSON/XML/диаграмма), но вопрос "
            "сводится к УЗНАВАНИЮ типа/формата артефакта («что это за диаграмма?», "
            "«в каком формате данные?»), а не к АНАЛИЗУ его содержимого — ответ "
            "очевиден из самого вида артефакта; или\n"
            "- вопрос бессмысленный/непонятный или артефакт не соответствует вопросу.\n\n"
            "ВАЖНО: дистракторы ОБЯЗАНЫ быть правдоподобными, но неверными — это норма, "
            "а не дефект. Не отклоняй вопрос за то, что дистрактор «звучит убедительно» "
            "или «можно интерпретировать как верный». Сомневаешься — ставь valid=true.\n\n"
            f"ВОПРОС:\n{q.model_dump_json(indent=2)}"
        )
        resp = await self._client.chat.completions.create(
            model=self.validate_model,
            messages=[
                {"role": "system",
                 "content": "Ты — рецензент тестовых вопросов. Отклоняй только явно "
                            "дефектные вопросы; правдоподобные неверные дистракторы — это норма."},
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

    async def recommend(self, level: str, weak_topics: list[tuple[str, float]]) -> str:
        lines = [
            f"- {get_topic(tid).title}: {round(acc * 100)}% верных"
            for tid, acc in weak_topics
        ]
        prompt = (
            "Дай студенту краткую персональную рекомендацию по подготовке к "
            f"сертификации (уровень {level}). Слабые темы (точность ниже порога):\n"
            + "\n".join(lines)
            + "\n\nДля каждой слабой темы — что повторить и на что обратить внимание. "
            "Пиши по-русски, дружелюбно и конкретно, без воды."
        )
        resp = await self._client.chat.completions.create(
            model=self.gen_model,
            messages=[
                {"role": "system",
                 "content": "Ты — наставник по подготовке системных аналитиков."},
                {"role": "user", "content": prompt},
            ],
        )
        content = resp.choices[0].message.content
        if not content:
            raise OpenAIResponseError("empty recommendation content")
        return content
