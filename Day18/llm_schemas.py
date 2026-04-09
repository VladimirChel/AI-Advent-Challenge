from pydantic import BaseModel, Field


class SummaryRequest(BaseModel):
    title: str
    prompt: str
    model: str
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=600, ge=32, le=4000)
