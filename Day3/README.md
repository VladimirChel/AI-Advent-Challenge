# 🧠 LLM Gateway Client

Десктопное приложение на Python для тестирования и сравнения ответов LLM через единый API (LLM Gateway).
https://github.com/VladimirChel/AI-Advent-Challenge/tree/main/Day2

Позволяет запускать один и тот же вопрос в разных сценариях, анализировать ответы и автоматически генерировать отчёты.

---

## 🚀 Возможности

* 📡 Подключение к LLM Gateway (`/generate`, `/health`, `/models`)
* 🤖 Поддержка разных моделей:

  * OpenAI (GPT-4, GPT-4.1, GPT-4o)
  * Anthropic (Claude)
  * Google (Gemini)
* 🧪 4 сценария генерации:

  1. Прямой ответ
  2. Пошаговое решение (Chain-of-Thought)
  3. Самогенерация prompt + ответ
  4. Группа экспертов (multi-agent)
* 📊 Автоматическое сравнение ответов
* 📈 Визуализация:

  * Время ответа
  * Использование токенов
* 📄 Экспорт отчётов:

  * HTML (с графиками)
  * JSON
  * CSV
* 🖥️ GUI-интерфейс (CustomTkinter)

---

## 🧱 Архитектура

Приложение состоит из нескольких ключевых компонентов:

* **LLMGatewayClient** — работа с API
* **FourModeRunner** — запуск 4 сценариев
* **SettingsPanel** — настройки параметров
* **App (GUI)** — основной интерфейс
* **Report Builder** — генерация HTML/CSV/JSON отчётов

---

## ⚙️ Установка

### 1. Клонировать репозиторий

```bash
git clone https://github.com/your-repo/llm-gateway-client.git
cd llm-gateway-client
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

Или вручную:

```bash
pip install customtkinter requests python-dotenv
```

---

## 🔐 Переменные окружения

Создай файл `.env`:

```env
REQUEST_URL=http://127.0.0.1:8000/generate
DEFAULT_MODEL=openai/gpt-4o-mini
```

---

## ▶️ Запуск

```bash
python llm_gateway_client.py
```

---

## 🖥️ Интерфейс

### Основные действия:

* **Проверить /health** — проверка сервера
* **Получить /models** — список моделей
* **Запустить 4 сценария** — основной запуск
* **Открыть отчёт** — открыть последний HTML-отчёт

---

## 🧪 Сценарии работы

### 1. Прямой ответ

Обычный запрос без дополнительных инструкций.

### 2. Пошаговое решение

Используется system prompt для reasoning.

### 3. Self-Prompting

1. LLM генерирует prompt
2. Затем отвечает с этим prompt

### 4. Группа экспертов

Имитация ролей:

* Аналитик
* Инженер
* Критик
* Модератор

---

## 📊 Отчёты

После запуска создаются файлы в папке `reports/`:

* `report_*.html` — визуальный отчёт
* `report_*.json` — сырые данные
* `report_*.csv` — метрики

### HTML включает:

* Ответы всех сценариев
* Использованные prompt'ы
* Raw API ответы
* Графики (Chart.js)

---

## 🔌 API формат

Запрос:

```json
{
  "model": "openai/gpt-4o-mini",
  "messages": [
    {"role": "user", "content": "Ваш вопрос"}
  ],
  "temperature": 0.3,
  "max_tokens": 1200
}
```

Ответ:

```json
{
  "content": "Ответ модели",
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 200,
    "total_tokens": 300
  }
}
```

---

## 📁 Структура проекта

```
.
├── llm_gateway_client.py
├── reports/
├── .env
└── README.md
```

---

## 🧠 Для чего это полезно

* Сравнение prompt-инжиниринга
* Benchmark моделей
* Анализ latency и токенов
* Исследование multi-agent подходов

---

## ⚠️ Требования

* Python 3.9+
* Запущенный LLM Gateway API

---

## 📌 TODO / идеи развития

* Поддержка streaming
* Сохранение истории запросов
* Batch-запросы
* A/B тестирование моделей
* Web-версия интерфейса

---

## 📝 Лицензия

Проект можно использовать и модифицировать под свои задачи.

---

## 👤 Автор

kvv
