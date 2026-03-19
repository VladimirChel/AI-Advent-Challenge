# 🚀 LLM Gateway via ProxyAPI

## 📌 Описание

**LLM Gateway** — это backend-сервис на Python, реализованный с использованием **FastAPI**, который выступает в роли прокси между клиентскими приложениями и языковыми моделями (LLM) через ProxyAPI.

Сервис обеспечивает:

* централизованный доступ к LLM
* контроль параметров генерации
* валидацию ответов
* логирование и аудит

---

## ⚙️ Основные возможности

### 🔹 Генерация текста

* Поддержка OpenAI-compatible API через ProxyAPI
* Настраиваемые параметры:

  * `temperature`
  * `max_tokens`
  * `top_p`
  * `presence_penalty`
  * `frequency_penalty`
  * `stop` последовательности

---

### 🔹 Валидация ответов

Можно задать правила проверки ответа модели:

* Минимальная/максимальная длина
* Обязательные слова (`must_contain`)
* Запрещённые слова (`forbid_phrases`)
* Проверка на корректный JSON

---

### 🔹 Логирование и аудит

Сервис автоматически сохраняет:

* 📄 `logs/app.log` — обычные логи
* 📄 `logs/audit.jsonl` — аудит всех запросов к LLM

Аудит включает:

* входные параметры
* результат генерации
* метрики
* ошибки

---

### 🔹 Middleware

Добавляет к каждому запросу:

* `X-Request-ID`
* `X-Latency-Ms`

И логирует:

* время выполнения
* статус ответа

---

## 🌐 API endpoints

### ✅ `GET /health`

Проверка состояния сервиса

**Ответ:**

```json
{
  "status": "ok",
  "service": "llm-gateway",
  "base_url": "...",
  "default_model": "...",
  "time": "..."
}
```

---

### 🤖 `POST /generate`

Основной endpoint для генерации текста

**Пример запроса:**

```json
{
  "model": "openai/gpt-4o-mini",
  "messages": [
    {"role": "user", "content": "Привет!"}
  ],
  "temperature": 0.2,
  "max_tokens": 100
}
```

**Ответ:**

```json
{
  "request_id": "...",
  "created_at": "...",
  "model": "...",
  "content": "...",
  "finish_reason": "stop",
  "latency_ms": 123,
  "usage": {},
  "validation": {
    "ok": true,
    "errors": []
  }
}
```

---

### 📦 `GET /models`

Получение списка доступных моделей

---

## 🧱 Архитектура

Проект состоит из:

* **Config** — переменные окружения
* **OpenAI Client** — подключение через ProxyAPI
* **Pydantic модели** — валидация данных
* **Бизнес-логика**:

  * генерация текста
  * обработка ответа
  * валидация
* **Логирование и аудит**
* **FastAPI API**

---

## 🔐 Конфигурация

Создайте `.env` файл:

```env
PROXYAPI_API_KEY=your_api_key
PROXYAPI_BASE_URL=https://openai.api.proxyapi.ru/v1

APP_HOST=0.0.0.0
APP_PORT=8000

DEFAULT_MODEL=openai/gpt-4o-mini
REQUEST_TIMEOUT_SECONDS=60

MAX_TEMPERATURE=1.2
MAX_MAX_TOKENS=4000

LOG_DIR=logs
```

---

## 🚀 Запуск

### 1. Установка зависимостей

```bash
pip install fastapi uvicorn python-dotenv openai pydantic
```

### 2. Запуск сервера

```bash
uvicorn app:app --reload
```

или

```bash
python app.py
```

---

## 📊 Преимущества

* ✅ Контроль над LLM-запросами
* ✅ Встроенная валидация ответов
* ✅ Полный аудит (важно для продакшена)
* ✅ Расширяемая архитектура
* ✅ Подходит для enterprise-решений

---

## 🛠️ Возможности для расширения

* Добавление rate limiting
* Кэширование ответов
* Авторизация пользователей
* Поддержка streaming-ответов
* Интеграция с другими LLM-провайдерами

---

## 📄 Лицензия

Проект можно использовать и модифицировать под свои задачи.

---

## ✨ Автор

Разработано как универсальный шлюз для работы с LLM через ProxyAPI.
