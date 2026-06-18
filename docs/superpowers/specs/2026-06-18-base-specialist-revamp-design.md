# Переработка base/specialist: 53 вопроса, 120 мин, без артефактов, тематические открытые — Design

**Дата:** 2026-06-18
**Статус:** Одобрено пользователем
**Контекст:** Уровни `base` (80 закрытых, 2 открытых, 120 мин) и `specialist` (120 закрытых, 2 открытых, 180 мин) переделываются. Вопросы с артефактами (код/SQL/JSON/XML/Mermaid) на этих уровнях «потеряли смысл» и убираются. Состав открытых вопросов меняется: 3 открытых = 1 случайный seed + 2 LLM по конкретным темам. Уровень `ba` НЕ затрагивается.

---

## Цель

base и specialist становятся 53-вопросными (50 закрытых + 3 открытых), 120 мин, только текстовые закрытые вопросы (без артефактов). Три открытых вопроса имеют заданный состав: 1 случайный seed-кейс + 1 LLM-вопрос по теме «Интеграция» + 1 LLM-вопрос по теме «Системное мышление».

## Решения (зафиксированы с пользователем)

1. **Объём:** base/specialist = 50 закрытых + 3 открытых = 53. `LEVEL_TOTALS`: base 80→50, specialist 120→50, ba 40 (без изм).
2. **Время:** 120 мин на обоих. `LEVEL_TIME_LIMITS`: base 120 (без изм), specialist 180→120, ba 90 (без изм).
3. **Открытые — число per-level:** base/specialist = 3, ba = 2.
4. **Артефакты:** убрать ПОЛНОСТЬЮ на base/specialist (0% — только текст). ba без изменений (Mermaid на modeling/process_analysis).
5. **Состав 3 открытых (base/specialist):** 1 случайный seed из {БА-1, БА-2} (детерминированно по session.id) + 1 LLM по теме «Интеграция» + 1 LLM по теме «Системное мышление». При сбое LLM на тематическом вопросе — мягкая деградация (вопрос пропускается, открытых меньше 3; finish не ломается).
6. **Генерация тематических открытых:** отдельный метод `generate_open_on_topic(topic_title, hint)` (отдельно от пулового `generate_open_questions`).
7. **base vs specialist различия:** сохраняются разные веса тем и пороги (70%/75%). Меняются только объём/время/артефакты/состав открытых.

## Архитектура

Всё — Python-константы и логика генератора. Миграций БД нет (`total_questions`/`time_limit_sec` пишутся в сессию при создании; старые сессии не затрагиваются).

### Поток сборки открытых вопросов (генератор)

Текущая логика (единая для всех уровней): пул = seed + LLM-кандидаты, сэмплим `OPEN_PER_SESSION`. Меняется на per-level:

```
open_count = LEVEL_OPEN_COUNT.get(level, 2)   # base/specialist=3, ba=2
if level in ("base", "specialist"):
    # Заданный состав: 1 случайный seed + 2 тематических LLM
    chosen = []
    rng = random.Random(str(session.id))
    chosen.append(rng.choice(SEED_OPEN_QUESTIONS))            # 1 случайный seed
    for topic_title, hint in OPEN_TOPICS_BASE_SPEC:           # «Интеграция», «Системное мышление»
        try:
            chosen.append(await client.generate_open_on_topic(topic_title, hint))
        except Exception:
            logger.exception(...)                            # мягкая деградация: пропускаем
else:
    # ba (без изменений): пул seed + LLM, сэмплим open_count
    pool = list(SEED_OPEN_QUESTIONS)
    try: pool += await client.generate_open_questions(level, count=LLM_OPEN_CANDIDATES)
    except Exception: logger.exception(...)
    chosen = _sample_open_pool(pool, open_count, rng)
# записать chosen как open-вопросы (seq после закрытых, generated_count += len(chosen))
```

## Компоненты

### 1. `backend/app/generation/planner.py`

- `LEVEL_TOTALS = {"base": 50, "specialist": 50, "ba": 40}`.
- `LEVEL_MULTI_TARGET` без изменений (`{"ba": 0.7}`).

### 2. `backend/app/generation/service.py`

- `LEVEL_TIME_LIMITS = {"base": 120 * 60, "specialist": 120 * 60, "ba": 90 * 60}`.

### 3. `backend/app/generation/generator.py`

- `OPEN_PER_SESSION = 2` (константа) заменяется на:
  ```python
  LEVEL_OPEN_COUNT = {"base": 3, "specialist": 3, "ba": 2}
  DEFAULT_OPEN_COUNT = 2
  ```
