import json
import re

from openai import AsyncOpenAI

from app.generation.schemas import (
    GeneratedBatch,
    GeneratedQuestion,
    OpenQuestion,
    ValidationVerdict,
)
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


def build_open_stem(
    topic_title: str, case: str, task: str, focus: str, criteria_visible: str
) -> str:
    """Assemble the full visible stem of an open question.

    Single source of the open-question format — used by both the seed module
    and the LLM generation path so fixed and generated questions look identical.
    The blocks are newline-separated; the frontend renders the stem with
    white-space: pre-line so they appear on separate labelled lines, matching
    the real BA certification layout.
    """
    return (
        "Ответ: до 2500 знаков с пробелами; достаточно тезисного, "
        "структурированного ответа.\n"
        f"Тип: открытый кейс. {topic_title.strip()}\n\n"
        f"{case.strip()}\n\n"
        f"Задание: {task.strip()}\n"
        f"Фокус ответа: {focus.strip()}\n"
        f"Критерии оценки: {criteria_visible.strip()}"
    )


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
        self, level, mode, plan_slice, avoid_stems=None, want_artifact=False,
        multi_ratio=None, mermaid_only=False,
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
            if mermaid_only:
                user_prompt += (
                    "\n\nВ КАЖДОМ вопросе этого набора добавь артефакт — "
                    "Mermaid-диаграмму (процесс/модель). Артефакт помещай ТОЛЬКО в "
                    "поле artifact_content (artifact_kind='mermaid'); в stem его НЕ "
                    "дублируй и ограждения ``` в stem не ставь. НЕ используй SQL, "
                    "форматы данных (JSON/XML) или код — только диаграмму.\n"
                    "ГЛАВНОЕ: вопрос должен требовать АНАЛИЗА СОДЕРЖИМОГО диаграммы "
                    "(понять поток/связь/кратность/состояния), а не узнавания её типа. "
                    "ЗАПРЕЩЕНЫ вопросы «что это за диаграмма?».\n"
                    "Для Mermaid соблюдай синтаксис строго, иначе диаграмма не "
                    "отрисуется: идентификаторы узлов — латиницей (A, B, Step1); "
                    "русский текст — только ВНУТРИ подписи; если в подписи есть скобки, "
                    "кавычки, запятые или двоеточия — бери подпись в кавычки, напр. "
                    "A[\"Проверка (условий)\"]. Используй простые проверенные типы: "
                    "flowchart TD/LR, sequenceDiagram, classDiagram, stateDiagram-v2. "
                    "Не используй экзотические возможности и не оставляй незакрытых "
                    "скобок."
                )
            else:
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
        if multi_ratio:
            pct = round(multi_ratio * 100)
            user_prompt += (
                f"\n\nКРИТИЧЕСКИ ВАЖНО про тип вопросов: БОЛЬШИНСТВО — не менее {pct}% "
                "вопросов в этом наборе — ДОЛЖНЫ быть типа multi (несколько верных "
                "вариантов: обычно 2–3 правильных из 4–5, в correct_keys перечисли ВСЕ "
                "верные). Это жёсткое требование, а не пожелание. Только меньшая часть "
                "может быть single (ровно один верный). НЕ делай почти все вопросы "
                "single. Multi-вопросы должны быть честными: несколько вариантов "
                "действительно корректны, а не искусственно добавлены."
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
            "- помеченный верный ответ ПРОТИВОРЕЧИТ тому, что реально изображено/"
            "записано в артефакте. ВНИМАТЕЛЬНО сверь ответ с содержимым: если "
            "вопрос про «проблему/ошибку» на диаграмме, а на самой диаграмме этой "
            "проблемы НЕТ (например, ответ говорит про исключающий шлюз, а на схеме "
            "стоит параллельный, и он там корректен) — это дефект, valid=false; или\n"
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

    async def generate_open_questions(
        self, level: str, count: int = 3
    ) -> list[OpenQuestion]:
        prompt = (
            f"Сгенерируй {count} ОТКРЫТЫХ вопроса-кейса для сертификации системного "
            f"аналитика (уровень {level}), в формате реального экзамена. Каждый — "
            "практическая ситуация, требующая развёрнутого текстового ответа (НЕ "
            "выбор варианта), объёмом ответа до 2500 знаков с пробелами. Для "
            "КАЖДОГО верни структурные части:\n"
            "- topic_title: короткая тема кейса (напр. «От бизнес-проблемы к "
            "требованиям»);\n"
            "- case: описание практической ситуации (2–4 предложения);\n"
            "- task: что именно сделать, с числовыми рамками (напр. «до 5 "
            "уточняющих вопросов, до 4 требований…»);\n"
            "- focus: на чём сфокусироваться и что НЕ нужно делать;\n"
            "- criteria_visible: краткие критерии оценки через точку с запятой "
            "(показываются студенту);\n"
            "- rubric: ПОДРОБНЫЕ скрытые критерии для проверяющего — что обязательно "
            "должно быть в сильном ответе (студенту НЕ показывается, должен быть "
            "детальнее, чем criteria_visible);\n"
            "- explanation: краткий разбор, что отличает сильный ответ (показывается "
            "на результатах).\n"
            "Пиши по-русски. Верни СТРОГО JSON по схеме."
        )
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "open_batch",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "questions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "topic_title": {"type": "string"},
                                    "case": {"type": "string"},
                                    "task": {"type": "string"},
                                    "focus": {"type": "string"},
                                    "criteria_visible": {"type": "string"},
                                    "rubric": {"type": "string"},
                                    "explanation": {"type": "string"},
                                },
                                "required": [
                                    "topic_title", "case", "task", "focus",
                                    "criteria_visible", "rubric", "explanation",
                                ],
                            },
                        }
                    },
                    "required": ["questions"],
                },
                "strict": True,
            },
        }
        last_err: Exception | None = None
        for _attempt in range(3):
            try:
                resp = await self._client.chat.completions.create(
                    model=self.gen_model,
                    messages=[
                        {"role": "system",
                         "content": "Ты — экзаменатор сертификации системных аналитиков IBS."},
                        {"role": "user", "content": prompt},
                    ],
                    response_format=response_format,
                )
                data = _parse_json_content(resp)
                return [
                    OpenQuestion(
                        stem=build_open_stem(
                            topic_title=item["topic_title"],
                            case=item["case"],
                            task=item["task"],
                            focus=item["focus"],
                            criteria_visible=item["criteria_visible"],
                        ),
                        rubric=item["rubric"],
                        explanation=item["explanation"],
                    )
                    for item in data["questions"]
                ]
            except Exception as e:  # noqa: BLE001 — retry on any failure, raise the last
                last_err = e
        assert last_err is not None  # loop ran ≥1 time, so this is always bound
        raise last_err

    async def generate_open_on_topic(
        self, topic_title: str, hint: str
    ) -> OpenQuestion:
        prompt = (
            f"Сгенерируй 1 ОТКРЫТЫЙ вопрос-кейс по теме «{topic_title}» для "
            "сертификации системного аналитика, в формате реального экзамена — "
            "практическая ситуация, требующая развёрнутого текстового ответа (НЕ "
            "выбор варианта), объёмом ответа до 2500 знаков с пробелами.\n"
            f"Ориентир по содержанию: {hint}\n"
            "Верни структурные части:\n"
            "- topic_title: короткая тема кейса (используй данную тему);\n"
            "- case: описание практической ситуации (2–4 предложения);\n"
            "- task: что именно сделать, с числовыми рамками где уместно;\n"
            "- focus: на чём сфокусироваться и что НЕ нужно делать;\n"
            "- criteria_visible: краткие критерии оценки через точку с запятой "
            "(показываются студенту);\n"
            "- rubric: ПОДРОБНЫЕ скрытые критерии для проверяющего (студенту НЕ "
            "показывается, детальнее criteria_visible);\n"
            "- explanation: краткий разбор, что отличает сильный ответ.\n"
            "Пиши по-русски. Верни СТРОГО JSON по схеме."
        )
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "open_one",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "topic_title": {"type": "string"},
                        "case": {"type": "string"},
                        "task": {"type": "string"},
                        "focus": {"type": "string"},
                        "criteria_visible": {"type": "string"},
                        "rubric": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": [
                        "topic_title", "case", "task", "focus",
                        "criteria_visible", "rubric", "explanation",
                    ],
                },
                "strict": True,
            },
        }
        last_err: Exception | None = None
        for _attempt in range(3):
            try:
                resp = await self._client.chat.completions.create(
                    model=self.gen_model,
                    messages=[
                        {"role": "system",
                         "content": "Ты — экзаменатор сертификации системных аналитиков IBS."},
                        {"role": "user", "content": prompt},
                    ],
                    response_format=response_format,
                )
                item = _parse_json_content(resp)
                return OpenQuestion(
                    stem=build_open_stem(
                        topic_title=item["topic_title"],
                        case=item["case"],
                        task=item["task"],
                        focus=item["focus"],
                        criteria_visible=item["criteria_visible"],
                    ),
                    rubric=item["rubric"],
                    explanation=item["explanation"],
                )
            except Exception as e:  # noqa: BLE001 — retry on any failure, raise the last
                last_err = e
        assert last_err is not None  # loop ran ≥1 time, so this is always bound
        raise last_err

    async def judge_open(self, stem: str, rubric: str, answer: str) -> str:
        prompt = (
            "Оцени ответ студента на открытый вопрос по сертификации СА и дай "
            "развёрнутую обратную связь (что хорошо, что упущено, как улучшить). "
            "Опирайся на критерии (rubric). НЕ ставь балл — только текст. "
            "Пиши по-русски, конкретно и доброжелательно.\n\n"
            f"ВОПРОС:\n{stem}\n\nКРИТЕРИИ (rubric):\n{rubric}\n\n"
            f"ОТВЕТ СТУДЕНТА:\n{answer}"
        )
        resp = await self._client.chat.completions.create(
            model=self.validate_model,
            messages=[
                {"role": "system",
                 "content": "Ты — наставник, оценивающий ответы системных аналитиков."},
                {"role": "user", "content": prompt},
            ],
        )
        content = resp.choices[0].message.content
        if not content:
            raise OpenAIResponseError("empty judge content")
        return content

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
