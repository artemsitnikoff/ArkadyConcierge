# ArkadyConcierge

Telegram concierge-бот: принимает задачу **текстом или голосовым сообщением**, расшифровывает голос (OpenRouter / Gemini 2.5 Pro с диаризацией), передаёт в **Claude CLI (opus)** с промптом разбивки и возвращает пользователю структурированный **JSON** для последующего создания задач в разных системах.

Архитектура скопирована с соседнего проекта `ArkadyJarvis` (FastAPI + aiogram v3, Claude CLI с OAuth auto-refresh, паттерн транскрипции голосовых из Socrates/Lead).

## Tech Stack

- Python 3.11+
- FastAPI + Uvicorn (владелец event loop)
- aiogram v3 (Telegram polling как `asyncio.create_task` в lifespan)
- Claude CLI (подписка, `CLAUDE_CODE_OAUTH_TOKEN` + `CLAUDE_REFRESH_TOKEN`)
- OpenRouter (Gemini 2.5 Pro, диаризация сегментами)

## Структура

```
app/
  main.py                      # FastAPI + lifespan + aiogram polling
  config.py                    # pydantic-settings (.env)
  logging_config.py            # JSON/plain formatters + trace_id ContextVar
  version.py
  utils.py                     # parse_json_response
  api/
    routes.py                  # GET /api/health, POST /api/concierge/breakdown
    schemas.py                 # Pydantic request/response
    middleware.py              # TraceIdMiddleware для ASGI
  bot/
    create.py                  # create_bot() + create_dispatcher()
    middlewares.py             # TraceId, Error, Access
    routers/
      start.py                 # /start, /help
      concierge.py             # Voice / text → breakdown
  services/
    ai_client.py               # Claude CLI wrapper (subprocess)
    claude_token.py            # OAuth auto-refresh (data/.claude_token.json)
    openrouter_client.py       # transcribe_voice (Gemini 2.5 Pro)
    prompts.py                 # load_prompt(name)
    concierge_service.py       # text → breakdown JSON через Claude CLI
prompts/
  voice_transcribe.md          # диаризация (копия из ArkadyJarvis)
  concierge_breakdown.md       # PLACEHOLDER — заменить своим промптом
data/
  .claude_token.json           # OAuth токены (создаётся автоматически)
tests/
  test_utils.py                # parse_json_response (12 кейсов)
  test_concierge_service.py    # сервис + моки AIClient (8)
  test_api.py                  # HTTP API, auth, validation (11)
  test_logging_config.py       # trace_id, JSON/plain форматы (9)
```

## Flow

1. Пользователь пишет `/start` → бот приветствует.
2. Пользователь шлёт:
   - **текст** → сразу в breakdown;
   - **голосовое (F.voice)** → скачивается `.ogg`, транскрибируется Gemini 2.5 Pro через OpenRouter.
3. Расшифрованный (или исходный) текст уходит в Claude CLI (opus) с промптом `prompts/concierge_breakdown.md`.
4. JSON возвращается файлом `breakdown.json` + короткое превью.

## Конфигурация (`.env`)

```
BOT_TOKEN=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=google/gemini-2.5-pro
OPENROUTER_TIMEOUT=300

CLAUDE_CLI_PATH=claude
CLAUDE_MODEL=claude-opus-4-7
CLAUDE_OAUTH_CLIENT_ID=9d1c250a-e61b-44d9-88ed-5944d1962f5e
CLAUDE_CODE_OAUTH_TOKEN=
CLAUDE_REFRESH_TOKEN=

ALLOWED_USERS=              # пусто = все; список TG id через запятую
API_KEY=                    # обязателен для POST /api/concierge/breakdown

MAX_VOICE_DURATION_SEC=600  # отсекаем длинные voice notes

LOG_LEVEL=INFO
LOG_FORMAT=plain            # plain | json
```

## Логирование

- `LOG_FORMAT=plain` — человекочитаемо: `13:17:05 [INFO] [tg-4242] concierge: ...`
- `LOG_FORMAT=json` — по одному JSON-объекту на строку: `{"ts":..., "level":..., "trace_id":..., ...}` для Loki/Elastic.
- `trace_id` проставляется автоматически:
  - HTTP: `X-Trace-Id` header читается/эхается в ответ (либо генерится `api-...`).
  - Telegram: `tg-{update_id}` — все логи одного update имеют один id.

Значения `OPENROUTER_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_REFRESH_TOKEN` можно взять из `.env` ArkadyJarvis. `BOT_TOKEN` — отдельный бот через @BotFather.

## Запуск

Локально:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env    # заполнить
uvicorn app.main:app --host 0.0.0.0 --port 8003
```

Docker:
```bash
docker compose up --build
```

Health: `curl localhost:8003/api/health`

HTTP-эндпоинт (без Telegram, требует `API_KEY`):
```bash
curl -X POST localhost:8003/api/concierge/breakdown \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your-secret-key' \
  -d '{"text": "Нужно завести лид по ACME, созвон во вторник 15:00, и задача в жиру — интеграция"}'
```

## Тесты

```bash
pip install -e ".[dev]"
pytest                      # 54 теста: utils, service, api, logging, middlewares, escape
```

Тесты изолированы от реального Telegram и Claude CLI (фейковые клиенты в `tests/conftest.py`).

## Деплой

Инструкция по продакшн-деплою — `DEPLOY.md`. Коротко:
1. `git clone` + `cp .env.example .env` → заполнить `BOT_TOKEN`, `OPENROUTER_API_KEY`, `API_KEY`, `CLAUDE_*`.
2. `scp data/.claude_token.json` с Mac (или задать токены в `.env`).
3. `docker compose up -d --build`.
4. Health: `curl localhost:8003/api/health`.

Обновление: `git pull && docker compose up -d --build`.

## Промпт разбивки

`prompts/concierge_breakdown.md` — сейчас **заглушка** с временной схемой. Замени на финальный промпт; если в нём есть `{text}` — пользовательский ввод подставится туда, иначе добавится отдельным блоком в конец.

Ответ AI должен быть валидным JSON (можно в ```json```-фенсе) — парсер `utils.parse_json_response` вытащит объект.
