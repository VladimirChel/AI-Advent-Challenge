# Day29 Debt Report Assistant MVP

MVP-агент анализирует отчеты 1С по дебиторской задолженности из локальной папки, строит снапшоты по дням, отвечает на вопросы через `LLM Assistant` и может работать как Telegram-бот.

## Архитектура

`XLSX/ODS -> pandas parser -> JSON snapshots -> analytics service -> LLM Assistant -> Telegram Bot API`

## Что умеет

- читать отчеты из папки `documents`
- извлекать дату отчета, общую дебиторку, просрочку, менеджеров, контрагентов и договоры
- строить локальные JSON-снапшоты по дням
- отвечать на типовые вопросы без LLM
- отправлять сложные вопросы в `LLM Assistant`
- обезличивать чувствительные поля перед облачной LLM и восстанавливать их в ответе
- работать через long polling Telegram Bot API без внешней Telegram SDK
- выводить обезличенные ответы с токенами `MANAGER_001`, `CLIENT_001`, `CONTRACT_001`

## Запуск

### 1. Индексация отчетов

```bash
python main.py index
```

### 2. Локальный вопрос из CLI

```bash
python main.py ask "какая общая дебиторка сегодня"
python main.py ask "топ должников"
python main.py ask "как изменилась просрочка за 3 дня"
python main.py ask --anonymized "что у Название_контрагента"
```

### 3. Telegram-бот

```bash
python main.py bot
```

Проверка только Telegram-бота:

```bash
python check_telegram_bot.py
python check_telegram_bot.py --updates
```

Команды бота:

- `/today` - сводка по текущему отчету
- `/top` - топ контрагентов по долгу
- `/reload` - пересобрать индекс из папки `documents`
- `/anon_on` - включить режим обезличенных данных
- `/anon_off` - выключить режим обезличенных данных
- `/mode` - показать текущий режим

## Переменные окружения

```env
DEBT_DOCUMENTS_DIR=D:\Yandex.Disk\Docs\AI\AI Advent Challenge\Repo\AI Advent Challenge\Day29\documents
DEBT_OUTPUT_DIR=D:\Yandex.Disk\Docs\AI\AI Advent Challenge\Repo\AI Advent Challenge\Day29\output
DEBT_SNAPSHOTS_DIR=D:\Yandex.Disk\Docs\AI\AI Advent Challenge\Repo\AI Advent Challenge\Day29\output\snapshots

LLM_ASSISTANT_URL=http://127.0.0.1:8000/generate
LLM_ASSISTANT_TOKEN=
LLM_MODEL=gpt-4o-mini
LLM_PROVIDER_ID=
LLM_CLOUD_MODE=false

TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=
TELEGRAM_POLL_TIMEOUT_SECONDS=30
TELEGRAM_PARSE_MODE=HTML
TELEGRAM_PROXY_URL=
```

`LLM_CLOUD_MODE=true` включает обезличивание `manager_name`, `client_name`, `contract_name` и `name` перед вызовом LLM.

Для Telegram можно задать `TELEGRAM_PROXY_URL`, например:

```env
TELEGRAM_PROXY_URL=socks5://127.0.0.1:1080
```

Если у прокси есть логин и пароль, используйте формат:

```env
TELEGRAM_PROXY_URL=socks5://username:password@127.0.0.1:1080
```

## Ограничения MVP

- парсер завязан на текущую структуру отчета 1С
- для тренда за 3 дня нужны 3 файла; если файлов меньше, агент честно сообщает это
- входящий Telegram реализован отдельно, а `MCP/telegram_sender` можно использовать дополнительно для исходящих уведомлений
