import time
import uuid

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user
from auth.schemas import PublicUser
from invariants.service import (
    build_invariant_refusal,
    check_response_against_invariants,
    load_project_invariants,
)
from llm.client import call_chat_completion, extract_text_from_chat_completion, get_usage
from llm.schemas import ChatMessage, GenerateRequest, GenerateResponse
from llm.service import validate_output
from memory.models import MemoryPolicy
from memory.orchestrator import build_agent_context, materialize_context_messages
from repositories.conversations import assert_conversation_access
from repositories.chunks import add_memory_chunks
from repositories.facts import extract_candidate_facts, upsert_facts
from repositories.messages import get_recent_messages_for_summary, save_messages
from repositories.summaries import build_summary_from_messages, upsert_conversation_summary
from tasks.service import maybe_update_task_memory

router = APIRouter()


@router.post("/generate", response_model=GenerateResponse)
def generate(payload: GenerateRequest, current_user: PublicUser = Depends(get_current_user)) -> GenerateResponse:
    request_id = str(uuid.uuid4())
    started = time.perf_counter()

    conversation_id = payload.conversation_id or str(uuid.uuid4())
    branch_id = payload.branch_id.strip() or "main"
    user_id = current_user.id

    assert_conversation_access(conversation_id=conversation_id, user_id=user_id)

    policy = MemoryPolicy()
    agent_ctx = build_agent_context(
        user_id=user_id,
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
        user_id=user_id,
    )

    content, finish_reason = extract_text_from_chat_completion(response)
    if not content.strip():
        raise HTTPException(status_code=502, detail="empty_model_response")

    invariants = load_project_invariants()
    invariant_check = check_response_against_invariants(
        user_messages=payload.messages,
        assistant_response=content,
        model=payload.model,
        user_id=user_id,
    )
    if not invariant_check.allowed:
        content = build_invariant_refusal(invariant_check)

    validate_output(content, payload.validation)
    usage = get_usage(response)

    exchange_messages = [*payload.messages, ChatMessage(role="assistant", content=content)]
    save_messages(
        conversation_id=conversation_id,
        branch_id=branch_id,
        user_id=user_id,
        model=payload.model,
        messages=exchange_messages,
    )

    maybe_update_task_memory(
        conversation_id=conversation_id,
        branch_id=branch_id,
        task_id=payload.task_id,
        input_messages=payload.messages,
        assistant_response=content,
    )

    facts = extract_candidate_facts(payload.messages)
    upsert_facts(conversation_id, branch_id, user_id, facts)
    add_memory_chunks(user_id, conversation_id, branch_id, exchange_messages)

    recent_messages, latest_seq_no = get_recent_messages_for_summary(
        conversation_id=conversation_id,
        branch_id=branch_id,
        limit=16,
    )
    summary = build_summary_from_messages(recent_messages)
    if summary:
        upsert_conversation_summary(
            conversation_id=conversation_id,
            branch_id=branch_id,
            user_id=user_id,
            summary=summary,
            source_upto_seq_no=latest_seq_no,
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
        long_term_used=bool(agent_ctx.long_term_summary or agent_ctx.long_term_facts or agent_ctx.retrieved_items),
        long_term_facts_count=len(agent_ctx.long_term_facts),
        long_term_summary_used=agent_ctx.long_term_summary is not None,
        retrieval_used=bool(agent_ctx.retrieved_items),
        retrieval_messages_used=len(agent_ctx.retrieved_items),
        project_invariants_used=bool(invariants.invariants),
        project_invariants_count=len(invariants.invariants),
        invariant_check_passed=invariant_check.allowed,
        invariant_violations=[item.id for item in invariant_check.violations],
    )