- Артефакты off на base/specialist: расширить `LEVEL_ARTIFACT_TOPICS`:
  ```python
  LEVEL_ARTIFACT_TOPICS = {"ba": {"modeling", "process_analysis"}, "base": set(), "specialist": set()}
  ```
  Пустой набор → `topic_id in artifact_topics` всегда False → `want_artifact` никогда не True → 0 артефактов. Квота/кап (15%/20%) становятся неактивными (ни один артефакт не запрашивается). Никакого нового флага.
- Темы тематических открытых:
  ```python
  # (topic_title, hint) для тематических открытых на base/specialist.
  OPEN_TOPICS_BASE_SPEC = [
      ("Описание интеграции",
       "Опиши, как ты подойдёшь к описанию интеграции между системами: какие "
       "требования к интеграции собрать, какие уточняющие вопросы задать "
       "(формат, протокол, объёмы, SLA, ошибки), какие критерии приёмки "
       "зафиксировать и какие риски/ошибки учесть (сбои, задержки, "
       "недоступность внешней системы, идемпотентность, ретраи)."),
      ("Системное мышление",
       "Кейс на системное мышление: декомпозиция задачи, выявление связей и "
       "зависимостей между компонентами, границы системы, причинно-следственные "
       "связи, целостный взгляд на проблему вместо локального."),
  ]
  ```
- Per-level сборка открытых, как в потоке выше. `_sample_open_pool` остаётся для ba.

### 4. `backend/app/generation/openai_client.py`

- Новый метод `generate_open_on_topic(self, topic_title: str, hint: str) -> OpenQuestion`:
  - Промпт: «Сгенерируй 1 открытый вопрос-кейс по теме "{topic_title}". {hint}» + формат реального экзамена (case/task/focus/criteria_visible/rubric/explanation), сборка `stem` через `build_open_stem`, скрытый `rubric`.
  - strict json_schema на один объект (не batch) с теми же 7 полями, что у пулового метода. Ретраи (3) и `OpenAIResponseError`, как в существующих методах.
  - Возвращает один `OpenQuestion`.
- `generate_open_questions` (пуловый, для ba) — без изменений.

## Обработка ошибок / совместимость

- **Артефакты off:** пустой `artifact_topics` гарантирует 0 артефактов; кап-логика безвредна (downgrade неактивен).
- **Сбой LLM на тематическом открытом:** ловится, логируется, вопрос пропускается → открытых < 3. Открытые — бонусная секция; finish считает скоринг по закрытым; пустой/неотвеченный открытый уже обрабатывается (заглушка).
- **Сбой ba-пула:** без изменений (fallback на seed).
- **Старые сессии:** не затрагиваются (объём/время записаны в БД при создании). Старые base на 80 вопросов до-проходятся.
- **Фронтенд:** 53 рендерится сам через `maxSeq`; счётчики (фикс 42/40) уже консистентны. Никаких правок фронта.
- **Миграций нет.**

## Тестирование

- `LEVEL_TOTALS`: base==50, specialist==50, ba==40.
- `LEVEL_TIME_LIMITS`: specialist==7200 (было 10800), base==7200, ba==5400.
- `LEVEL_OPEN_COUNT`: base/specialist==3, ba==2; `.get("ba",2)`==2.
- `LEVEL_ARTIFACT_TOPICS["base"]==set()` и `["specialist"]==set()`; ba неизменно.
- `plan_exam("base")`/`("specialist")`: сумма==50, 10 тем (каждая ≥1); base/specialist веса/пороги не изменены (regression).
- `generate_open_on_topic` (мок-клиент): возвращает 1 OpenQuestion; stem собран через build_open_stem; rubric отдельно, не в stem; промпт содержит topic_title и hint.
- Генератор base/specialist: ровно 3 открытых = 1 seed (из SEED_OPEN_QUESTIONS) + 2 тематических (по OPEN_TOPICS_BASE_SPEC); 50 закрытых; 0 артефактов (все closed artifact_kind=="none"); generated_count == 50+3.
- Генератор при сбое тематического LLM: открытых 1–2 (мягкая деградация), сессия ready, finish работает.
- Генератор ba: 40 закрытых + 2 открытых (regression, без изменений).
- Живой smoke: base → 50 закрытых (0 артефактов) + 3 открытых (1 БА-кейс + интеграция + системное мышление по темам), 120 мин; specialist аналогично; ba не затронут.

## Вне scope (YAGNI)

- Изменение весов тем base/specialist или порогов.
- Тематические открытые для ba (ba оставляет пуловую логику).
- Фиксированные seed-кейсы для «интеграции»/«системного мышления» (решено: LLM по теме).
- Гарантия ровно 3 открытых при полном сбое LLM (мягкая деградация достаточна).
- Изменение `LLM_OPEN_CANDIDATES` (используется только для ba-пула).
