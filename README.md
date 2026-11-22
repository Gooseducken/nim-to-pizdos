# NVIDIA NIM → OpenAI-compatible прокси для JanitorAI

Простой прокси-сервер, который принимает OpenAI-compatible запросы (например, от JanitorAI на Android) и перенаправляет их в [NVIDIA NIM](https://build.nvidia.com/).

## Куда вводить API ключ NVIDIA NIM

1. Получите ключ на [build.nvidia.com](https://build.nvidia.com/) → профиль → **API Keys** → **Generate API Key**. Ключ выглядит как `nvapi-...`.
2. На [Railway](https://railway.com/) откройте ваш проект/сервис → вкладка **Variables** → нажмите **New Variable**.
3. Добавьте переменную:
   - **Name:** `NIM_API_KEY`
   - **Value:** ваш ключ `nvapi-...`
4. Railway автоматически перезапустит сервис после сохранения переменной.

> Не вставляйте ключ в код и не коммитьте его в репозиторий. На Railway он хранится в Variables (переменных окружения).

### Важно про ключ

- Если `NIM_API_KEY` задан на Railway, прокси **всегда использует его** для запросов в NVIDIA NIM. Это удобно для JanitorAI, который часто отправляет placeholder в поле API Key.
- Если `NIM_API_KEY` не задан, прокси использует `Authorization` заголовок, переданный клиентом.
- Значение `NIM_API_KEY` должно быть самим ключом `nvapi-...` (без кавычек и без лишнего `Bearer `).

## Деплой на Railway

1. Загрузите этот репозиторий в GitHub.
2. На [Railway](https://railway.com/) создайте **New Project** → **Deploy from GitHub repo** → выберите репозиторий.
3. В **Variables** добавьте `NIM_API_KEY` (см. выше).
4. Railway сам определит Python-проект по `requirements.txt` и запустит его по `Procfile`.
5. В настройках сервиса откройте **Networking** → **Generate Domain**. Вы получите URL вида `https://your-app.up.railway.app`.

## Настройка JanitorAI (Android)

1. В JanitorAI откройте настройки API / Proxy.
2. Выберите режим **OpenAI** / **Proxy** (OpenAI-compatible).
3. В поле **API URL / Endpoint** укажите ваш Railway URL, например:
   - `https://your-app.up.railway.app/v1`
4. В поле **API Key**:
   - если `NIM_API_KEY` задан на Railway — можно ввести любое непустое значение (или тот же ключ);
   - если не задан — введите ваш `nvapi-...` ключ.
5. Выберите модель NVIDIA NIM, например:
   - `meta/llama-3.1-405b-instruct`
   - `meta/llama-3.1-70b-instruct`
   - `nvidia/llama-3.1-nemotron-70b-instruct`
   - или другую доступную на [build.nvidia.com](https://build.nvidia.com/).

Точный список доступных моделей зависит от вашего аккаунта NVIDIA NIM и можно посмотреть через `GET /v1/models`.

## Переменные окружения

| Переменная | Обязательная | По умолчанию | Описание |
|---|---:|---|---|
| `NIM_API_KEY` | нет* | пусто | API ключ NVIDIA NIM. *Обязателен, если клиент не передаёт свой `Authorization`. |
| `NIM_BASE_URL` | нет | `https://integrate.api.nvidia.com/v1` | Базовый URL NVIDIA NIM API. |
| `PORT` | нет | `8000` | Порт, который задаёт Railway автоматически. |

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# впишите NIM_API_KEY в .env

uvicorn main:app --host 0.0.0.0 --port 8000
```

Проверка:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/v1/models -H "Authorization: Bearer $NIM_API_KEY"
```

## Эндпоинты

- `GET /` — статус прокси
- `GET /health` — healthcheck
- `GET /v1/models` — список моделей (проксируется в NVIDIA NIM)
- `POST /v1/chat/completions` — чат-запросы, включая streaming (`stream: true`)

Прокси также пробрасывает другие пути `/v1/*` в NVIDIA NIM.
