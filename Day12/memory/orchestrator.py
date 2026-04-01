from llm.schemas import ChatMessage
from memory.models import AgentMemoryContext, MemoryPolicy
from memory.short_term import load_short_term_memory
from memory.working import build_working_memory_message
from memory.long_term import build_facts_message, build_summary_message, build_retrieval_message
from tasks.repository import get_task_memory
from repositories.facts import get_user_facts
from repositories.summaries import get_user_memory_summary
from repositories.chunks import retrieve_memory_chunks


def build_agent_context(
    *,
    user_id: str,
    conversation_id: str,
    branch_id: str,
    task_id: str | None,
    policy: MemoryPolicy,
    live_messages: list[ChatMessage],
) -> AgentMemoryContext:
    ctx = AgentMemoryContext()

    if policy.short_term_enabled:
        ctx.short_term_messages = load_short_term_memory(
            conversation_id=conversation_id,
            branch_id=branch_id,
            limit=policy.short_term_limit,
        )

    if policy.working_memory_enabled and task_id:
        ctx.working_memory = get_task_memory(conversation_id, branch_id, task_id)

    if policy.long_term_enabled:
        if policy.summary_enabled:
            ctx.long_term_summary = get_user_memory_summary(user_id)

        if policy.sticky_facts_enabled:
            ctx.long_term_facts = get_user_facts(user_id)

        if policy.retrieval_enabled:
            query = "\n".join(m.content for m in live_messages if m.role == "user").strip()
            if query:
                ctx.retrieved_items = retrieve_memory_chunks(
                    user_id=user_id,
                    query=query,
                    limit=policy.retrieval_limit,
                )

    return ctx


def materialize_context_messages(ctx: AgentMemoryContext) -> list[ChatMessage]:
    result: list[ChatMessage] = []

    working_msg = build_working_memory_message(ctx.working_memory)
    if working_msg:
        result.append(working_msg)

    facts_msg = build_facts_message(ctx.long_term_facts)
    if facts_msg:
        result.append(facts_msg)

    summary_msg = build_summary_message(ctx.long_term_summary)
    if summary_msg:
        result.append(summary_msg)

    retrieval_msg = build_retrieval_message(ctx.retrieved_items)
    if retrieval_msg:
        result.append(retrieval_msg)

    result.extend(ctx.short_term_messages)
    return result
