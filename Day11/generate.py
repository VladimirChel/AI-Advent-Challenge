import time
import uuid
from fastapi import APIRouter, HTTPException

from llm.schemas import GenerateRequest, GenerateResponse, ChatMessage
from llm.client import call_chat_completion, extract_text_from_chat_completion, get_usage
from llm.service import validate_output
from memory.models import MemoryPolicy
from memory.orchestrator import build_agent_context, materialize_context_messages
from repositories.messages import save_messages
from tasks.service import maybe_update_task_memory

router = APIRouter()


@router.post("/generate", response_model=GenerateResponse)
def generate(payload: GenerateRequest) -> GenerateResponse:
    request_id = str(uuid.uuid4())
    started = time.perf_counter()

    conversation_id = payload.conversation_id or str(uuid.uuid4())
    branch_id = payload.branch_id.strip() or "main"

    policy = MemoryPolicy()

    agent_ctx = build_agent_context(
        conversation_id=conversation_id,
        branch_id=branch_id,
        task_id=payload.task_id,
        policy=policy,
        live_messages=payload.messages,
    )

    full_messages = [*materialize_context_messages(agent_ctx), *payload.messages]

    response = call_chat_completion(
        model=payload.model,
        messages=full_messages,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        top_p=payload.top_p,
        presence_penalty=payload.presence_penalty,
        frequency_penalty=payload.frequency_penalty,
        user_id=payload.user_id,
    )

    content, finish_reason = extract_text_from_chat_completion(response)
    if not content.strip():
        raise HTTPException(status_code=502, detail="empty_model_response")

    validation = validate_output(content, payload.validation)
    usage = get_usage(response)

    save_messages(
        conversation_id=conversation_id,
        branch_id=branch_id,
        user_id=payload.user_id,
        model=payload.model,
        messages=[*payload.messages, ChatMessage(role="assistant", content=content)],
    )

    maybe_update_task_memory(
        conversation_id=conversation_id,
        branch_id=branch_id,
        task_id=payload.task_id,
        input_messages=payload.messages,
        assistant_response=content,
    )

    latency_ms = int((time.perf_counter() - started) * 1000)

    return GenerateResponse(
        request_id=request_id,
        conversation_id=conversation_id,
        branch_id=branch_id,
        task_id=payload.task_id,
        model=payload.model,
        content=content,
        finish_reason=finish_reason,
        usage=usage,
        latency_ms=latency_ms,
        short_term_used=bool(agent_ctx.short_term_messages),
        short_term_messages_used=len(agent_ctx.short_term_messages),
        working_memory_used=agent_ctx.working_memory is not None,
        long_term_used=bool(
            agent_ctx.long_term_summary
            or agent_ctx.long_term_facts
            or agent_ctx.retrieved_items
        ),
        long_term_facts_count=len(agent_ctx.long_term_facts),
        long_term_summary_used=agent_ctx.long_term_summary is not None,
        retrieval_used=bool(agent_ctx.retrieved_items),
        retrieval_messages_used=len(agent_ctx.retrieved_items),
    )