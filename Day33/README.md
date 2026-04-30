# Day33 Support Assistant MVP

Мини-сервис поддержки пользователей, который:

- отвечает на вопросы о продукте;
- использует RAG по FAQ и документации;
- учитывает контекст пользователя и тикета через MCP;
- использует `LLM Assistant` как backend генерации.

## Структура

- `main.py` - FastAPI API
- `support_service.py` - orchestration
- `assistant_client.py` - клиент к `LLM Assistant`
- `support_cli.py` - пользовательский CLI-интерфейс в стиле `Day26`
- `rag_adapter.py` - retrieval по артефактам `Day21`
- `mcp_client.py` - stdio MCP клиент
- `generate_support_data.py` - генератор `users.json` и `tickets.json`
- `index_support_docs.py` - индексация FAQ-документов
- `data/` - JSON и документация

## Быстрый старт

1. Сгенерировать demo-данные:

```powershell
python .\generate_support_data.py --seed-demo
```

2. Собрать RAG-индекс:

```powershell
python .\index_support_docs.py
```

3. Убедиться, что `LLM Assistant` запущен.

4. Запустить сервис:

```powershell
python .\main.py
```

5. Запустить пользовательский интерфейс:

```powershell
python .\support_cli.py --ticket T-1001
```

Если `ticket_id` заранее неизвестен, интерфейс сначала попросит пользователя представиться.
Можно ввести имя или `username`, после чего backend найдёт соответствующий аккаунт.
Если у пользователя есть недавние тикеты, CLI покажет их списком, и можно будет выбрать тикет просто по номеру.

6. Проверить demo-запрос:

```powershell
python .\demo_request.py
```

## Важные переменные окружения

- `ASSISTANT_BASE_URL`
- `ASSISTANT_AUTH_TOKEN`
- `ASSISTANT_MODEL`
- `SUPPORT_RAG_EMBED_MODEL`
- `SUPPORT_RAG_OLLAMA_URL`
- `SUPPORT_MCP_SERVER_SCRIPT`
