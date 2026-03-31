# 🤖 LLM Assistant

LLM Assistant — это backend-сервис на FastAPI для работы с языковыми моделями (LLM), поддерживающий память (short-term и long-term), оркестрацию контекста и гибкую конфигурацию.

---

## 🚀 Возможности

* 🔌 Интеграция с LLM (OpenAI / proxy API)
* 🧠 Краткосрочная и долгосрочная память
* 🔄 Оркестрация контекста
* 🌐 REST API (FastAPI)
* ⚙️ Конфигурация через `.env` 
* 🧩 Расширяемая архитектура

---

## 📁 Структура проекта

```
llm_proj/
│
├── main.py                # Точка входа (FastAPI)
├── config.py             # Конфигурация
├── db.py                 # Работа с БД
├── generate.py           # Локальный запуск генерации
│
├── api/
│   └── generate.py       # HTTP endpoint
│
├── llm/
│   ├── client.py         # Клиент LLM
│   ├── schemas.py        # Pydantic схемы
│   └── service.py        # Логика генерации
│
├── memory/
│   ├── models.py         # Модели памяти
│   ├── long_term.py      # Долгосрочная память
│   └── orchestrator.py   # Управление памятью
│
└── .env.example
```

---

## ⚙️ Установка

### 1. Клонирование репозитория

```bash
git clone <your-repo-url>
cd llm_proj
```

### 2. Создание виртуального окружения

```bash
python -m venv venv
source venv/bin/activate  # Linux / Mac
venv\Scripts\activate     # Windows
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

---

## 🔐 Конфигурация

Создай `.env` файл на основе `.env.example`:

```env
APP_NAME=llm-assistant
APP_VERSION=1.0.0

PROXYAPI_API_KEY=your_api_key
PROXYAPI_BASE_URL=https://api.proxy.com/v1

DEFAULT_MODEL=gpt-4o-mini
REQUEST_TIMEOUT_SECONDS=30
```

---

## ▶️ Запуск

```bash
uvicorn main:app --reload
```

Приложение будет доступно по адресу:

```
http://localhost:8000
```

Swagger UI:

```
http://localhost:8000/docs
```

---

## 📡 API

### 🔹 Генерация ответа

**POST** `/generate`

#### Request:

```json
{
  "message": "Привет, кто ты?",
  "user_id": "123"
}
```

#### Response:

```json
{
  "response": "Я LLM ассистент 🤖"
}
```

---

### 🔹 Health Check

**GET** `/health`

---

## 🧠 Как работает система

1. Пользователь отправляет запрос
2. API принимает запрос
3. Memory Orchestrator:

   * извлекает релевантную память
   * формирует контекст
4. LLM Service:

   * собирает prompt
   * вызывает модель
5. Ответ:

   * сохраняется в память
   * возвращается пользователю

---

## 🧩 Конфигурация LLM (YAML)


## 🧠 Memory система

### Short-term memory

* Контекст диалога
* Sliding window

### Long-term memory

* Сохраняет знания
* Используется для RAG-подобных сценариев

### Orchestrator

* Решает:

  * что добавить в prompt
  * что сохранить
  * когда суммаризировать

---

## 🛠️ Разработка

### Запуск генерации локально

```bash
python generate.py
```

---

## 📈 Roadmap

* [ ] Streaming ответов
* [ ] RAG (vector DB)
* [ ] Function calling
* [ ] Multi-agent система
* [ ] Web UI

---

## 🐳 Docker (опционально)

```bash
docker build -t llm-assistant .
docker run -p 8000:8000 llm-assistant
```

---

## 📄 License

MIT License
