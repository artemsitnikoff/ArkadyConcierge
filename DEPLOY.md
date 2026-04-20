# Деплой ArkadyConcierge

## Требования к серверу

- Docker + Docker Compose
- Git
- Сетевой доступ к `api.telegram.org`, `openrouter.ai`, `api.anthropic.com`
  (через прямой канал или прокси)

## Первоначальная установка

### 1. Клонировать репозиторий

```bash
git clone https://github.com/artemsitnikoff/ArkadyConcierge.git
cd ArkadyConcierge
```

### 2. Настроить `.env`

```bash
cp .env.example .env
nano .env
```

Обязательные переменные:

| Переменная | Откуда взять |
|---|---|
| `BOT_TOKEN` | @BotFather → новый бот → токен |
| `OPENROUTER_API_KEY` | openrouter.ai → Keys (можно тот же ключ, что в ArkadyJarvis) |
| `API_KEY` | любая длинная случайная строка — защищает `POST /api/concierge/breakdown` |
| `CLAUDE_CODE_OAUTH_TOKEN` | токен Claude CLI (см. п. 3) |
| `CLAUDE_REFRESH_TOKEN` | refresh-токен Claude CLI (см. п. 3) |

Опционально:
- `ALLOWED_USERS` — Telegram ID через запятую; пусто = открыто для всех.
- `MAX_VOICE_DURATION_SEC` — лимит длины голосового (по умолчанию 600).
- `LOG_FORMAT=json` для продакшна (агрегаторы логов).

### 3. Настроить Claude-токены

Anthropic OAuth refresh-токены **одноразовые**: после каждого обновления старый refresh-токен сразу перестаёт работать. Это значит, что **два бота с отдельными копиями `.claude_token.json`, использующих одну учётку Claude, будут обезвреживать токены друг у друга** при каждом refresh.

**Если на этом же сервере уже есть ArkadyJarvis** — просто шарь между ботами один каталог `data/`. Это уже прописано в `docker-compose.yml`:

```yaml
volumes:
  - ../ArkadyJarvis/data:/app/data
```

То есть Concierge не держит свой `.claude_token.json` — читает файл Jarvis, Jarvis его и обновляет. Свой локальный `data/` у Concierge можно удалить (или оставить пустым, он не используется).

**Если Jarvis-а на сервере нет** — инициализируй токен-файл с нуля:

1. Положи в `.env` значения из переменных `CLAUDE_CODE_OAUTH_TOKEN` и `CLAUDE_REFRESH_TOKEN` (возьми с Mac, где вы залогинены в Claude CLI).
2. Верни volume к локальной папке в `docker-compose.yml`:
   ```yaml
   volumes:
     - ./data:/app/data
   ```
3. Создай папку: `mkdir -p data`.
4. На первом старте `init_token_file` создаст `data/.claude_token.json` из `.env`.

**Если Jarvis на другом сервере/машине** — нужна отдельная Claude-подписка для Concierge. Две копии одной учётки на двух хостах будут мешать друг другу.

### 4. Запустить

```bash
docker compose up -d --build
```

Проверить:

```bash
curl localhost:8003/api/health
docker compose logs -f
```

Ответ: `{"status":"ok","version":"0.1.0"}`.

### 5. Проверить бота в Telegram

- Написать боту `/start` — должен ответить приветствием.
- Прислать текст или голосовое — в ответ придёт файл `breakdown.json` + превью.

## Обновление (деплой новой версии)

```bash
cd ~/ArkadyConcierge
git pull
docker compose up -d --build
```

Одной строкой:

```bash
cd ~/ArkadyConcierge && git pull && docker compose up -d --build
```

### Правка промпта без пересборки

`prompts/` смонтирован как volume — можно менять `concierge_breakdown.md` на сервере и перезапускать контейнер:

```bash
nano prompts/concierge_breakdown.md
docker compose restart
```

### Проверка после обновления

```bash
curl localhost:8003/api/health
docker compose logs --tail=50
docker compose ps
```

## Полезные команды

```bash
# Логи в реальном времени
docker compose logs -f

# Перезапуск без пересборки
docker compose restart

# Остановить
docker compose down

# Пересобрать и запустить
docker compose up -d --build

# Зайти в контейнер
docker compose exec concierge bash

# Посмотреть текущий токен-файл (не логировать его никуда!)
docker compose exec concierge cat /app/data/.claude_token.json

# Ручной вызов breakdown-эндпоинта
curl -X POST localhost:8003/api/concierge/breakdown \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $(grep ^API_KEY= .env | cut -d= -f2-)" \
  -d '{"text": "Нужно завести лид по ACME и созвон во вторник"}'
```

## Бэкап

```bash
# Скопировать Claude-токены с сервера (на случай сбоя refresh)
scp user@server:~/ArkadyConcierge/data/.claude_token.json \
    ./backup_claude_token_$(date +%Y%m%d).json
```

## Структура `data/`

```
data/
  .claude_token.json        # OAuth-токены Claude CLI (auto-refresh + atomic write)
```

Персистентно через Docker volume (`./data:/app/data`). При `docker compose down` данные сохраняются. Если файл случайно удалён/повреждён, первый старт пересоздаст его из `CLAUDE_CODE_OAUTH_TOKEN` + `CLAUDE_REFRESH_TOKEN` в `.env` (одноразовый refresh → после первого refresh в `.env` значения устареют, полагайся на файл).

## Наблюдаемость

- Health: `GET /api/health` → 200 + `{"status":"ok"}`.
- Docker HEALTHCHECK настроен (`curl http://localhost:8003/api/health` каждые 30 с), `docker compose ps` покажет `healthy`.
- Логи — `trace_id` на каждую операцию:
  - HTTP: `api-{uuid}` (или значение заголовка `X-Trace-Id` от клиента)
  - Telegram: `tg-{update_id}` — все строки одного апдейта с одним id
- `LOG_FORMAT=json` — по одному JSON-объекту на строку, удобно для Loki / Elastic / Datadog.

## Troubleshooting

**`401 Unauthorized` на `/api/concierge/breakdown`** — нет/неверный `X-API-Key`. Проверить `API_KEY` в `.env`.

**`503` на `/api/concierge/breakdown`** — `API_KEY` пустой. Это fail-closed: пустой ключ = эндпоинт выключен.

**`claude CLI (code 1)` в логах** — токены протухли. Скопировать свежий `data/.claude_token.json` с Mac либо обновить `CLAUDE_CODE_OAUTH_TOKEN` / `CLAUDE_REFRESH_TOKEN` в `.env` и перезапустить.

**`OpenRouter 401`** — неверный `OPENROUTER_API_KEY`.

**Бот не отвечает в Telegram** — проверить `BOT_TOKEN` и что бот не добавлен в `ALLOWED_USERS`-фильтр с другим ID: `docker compose logs | grep "Access denied"`.
