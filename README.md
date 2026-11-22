# NIM to OpenAI Router

Простой HTTP-роутер на FastAPI, который принимает запросы NVIDIA NIM-стиля к `/v1/chat/completions` и проксирует их в OpenAI-compatible upstream.

## Что делает

- Принимает `POST /v1/chat/completions` (JSON, non-streaming).
- Проверяет базовые поля: `model`, `messages`.
- Отклоняет `stream=true` (в этой версии streaming не поддерживается).
- Пересылает запрос в `{OPENAI_BASE_URL}/chat/completions`.
- Использует `OPENAI_API_KEY` для upstream, либо прокидывает входящий `Authorization`, если upstream-ключ не задан.
- Возвращает статус и JSON-ответ upstream как есть.

> NVIDIA NIM Chat Completions API в основном OpenAI-compatible, поэтому роутер работает как прозрачный адаптер/прокси с конфигурируемым upstream.

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Отредактируйте .env: OPENAI_BASE_URL, OPENAI_API_KEY

uvicorn app:app --host 0.0.0.0 --port 8000
```

Или:

```bash
python app.py
```

## Конфигурация

Переменные окружения (см. `.env.example`):

| Переменная | По умолчанию | Описание |
|---|---|---|
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Базовый URL OpenAI-compatible upstream |
| `OPENAI_API_KEY` | пусто | API key для upstream. Если пусто, используется входящий `Authorization` |
| `INBOUND_API_KEY` | пусто | Если задан, роутер требует `Authorization: Bearer <INBOUND_API_KEY>` от клиента |
| `HOST` | `0.0.0.0` | Хост сервера |
| `PORT` | `8000` | Порт сервера |
| `UPSTREAM_TIMEOUT` | `120` | Таймаут upstream-запроса в секундах |

## Пример запроса

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $INBOUND_API_KEY" \
  -d '{
    "model": "meta/llama-3.1-8b-instruct",
    "messages": [
      {"role": "user", "content": "Привет! Кто ты?"}
    ],
    "temperature": 0.2
  }'
```

## Health check

```bash
curl http://localhost:8000/health
```

Ответ:

```json
{"status":"ok"}
```

## Ограничения текущей версии

- Только `POST /v1/chat/completions`.
- Без streaming (`stream=true` возвращает `400`).
- Без трансформации специфичных полей моделей; payload проксируется прозрачно.
