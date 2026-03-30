# 🧠 LLM Gateway (FastAPI + ProxyAPI)

Прокси-сервер для работы с LLM (OpenAI-совместимые модели через ProxyAPI) с продвинутым управлением памятью, историей диалога и валидацией ответов.

---

## 🚀 Возможности

* 🔌 Прокси к LLM (через ProxyAPI)
* 💬 Хранение диалогов в PostgreSQL
* 🌳 Ветки диалогов (branching)
* 🧠 Продвинутая память:

  * window (последние сообщения)
  * summary (сжатие истории)
  * retrieval (поиск по истории)
  * sticky facts (долгосрочные факты)
  * hybrid режимы
* 📊 Логирование и аудит
* ✅ Валидация ответов LLM
* ⚡ FastAPI + асинхронная архитектура

---

## 🏗️ Архитектура

```
Client → FastAPI → LLM Gateway → ProxyAPI → LLM
                     ↓
                PostgreSQL
```

---

## 📦 Установка

### 1. Клонировать репозиторий

```bash
git clone <repo_url>
cd <repo_name>
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

### 3. Создать `.env`

```env
PROXYAPI_API_KEY=your_api_key
PROXYAPI_BASE_URL=https://openai.api.proxyapi.ru/v1
DATABASE_URL=postgresql://user:password@localhost:5432/dbname

APP_HOST=0.0.0.0
APP_PORT=8000
DEFAULT_MODEL=openai/gpt-4o-mini
```

---

## 🧠 База данных

При запуске автоматически создаются таблицы:

* `conversations`
* `messages`
* `conversation_summaries`
* `conversation_facts`

Также используются расширения:

* `pgcrypto`
* `pg_trgm` (для retrieval)

---

## ▶️ Запуск

```bash
python app.py
```

или

```bash
uvicorn app:app --reload
```

---

## 📡 API

### 🔍 Health check

```
GET /health
```

---

### 🤖 Генерация ответа

```
POST /generate
```

#### Пример запроса:

```json
{
  "model": "openai/gpt-4o-mini",
  "messages": [
    {"role": "user", "content": "Привет!"}
  ],
  "use_memory": true,
  "memory_strategy": "hybrid"
}
```

#### Ответ:

```json
{
  "content": "...",
  "conversation_id": "...",
  "latency_ms": 123,
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 20
  }
}
```

---

## 🧠 Memory стратегии

| Стратегия      | Описание                     |
| -------------- | ---------------------------- |
| `none`         | без памяти                   |
| `window`       | последние N сообщений        |
| `summary`      | сжатая история               |
| `retrieval`    | поиск по истории             |
| `facts`        | sticky facts                 |
| `hybrid`       | window + summary + retrieval |
| `hybrid_facts` | всё + sticky facts           |

---

## 🌳 Ветки диалогов

Позволяют "форкать" диалог:

```
POST /conversations/{id}/branches
```

Используется:

* `branch_id`
* `fork_from_message_uuid`

---

## 📚 Работа с историей

### Получить сообщения

```
GET /conversations/{id}/messages
```

### Получить summary

```
GET /conversations/{id}/summary
```

### Получить facts

```
GET /conversations/{id}/facts
```

---

## 🔄 Обновление памяти

### Обновить summary

```
POST /conversations/{id}/summary/refresh
```

### Обновить facts

```
POST /conversations/{id}/facts/refresh
```

---

## 🔍 Retrieval

* Использует `pg_trgm`
* Поиск по схожести текста
* Ограничение по score и длине

---

## 🧾 Логи

* `logs/app.log` — обычные логи
* `logs/audit.jsonl` — аудит всех LLM вызовов

---

## ⚙️ Конфигурация (ENV)

| Переменная                        | Описание            |
| --------------------------------- | ------------------- |
| `PROXYAPI_API_KEY`                | API ключ            |
| `DATABASE_URL`                    | строка подключения  |
| `DEFAULT_MODEL`                   | модель по умолчанию |
| `REQUEST_TIMEOUT_SECONDS`         | таймаут             |
| `MAX_TEMPERATURE`                 | лимит температуры   |
| `RETRIEVAL_ENABLED_BY_DEFAULT`    | включить retrieval  |
| `STICKY_FACTS_ENABLED_BY_DEFAULT` | включить facts      |

---

## 🛡️ Валидация ответа

Можно задать правила:

```json
"validation": {
  "min_output_length": 10,
  "must_contain": ["important"],
  "require_json": true
}
```

---

## 🧪 Разработка

* Python 3.10+
* FastAPI
* PostgreSQL
* psycopg3

---

## 📌 TODO / идеи

* streaming ответов
* embeddings вместо trigram
* UI для диалогов
* rate limiting
* auth

---

## 📄 Лицензия

MIT
