agent_app/
  main.py
  config.py
  db.py
  logging_setup.py

  api/
    generate.py
    conversations.py
    memory.py
    tasks.py

  llm/
    client.py
    schemas.py
    service.py

  conversations/
    models.py
    repository.py
    service.py

  memory/
    models.py
    orchestrator.py
    short_term.py
    working.py
    long_term.py
    summarizer.py
    facts.py
    retrieval.py

  tasks/
    models.py
    repository.py
    service.py

  repositories/
    messages.py
    summaries.py
    facts.py
    chunks.py

  migrations/
    001_init_agent_memory.sql