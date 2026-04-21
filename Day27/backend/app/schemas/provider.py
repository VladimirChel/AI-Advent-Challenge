from pydantic import BaseModel


class ChatRequest(BaseModel):
    chat_id: str
    provider: str
    model: str
    messages: list[dict[str, str]]
    temperature: float = 0.7
    max_tokens: int = 1024
    stream: bool = False
    system_prompt: str = ""


class ChatResponse(BaseModel):
    provider: str
    model: str
    content: str
    usage: dict[str, int]
    latency_ms: int
    finish_reason: str = "stop"

