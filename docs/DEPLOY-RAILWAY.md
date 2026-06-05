# Деплой на Railway

Архитектура на Railway: **3 сервиса** в одном проекте.

```
┌─────────────┐     /api/* (rewrite)     ┌─────────────┐     asyncpg     ┌────────────┐
│  frontend   │ ───────────────────────▶ │   backend   │ ──────────────▶ │  Postgres  │
│  (Next.js)  │                          │  (FastAPI)  │                 │ (managed)  │
│  публичный  │ ◀─── пользователь        │             │                 │            │
└─────────────┘                          └─────────────┘                 └────────────┘
```

Браузер обращается **только к домену frontend**. Frontend проксирует `/api/*`
на backend через Next.js rewrite → cookie остаётся same-origin (без cross-site
проблем и CORS). Backend и Postgres могут быть приватными.

---

## Предусловия
- Аккаунт на [railway.com](https://railway.com).
- Репозиторий на GitHub (`git remote add origin … && git push`).
- Реальный `OPENAI_API_KEY`.

В репозитории уже подготовлено:
- `backend/railway.json` — миграции + старт uvicorn на `$PORT`.
- `backend/requirements.txt` — runtime-зависимости (без dev/test).
- `frontend/railway.json` — старт Next.js на `$PORT`.
- `frontend/next.config.mjs` — rewrite `/api/*` → `BACKEND_URL`.
- Нормализация `DATABASE_URL` (`postgres://` → `postgresql+asyncpg://`).

---

## Шаг 1. Создать проект и Postgres
1. Railway → **New Project** → **Deploy PostgreSQL** (managed Postgres).
2. Railway сам создаёт переменную `DATABASE_URL` в сервисе Postgres.

## Шаг 2. Backend-сервис
1. В проекте → **New** → **GitHub Repo** → выбрать репозиторий.
2. Открыть созданный сервис → **Settings**:
   - **Root Directory:** `backend`
   - **Config-as-code** подхватится из `backend/railway.json` автоматически
     (builder NIXPACKS, startCommand с миграциями).
3. **Variables** (вкладка Variables сервиса backend) — добавить:
   | Переменная | Значение |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (reference на сервис Postgres) |
   | `SESSION_SECRET` | длинная случайная строка (напр. `openssl rand -hex 32`) |
   | `ACCESS_CODE` | код доступа для регистрации (сообщите своим ~15 людям) |
   | `OPENAI_API_KEY` | ваш реальный ключ `sk-...` |
   | `OPENAI_GEN_MODEL` | напр. `gpt-5.4-mini` (сверьте актуальный ID в OpenAI) |
   | `OPENAI_VALIDATE_MODEL` | напр. `gpt-4o-mini` |
   | `COOKIE_SECURE` | `true` (Railway отдаёт HTTPS) |
   | `DAILY_SESSION_LIMIT` | напр. `10` |
   | `GENERATION_BATCH_SIZE` | `3` |

   > `DATABASE_URL` через reference `${{Postgres.DATABASE_URL}}` —
   > [cross-service variables](https://docs.railway.com/guides/variables). Код
   > сам переведёт `postgres://` в `postgresql+asyncpg://`.

4. **Networking** → включить **Public Networking** (Generate Domain). Запомнить
   URL, напр. `https://backend-production-xxxx.up.railway.app`.
   *(Можно оставить приватным и проксировать через приватный домен Railway —
   тогда в шаге 3 укажите внутренний URL. Для простоты начните с публичного.)*

   Миграции (`alembic upgrade head`) выполняются автоматически при каждом старте
   — таблицы создадутся при первом деплое.

## Шаг 3. Frontend-сервис
1. В проекте → **New** → **GitHub Repo** → тот же репозиторий.
2. **Settings**:
   - **Root Directory:** `frontend`
   - Config-as-code из `frontend/railway.json`.
3. **Variables** (сервис frontend):
   | Переменная | Значение |
   |---|---|
   | `NEXT_PUBLIC_API_BASE` | `/api` |
   | `BACKEND_URL` | публичный URL backend из шага 2 (`https://backend-…up.railway.app`) |

   > `NEXT_PUBLIC_API_BASE=/api` — клиент шлёт запросы на `/api/*` (свой домен).
   > `BACKEND_URL` — куда rewrite проксирует (см. `next.config.mjs`).
   > **Важно:** `NEXT_PUBLIC_*` вшивается на этапе сборки, так что после
   > изменения этой переменной нужен redeploy frontend.

4. **Networking** → **Generate Domain**. Это публичный адрес приложения, его
   дают пользователям, напр. `https://frontend-production-xxxx.up.railway.app`.

## Шаг 4. Проверка
1. Открыть домен frontend → должно редиректить на `/login`.
2. Зарегистрироваться (логин, пароль, **код доступа** = `ACCESS_CODE`).
3. Дашборд → выбрать уровень/режим → «Начать».
4. Экран подготовки покажет рост `сгенерировано N/…` → «Начать отвечать».
5. Пройти тест → «Завершить» → результаты с разбором и рекомендацией.

Если регистрация/вход не работают — проверьте в DevTools (Network), что запросы
идут на `/api/...` (свой домен) и возвращают 2xx, а в ответ приходит `Set-Cookie`.

---

## Обновления
При выбранном GitHub-деплое каждый `git push` в основную ветку триггерит
авто-деплой обоих сервисов (Railway пересобирает только изменившийся, по watch
paths можно сузить — см. [monorepo guide](https://docs.railway.com/guides/monorepo)).

## Типичные проблемы
| Симптом | Причина / решение |
|---|---|
| Backend падает на старте, `connection refused` к БД | `DATABASE_URL` не проставлен или не reference на Postgres. Проверьте Variables. |
| Фронт грузится, но вход/регистрация 404/Network error | `BACKEND_URL` неверный или frontend не пересобран после смены `NEXT_PUBLIC_API_BASE`. Redeploy frontend. |
| Вход проходит, но `/auth/me` сразу 401 (кука не ставится) | `COOKIE_SECURE=true` обязателен на HTTPS; и убедитесь, что ходите через `/api` (same-origin), а не напрямую на домен backend. |
| Генерация падает / тест `failed` | нет/неверный `OPENAI_API_KEY` или неверный `OPENAI_GEN_MODEL`. |
| «Достигнут дневной лимит» | `DAILY_SESSION_LIMIT`; провальные сессии слот возвращают. |
| Много одновременных пользователей упираются в БД | поднять пул соединений в `backend/app/db/base.py` (`create_async_engine(..., pool_size=20, max_overflow=20)`). |

## Безопасность для production
- `SESSION_SECRET` — длинный и случайный, не из примеров.
- `ACCESS_CODE` — смените на нетривиальный.
- `COOKIE_SECURE=true` — всегда на проде.
- Не коммитьте реальные ключи; задавайте их только в Railway Variables.
