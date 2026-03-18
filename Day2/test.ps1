curl.exe -X POST "http://127.0.0.1:8000/generate" `
  -H "Content-Type: application/json" `
  -d '{
    "model": "openai/gpt-4o-mini",
    "messages": [
      {"role": "system", "content": "Отвечай кратко и по делу."},
      {"role": "user", "content": "Объясни, что такое FastAPI."}
    ],
    "temperature": 0.2,
    "max_tokens": 300,
    "validation": {
      "min_output_length": 30,
      "forbid_phrases": ["я не знаю"]
    }
  }'
