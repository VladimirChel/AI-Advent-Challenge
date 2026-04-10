# MCP сервер для отправки сообщений в Telegram

`telegram_sender` — это простой MCP сервер по `stdio`, который отправляет сообщения в Telegram через Bot API.

Сервер подходит для сценариев, где MCP-клиенту нужно:

- отправить уведомление в личный чат, группу или канал
- послать форматированное сообщение через `HTML` или `MarkdownV2`
- писать в конкретный топик супергруппы через `message_thread_id`

Реализация сделана по тому же принципу, что и в `Day16`: отдельный MCP сервер, отдельный модуль с бизнес-логикой и маленький локальный клиент для проверки.

## Состав проекта

- `server.py` — MCP сервер по `stdio`
- `telegram_sender.py` — работа с Telegram Bot API и загрузка `.env`
- `mcp_stdio.py` — чтение и запись JSON-RPC сообщений MCP
- `client.py` — локальный тестовый клиент
- `.env.example` — пример настроек

## Что умеет сервер

Сервер предоставляет 3 MCP tool:

- `telegram_sender_status` — показывает, настроены ли токен и чат по умолчанию
- `telegram_get_me` — возвращает информацию о боте через `getMe`
- `send_telegram_message` — отправляет сообщение в Telegram

### Параметры `send_telegram_message`

- `text` — текст сообщения, обязательный параметр
- `chat_id` — id чата; можно не передавать, если задан `TELEGRAM_DEFAULT_CHAT_ID`
- `parse_mode` — режим форматирования, например `HTML` или `MarkdownV2`
- `disable_web_page_preview` — отключить превью ссылок
- `disable_notification` — отправить без звука
- `protect_content` — запретить пересылку и сохранение
- `message_thread_id` — id топика в супергруппе

## Настройка

Проект не требует сторонних Python-библиотек.

Создай файл `.env` рядом с `server.py`:

```env
TELEGRAM_BOT_TOKEN=123456789:replace_with_real_token
TELEGRAM_DEFAULT_CHAT_ID=-1003824629076
TELEGRAM_DEFAULT_PARSE_MODE=HTML
```

### Переменные окружения

- `TELEGRAM_BOT_TOKEN` — токен бота из BotFather
- `TELEGRAM_DEFAULT_CHAT_ID` — чат по умолчанию для отправки
- `TELEGRAM_DEFAULT_PARSE_MODE` — форматирование по умолчанию: `HTML`, `MarkdownV2`, `Markdown`

## Важные замечания по Telegram

- Бот должен быть добавлен в нужный чат, группу или канал
- Для личного чата пользователь должен хотя бы один раз написать боту
- Для супергрупп и каналов `chat_id` обычно отрицательный и часто начинается с `-100`
- Если Telegram отвечает `Bad Request: chat not found`, чаще всего проблема в неверном `chat_id` или в том, что бот не имеет доступа к чату

## Локальная проверка

```bash
python client.py status
python client.py me
python client.py send --text "Hello from MCP"
python client.py send --chat-id -1003824629076 --text "<b>Hello</b>" --parse-mode HTML
python client.py send --chat-id -1003824629076 --text "Topic message" --message-thread-id 123
```

## Запуск MCP сервера

```bash
python server.py
```

После запуска сервер принимает MCP JSON-RPC сообщения через стандартный ввод и стандартный вывод, поэтому его можно подключать к любому MCP-совместимому клиенту.
