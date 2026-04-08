import time
import uuid

from fastapi import APIRouter, Depends, HTTPException

from config import (
    MCP_ENABLED_BY_DEFAULT,
    MCP_MAX_TOOL_ROUNDTRIPS,
    MCP_SERVER_SCRIPT,
    MCP_TOOL_CALL_TIMEOUT_SECONDS,
    MCP_WAIT_AFTER_START_SECONDS,
)
from auth.dependencies import get_current_user
from auth.schemas import PublicUser
from invariants.schemas import InvariantCheckResult
from invariants.service import (
    build_invariant_refusal,
    check_response_against_invariants,
    load_project_invariants,
)
from llm.client import aggregate_usage, call_chat_completion_with_mcp, extract_text_from_chat_completion
from llm.schemas import ChatMessage, GenerateRequest, GenerateResponse, MCPSettings
from llm.service import validate_output
from memory.models import MemoryPolicy
from memory.orchestrator import build_agent_context, materialize_context_messages
from repositories.conversations import assert_conversation_access
from repositories.chunks import add_memory_chunks
from repositories.facts import extract_candidate_facts, upsert_facts
from repositories.messages import ensure_conversation, get_recent_messages_for_summary, save_messages
from repositories.summaries import build_summary_from_messages, upsert_conversation_summary
from tasks.workflow_service import build_task_transition_chat_note, maybe_update_task_memory

router = APIRouter()


def resolve_mcp_settings(payload: GenerateRequest) -> MCPSettings | None:
    if payload.mcp is not None:
        if not payload.mcp.enabled:
            return payload.mcp
        return payload.mcp.model_copy(
            update={
                "server_script": payload.mcp.server_script or str(MCP_SERVER_SCRIPT),
                "wait_after_start_seconds": (
                    payload.mcp.wait_after_start_seconds
                    if payload.mcp.wait_after_start_seconds is not None
                    else MCP_WAIT_AFTER_START_SECONDS
                ),
                "tool_call_timeout_seconds": (
                    payload.mcp.tool_call_timeout_seconds
                    if payload.mcp.tool_call_timeout_seconds is not None
                    else MCP_TOOL_CALL_TIMEOUT_SECONDS
                ),
                "max_tool_roundtrips": (
                    payload.mcp.max_tool_roundtrips
                    if payload.mcp.max_tool_roundtrips is not None
                    else MCP_MAX_TOOL_ROUNDTRIPS
                ),
            }
        )

    if not MCP_ENABLED_BY_DEFAULT:
        return None

    return MCPSettings(
        enabled=True,
        server_script=str(MCP_SERVER_SCRIPT),
        wait_after_start_seconds=MCP_WAIT_AFTER_START_SECONDS,
        tool_call_timeout_seconds=MCP_TOOL_CALL_TIMEOUT_SECONDS,
        max_tool_roundtrips=MCP_MAX_TOOL_ROUNDTRIPS,
    )


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
    mcp_settings = resolve_mcp_settings(payload)

    response, mcp_execution = call_chat_completion_with_mcp(
        model=payload.model,
        messages=full_messages,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        top_p=payload.top_p,
        presence_penalty=payload.presence_penalty,
        frequency_penalty=payload.frequency_penalty,
        user_id=user_id,
        mcp_settings=mcp_settings,
    )

    content, finish_reason = extract_text_from_chat_completion(response)
    if not content.strip():
        raise HTTPException(status_code=502, detail="empty_model_response")

    ensure_conversation(conversation_id=conversation_id, user_id=user_id, model=payload.model)

    task_update = maybe_update_task_memory(
        conversation_id=conversation_id,
        branch_id=branch_id,
        task_id=payload.task_id,
        input_messages=payload.messages,
        assistant_response=content,
    )
    task_note = build_task_transition_chat_note(task_update)

    invariants = load_project_invariants()
    task_transition_error = task_update.get("task_transition_error")
    if task_transition_error:
        content = task_note or "System: task state was not changed."
        invariant_check = InvariantCheckResult(allowed=True)
    else:
        invariant_check = check_response_against_invariants(
            user_messages=payload.messages,
            assistant_response=content,
            model=payload.model,
            user_id=user_id,
        )
        if not invariant_check.allowed:
            content = build_invariant_refusal(invariant_check)

    if payload.show_task_transition_in_chat and task_note and not task_transition_error:
        content = f"{content.rstrip()}\n\n{task_note}"

    validate_output(content, payload.validation)
    usage = aggregate_usage(mcp_execution.responses)

    exchange_messages = [*payload.messages, ChatMessage(role="assistant", content=content)]
    save_messages(
        conversation_id=conversation_id,
        branch_id=branch_id,
        user_id=user_id,
        model=payload.model,
        messages=exchange_messages,
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
        task_state=task_update["task_state"],
        task_transition=task_update["task_transition"],
        task_transition_error=task_update["task_transition_error"],
        mcp_used=mcp_execution.used,
        mcp_server=mcp_execution.server_script,
        mcp_tools_offered=mcp_execution.tools_offered,
        mcp_tool_calls=mcp_execution.tool_calls,
    )
