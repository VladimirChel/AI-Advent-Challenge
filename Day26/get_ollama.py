import requests

url = "http://localhost:11434/api/generate"

data = {
    "model": "llama3",
    "prompt": "Напиши короткий список из 5 пунктов на русском",
    "stream": False
}

response = requests.post(url, json=data)
response.raise_for_status()

print(response.json())
print(response.json()["response"])