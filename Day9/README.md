# LLM Gateway via ProxyAPI

Прокси-сервис для безопасной и контролируемой работы с LLM (Large Language Models) через ProxyAPI.  
Предоставляет REST API с поддержкой памяти диалогов, валидации ответов и автоматического суммаризирования.

---

## 🚀 Возможности

- 🔌 Прокси к LLM (через ProxyAPI / OpenAI-совместимый API)
- 💾 Хранение истории диалогов в PostgreSQL
- 🧠 Поддержка "памяти" с автоматическим суммаризированием
- ✅ Валидация ответов модели (длина, JSON, ключевые слова и т.д.)
- 📊 Логирование и аудит всех запросов
- ⚡ FastAPI + асинхронная архитектура
- 🔄 Контроль параметров генерации (temperature, top_p и др.)

---

## 📦 Технологии

- Python 3.10+
- FastAPI
- PostgreSQL (через psycopg + connection pool)
- OpenAI SDK (через ProxyAPI)
- Pydantic
- Uvicorn

---

## ⚙️ Переменные окружения

Создай `.env` файл:

PROXYAPI_API_KEY=your_api_key
PROXYAPI_BASE_URL=https://openai.api.proxyapi.ru/v1

DATABASE_URL=postgresql://user:password@localhost:5432/dbname

APP_HOST=0.0.0.0
APP_PORT=8000

DEFAULT_MODEL=openai/gpt-4o-mini
REQUEST_TIMEOUT_SECONDS=60

MAX_TEMPERATURE=1.2
MAX_MAX_TOKENS=4000

DEFAULT_HISTORY_LIMIT=20
MAX_HISTORY_LIMIT=100

SUMMARY_TRIGGER_MESSAGES=24
SUMMARY_KEEP_LAST_MESSAGES=10
SUMMARY_MAX_INPUT_MESSAGES=100
SUMMARY_MAX_TOKENS=500
SUMMARY_MODEL=

---

## 🛠 Установка и запуск

git clone <repo>
cd <repo>

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

Запуск:

python app.py

или

uvicorn app:app --reload

---

## 📡 API

### 🔹 Health check
GET /health

### 🔹 Генерация ответа
POST /generate

Пример запроса:

{
  "model": "openai/gpt-4o-mini",
  "messages": [
    {"role": "user", "content": "Привет!"}
  ],
  "conversation_id": "optional-id",
  "use_memory": true
}

### 🔹 Получить сообщения диалога
GET /conversations/{conversation_id}/messages

### 🔹 Получить summary диалога
GET /conversations/{conversation_id}/summary

### 🔹 Принудительно обновить summary
POST /conversations/{conversation_id}/summary/refresh

### 🔹 Список моделей
GET /models

---

## 🧠 Как работает память

1. Сообщения сохраняются в БД
2. При достижении порога:
   - старые сообщения сжимаются в summary
3. При новых запросах:
   - используется summary + последние сообщения

---

## ✅ Валидация ответа

Пример:

{
  "validation": {
    "min_output_length": 10,
    "max_output_length": 500,
    "must_contain": ["ответ"],
    "forbid_phrases": ["ошибка"],
    "require_json": false
  }
}

---

## 🗄 Структура БД

### conversations
- id
- user_id
- model
- created_at
- updated_at

### messages
- id
- conversation_id
- role
- content
- seq_no

### conversation_summaries
- conversation_id
- summary
- source_upto_seq_no

---

## 📊 Логирование

- logs/app.log — обычные логи
- logs/audit.jsonl — аудит запросов и ответов

---

## ⚠️ Ошибки

{
  "error": "upstream_llm_error",
  "message": "...",
  "request_id": "...",
  "conversation_id": "...",
  "latency_ms": 123
}

---

## 🔐 Безопасность

- Контроль параметров генерации
- Ограничения на длину входа/выхода
- Валидация структуры данных
- Аудит всех запросов

---

## 🧩 Возможные улучшения

- Rate limiting
- Кэширование ответов
- Streaming responses
- WebSocket поддержка
- RBAC / auth

---

## 📄 Лицензия

MIT

---

## 👨‍💻 Автор

LLM Gateway Team
