# Day30 - Тестирование локальной LLM

В этой папке находится скрипт для тестирования локальной LLM через `LLM Assistant`, запущенный в `stateless mode`.

Файл:

- [test_local_llm.py](D:\Yandex.Disk\Docs\AI\AI Advent Challenge\Repo\AI Advent Challenge\Day30\test_local_llm.py)

## Что проверяет скрипт

Скрипт отправляет запросы в `LLM Assistant` через HTTP API и проверяет:

- доступность сервиса через `smoke test`;
- базовые ограничения по размеру контекста;
- поведение при серии параллельных запросов;
- наличие или отсутствие `429 Too Many Requests`;
- задержки ответа.

Во время теста скрипт принудительно отключает:

- `RAG`;
- `MCP`;
- вывод переходов задач в чат.

Это сделано для того, чтобы измерять именно поведение локальной модели, а не дополнительной обвязки.

## Требования

- Python 3.10+;
- запущенный `LLM Assistant`;
- доступный HTTP API, обычно `http://127.0.0.1:8000`;
- `LLM Assistant` в `stateless mode`.

Проверить состояние сервиса можно так:

```bash
curl http://127.0.0.1:8000/health
```

Ожидаемо в ответе должно быть:

- `"stateless_mode": true`
- `"memory_enabled": false`

## Быстрый старт

Запуск с настройками по умолчанию:

```bash
python .\test_local_llm.py
```

Запуск с HTML-отчётом:

```bash
python .\test_local_llm.py --html-out .\test_report.html
```

Запуск с JSON и HTML одновременно:

```bash
python .\test_local_llm.py --json-out .\test_report.json --html-out .\test_report.html
```

## Выбор модели

Сначала можно получить список доступных моделей:

```bash
python .\test_local_llm.py --list-models
```

Пример вывода:

```text
provider_id: ollama
Available models:
- qwen2.5:7b-instruct
- llama3:latest
```

После этого можно явно выбрать модель:

```bash
python .\test_local_llm.py --model qwen2.5:7b-instruct
```

Или выбрать модель вместе с провайдером:

```bash
python .\test_local_llm.py --provider-id ollama --model llama3:latest
```

Если `--model` не передан, скрипт автоматически использует `default_model` из `/health`.

## Основные параметры

- `--base-url` - адрес `LLM Assistant`, по умолчанию `http://127.0.0.1:8000`
- `--model` - модель для тестирования
- `--provider-id` - идентификатор провайдера
- `--list-models` - вывести список моделей и завершить работу
- `--timeout` - таймаут одного запроса в секундах
- `--context-start` - начальный размер контекста в символах
- `--context-step` - шаг увеличения контекста в символах
- `--context-max` - максимальный размер контекста в символах
- `--rate-requests` - количество запросов в burst-тесте
- `--rate-concurrency` - уровень параллелизма в burst-тесте
- `--json-out` - путь к JSON-отчёту
- `--html-out` - путь к HTML-отчёту

## Примеры запуска

Проверка контекста до 100000 символов:

```bash
python .\test_local_llm.py --context-start 20000 --context-step 20000 --context-max 100000
```

Проверка burst-нагрузки:

```bash
python .\test_local_llm.py --rate-requests 12 --rate-concurrency 4
```

Полный запуск с выбранной моделью и HTML-отчётом:

```bash
python .\test_local_llm.py ^
  --provider-id ollama ^
  --model qwen2.5:7b-instruct ^
  --context-start 20000 ^
  --context-step 20000 ^
  --context-max 100000 ^
  --rate-requests 12 ^
  --rate-concurrency 4 ^
  --html-out .\test_report.html
```

## Что есть в отчётах

### Консольный отчёт

Скрипт печатает:

- статус сервиса;
- выбранную модель;
- результат `smoke test`;
- таблицу по росту контекста;
- итог по последнему успешному размеру контекста;
- статистику по burst-тесту;
- число ответов `429`.

### JSON-отчёт

JSON содержит сырые данные всех тестов:

- `health`
- `smoke`
- `context_results`
- `rate_result`

Подходит для дальнейшей автоматической обработки.

### HTML-отчёт

HTML содержит:

- краткую сводку по тесту;
- карточки с ключевыми метриками;
- таблицу `smoke test`;
- таблицу `context sweep`;
- таблицу `rate test`.

Подходит для ручного просмотра в браузере.

## Как интерпретировать результаты

Если в отчёте написано:

- `429 ответов не обнаружено` - в текущем burst-тесте сервер не вернул `HTTP 429`
- `last successful context` - максимальный успешно пройденный размер контекста в рамках заданного диапазона
- `first failed context` - первый размер контекста, на котором тест перестал проходить

Важно: отсутствие `429` не означает, что лимитов нет вообще. Это означает только то, что в текущей конфигурации теста они не проявились.

## Ограничения

- размер контекста оценивается грубо, через соотношение `1 токен ~= 4 символа`;
- реальные лимиты зависят от конкретной модели;
- результаты могут отличаться для разных провайдеров;
- burst-тест показывает практическое поведение сервиса, а не гарантированный паспортный лимит модели.

## Полезная команда

Вывести все параметры:

```bash
python .\test_local_llm.py --help
```
