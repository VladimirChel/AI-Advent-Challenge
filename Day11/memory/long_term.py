from llm.schemas import ChatMessage
from memory.models import StickyFact, RetrievedMemoryItem


def build_facts_message(facts: list[StickyFact]) -> ChatMessage | None:
    if not facts:
        return None

    lines = ["Долговременные факты:"]
    for fact in facts:
        lines.append(f"- [{fact.memory_kind}] {fact.key}: {fact.value}")
    return ChatMessage(role="system", content="\n".join(lines))


def build_summary_message(summary: str | None) -> ChatMessage | None:
    if not summary:
        return None
    return ChatMessage(role="system", content="Долговременное резюме:\n" + summary)


def build_retrieval_message(items: list[RetrievedMemoryItem]) -> ChatMessage | None:
    if not items:
        return None

    lines = ["Релевантные фрагменты из долговременной памяти:"]
    for item in items:
        lines.append(f"- source={item.source_type}:{item.source_ref} score={item.score}: {item.content}")
    return ChatMessage(role="system", content="\n".join(lines))