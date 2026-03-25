# LLM Gateway via ProxyAPI

## 📌 Overview

**LLM Gateway** — это прокси-сервис на базе **FastAPI**, предназначенный для безопасного и контролируемого взаимодействия с LLM через ProxyAPI.

Основные возможности:

* централизованный доступ к LLM
* хранение истории диалогов в PostgreSQL
* валидация ответов модели
* аудит и логирование
* управление параметрами генерации

---

## ⚙️ Tech Stack

* Python 3.10+
* FastAPI
* PostgreSQL (psycopg)
* OpenAI SDK (через ProxyAPI)
* Pydantic v2
* Uvicorn

---

## 🚀 Features

* 🔁 Поддержка истории диалогов (conversation memory)
* 🧠 Контекстные запросы с ограничением истории
* 📏 Валидация ответа (длина, ключевые слова, JSON)
* 📊 Логирование (app.log + audit.jsonl)
* 🔐 Контроль параметров генерации
* 🧩 Middleware с трассировкой запросов
* ❤️ Health-check endpoint

---

## 📁 Project Structure

```
.
├── app.py              # Основное приложение
├── logs/
│   ├── app.log        # Логи приложения
│   └── audit.jsonl    # Аудит вызовов LLM
└── README.md
```

---

## 🔑 Environment Variables

| Variable            | Description                  | Required |
| ------------------- | ---------------------------- | -------- |
| `PROXYAPI_API_KEY`  | API ключ ProxyAPI            | ✅        |
| `PROXYAPI_BASE_URL` | URL ProxyAPI                 | ❌        |
| `DATABASE_URL`      | PostgreSQL connection string | ✅        |
| `APP_HOST`          | Хост приложения              | ❌        |
| `APP_PORT`          | Порт приложения              | ❌        |
| `DEFAULT_MODEL`     | Модель по умолчанию          | ❌        |

---

## 🛠 Installation

```bash
git clone <repo>
cd <repo>

python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

---

## ▶️ Run Application

```bash
python app.py
```

или через uvicorn:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📡 API Endpoints

### 🔍 Health Check

```
GET /health
```

---

### 🤖 Generate Response

```
POST /generate
```

#### Request Example

```json
{
  "model": "openai/gpt-4o-mini",
  "messages": [
    {"role": "user", "content": "Hello"}
  ]
}
```

---

### 💬 Get Conversation Messages

```
GET /conversations/{conversation_id}/messages
```

---

### 📦 List Available Models

```
GET /models
```

---

## 🧠 Conversation Memory

* Используется `conversation_id`
* История хранится в PostgreSQL
* Ограничивается параметром `history_limit`

---

## ✅ Response Validation

Поддерживается:

* минимальная / максимальная длина
* обязательные фразы
* запрещённые фразы
* проверка JSON

Пример:

```json
"validation": {
  "min_output_length": 10,
  "must_contain": ["success"],
  "require_json": true
}
```

---

## 🗄 Database Schema

### conversations

| Column     | Type      |
| ---------- | --------- |
| id         | TEXT      |
| user_id    | TEXT      |
| model      | TEXT      |
| created_at | TIMESTAMP |
| updated_at | TIMESTAMP |

---

### messages

| Column          | Type      |
| --------------- | --------- |
| id              | BIGSERIAL |
| conversation_id | TEXT      |
| role            | TEXT      |
| content         | TEXT      |
| seq_no          | INTEGER   |
| created_at      | TIMESTAMP |

---

## 📜 Logging & Audit

* `logs/app.log` — технические логи
* `logs/audit.jsonl` — аудит запросов к LLM

---

## ⚠️ Error Handling

* `500` — internal server error
* `502` — ошибка upstream LLM
* Все ошибки возвращают:

  * `request_id`
  * `latency_ms`

---

## 🔒 Security Notes

* Не храните API ключи в коде
* Используйте `.env`
* Ограничивайте параметры генерации

---

## 📌 TODO

* [ ] Rate limiting
* [ ] Auth (JWT/API key)
* [ ] Streaming responses
* [ ] Metrics (Prometheus)

---

## 📄 License

Используй свободно под свои задачи.
