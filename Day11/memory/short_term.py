from llm.schemas import ChatMessage
from repositories.short_term import get_recent_messages


def load_short_term_memory(conversation_id: str, branch_id: str, limit: int) -> list[ChatMessage]:
    return get_recent_messages(conversation_id, branch_id, limit)