import time
import uuid

from fastapi import APIRouter, Depends, HTTPException

from config import (
    MEMORY_ENABLED,
    MCP_ENABLED,
    MCP_MAX_TOOL_ROUNDTRIPS,
    MCP_SERVER_SCRIPT,
    MCP_SERVER_SCRIPTS,
    MCP_TOOL_CALL_TIMEOUT_SECONDS,
    MCP_WAIT_AFTER_START_SECONDS,
    SUMMARY_MAX_INPUT_MESSAGES,
    TASK_AUTO_ID_FOR_RAG_CHAT,
)
from auth.dependencies import get_current_user
from auth.schemas import PublicUser
from invariants.schemas import InvariantCheckResult
from invariants.service import (
    build_invariant_refusal,
    check_response_against_invariants,
    load_project_invariants,
)
from llm.client import (
    aggregate_usage,
    call_chat_completion_with_mcp,
    extract_text_from_chat_completion,
    resolve_provider_id,
)
from llm.schemas import ChatMessage, GenerateRequest, GenerateResponse, MCPServerConfig, MCPSettings
from llm.service import validate_output
from memory.models import MemoryPolicy
from memory.orchestrator import build_agent_context, materialize_context_messages
from project_help import (
    HELP_MODE,
    build_project_help_system_message,
    HYBRID_ROUTE,
    MCP_ROUTE,
    resolve_help_mode,
    resolve_project_mcp_settings,
    resolve_project_rag_settings,
)
from rag.service import (
    build_day22_rag_context,
    build_rag_citations,
    build_rag_sources,
    build_task_aware_rag_query,
    enforce_rag_response_contract,
    resolve_rag_settings,
)
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

        payload_servers = _normalize_payload_mcp_servers(payload.mcp)
        if payload_servers:
            return payload.mcp.model_copy(
                update={
                    "servers": payload_servers,
                    "max_tool_roundtrips": (
                        payload.mcp.max_tool_roundtrips
                        if payload.mcp.max_tool_roundtrips is not None
                        else MCP_MAX_TOOL_ROUNDTRIPS
                    ),
                }
            )

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

    if not MCP_ENABLED:
        return None

    default_servers = _build_default_mcp_servers()
    if default_servers:
        return MCPSettings(
            enabled=True,
            servers=default_servers,
            max_tool_roundtrips=MCP_MAX_TOOL_ROUNDTRIPS,
        )

    return MCPSettings(
        enabled=True,
        server_script=str(MCP_SERVER_SCRIPT),
        wait_after_start_seconds=MCP_WAIT_AFTER_START_SECONDS,
        tool_call_timeout_seconds=MCP_TOOL_CALL_TIMEOUT_SECONDS,
        max_tool_roundtrips=MCP_MAX_TOOL_ROUNDTRIPS,
    )


def _normalize_payload_mcp_servers(settings: MCPSettings) -> list[MCPServerConfig]:
    result: list[MCPServerConfig] = []
    for index, server in enumerate(settings.servers, start=1):
        if not server.enabled or not server.server_script:
            continue
        result.append(
            server.model_copy(
                update={
                    "id": server.id or f"server_{index}",
                    "wait_after_start_seconds": (
                        server.wait_after_start_seconds
                        if server.wait_after_start_seconds is not None
                        else settings.wait_after_start_seconds
                        if settings.wait_after_start_seconds is not None
                        else MCP_WAIT_AFTER_START_SECONDS
                    ),
                    "tool_call_timeout_seconds": (
                        server.tool_call_timeout_seconds
                        if server.tool_call_timeout_seconds is not None
                        else settings.tool_call_timeout_seconds
                        if settings.tool_call_timeout_seconds is not None
                        else MCP_TOOL_CALL_TIMEOUT_SECONDS
                    ),
                }
            )
        )
    return result


def _build_default_mcp_servers() -> list[MCPServerConfig]:
    scripts = MCP_SERVER_SCRIPTS or [MCP_SERVER_SCRIPT]
    result: list[MCPServerConfig] = []
    for index, script in enumerate(scripts, start=1):
        result.append(
            MCPServerConfig(
                id=f"server_{index}",
                server_script=str(script),
                wait_after_start_seconds=MCP_WAIT_AFTER_START_SECONDS,
                tool_call_timeout_seconds=MCP_TOOL_CALL_TIMEOUT_SECONDS,
            )
        )
    return result


@router.post("/generate", response_model=GenerateResponse)
def generate(payload: GenerateRequest, current_user: PublicUser = Depends(get_current_user)) -> GenerateResponse:
    request_id = str(uuid.uuid4())
    started = time.perf_counter()

    conversation_id = payload.conversation_id or str(uuid.uuid4())
    branch_id = payload.branch_id.strip() or "main"
    user_id = current_user.id
    effective_provider_id = resolve_provider_id(payload.provider_id)

    if MEMORY_ENABLED:
        assert_conversation_access(conversation_id=conversation_id, user_id=user_id)

    policy = MemoryPolicy()
    effective_task_id = payload.task_id
    if TASK_AUTO_ID_FOR_RAG_CHAT and payload.chat_mode == "rag_task_chat" and not effective_task_id:
        effective_task_id = conversation_id

    agent_ctx = build_agent_context(
        user_id=user_id,
        conversation_id=conversation_id,
        branch_id=branch_id,
        task_id=effective_task_id,
        policy=policy,
        live_messages=payload.messages,
    )
    help_state = resolve_help_mode(
        short_term_messages=agent_ctx.short_term_messages,
        live_messages=payload.messages,
        project=payload.project,
    )
    effective_chat_mode = HELP_MODE if help_state.active_mode == HELP_MODE else payload.chat_mode

    if help_state.immediate_response is not None:
        content = help_state.immediate_response
        finish_reason = "stop"
        usage = {}
        rag_result = build_day22_rag_context("", None)
        mcp_execution = resolve_mcp_empty_execution()
        task_update = {
            "task_state": None,
            "task_transition": None,
            "task_transition_error": None,
        }
        if MEMORY_ENABLED:
            ensure_conversation(conversation_id=conversation_id, user_id=user_id, model=payload.model)
            save_messages(
                conversation_id=conversation_id,
                branch_id=branch_id,
                user_id=user_id,
                model=payload.model,
                messages=[*payload.messages, ChatMessage(role="assistant", content=content)],
            )

        latency_ms = int((time.perf_counter() - started) * 1000)
        return GenerateResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            branch_id=branch_id,
            task_id=effective_task_id,
            provider_id=effective_provider_id,
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
            rag_used=False,
            rag_chunks_used=0,
            rag_strategy=None,
            rag_chunks=[],
            sources=[],
            citations=[],
            project_invariants_used=False,
            project_invariants_count=0,
            invariant_check_passed=True,
            invariant_violations=[],
            task_state=task_update["task_state"],
            task_transition=task_update["task_transition"],
            task_transition_error=task_update["task_transition_error"],
            active_mode=help_state.active_mode,
            project_id=help_state.project_id,
            project_help_route=help_state.route if help_state.active_mode == HELP_MODE else None,
            mcp_used=False,
            mcp_server=None,
            mcp_servers=[],
            mcp_tools_offered=0,
            mcp_available_tools=[],
            mcp_tool_calls=[],
            mcp_tool_trace=[],
        )
    else:
        help_route = help_state.route if help_state.active_mode == HELP_MODE else RAG_ROUTE_FALLBACK
        effective_rag_payload = resolve_project_rag_settings(
            payload.project,
            payload.rag,
            help_mode_active=help_state.active_mode == HELP_MODE and help_route in {RAG_ROUTE_FALLBACK, HYBRID_ROUTE},
        )
        rag_settings = resolve_rag_settings(effective_rag_payload)
        latest_user_message = "\n".join(m.content for m in help_state.rewritten_live_messages if m.role == "user").strip()
        if rag_settings is not None:
            rag_question = build_task_aware_rag_query(latest_user_message, agent_ctx.working_memory)
            rag_result = build_day22_rag_context(rag_question, rag_settings)
        else:
            rag_result = build_day22_rag_context("", None)

        full_messages = [*materialize_context_messages(agent_ctx)]
        if help_state.active_mode == HELP_MODE:
            help_system_message = build_project_help_system_message(payload.project)
            if help_system_message:
                full_messages.append(help_system_message)
        if rag_result.context_message:
            full_messages.append(rag_result.context_message)
        full_messages.extend(help_state.rewritten_live_messages)

        project_mcp_settings = resolve_project_mcp_settings(
            payload.project,
            payload.mcp,
            help_mode_active=help_state.active_mode == HELP_MODE and help_route in {MCP_ROUTE, HYBRID_ROUTE},
        )
        mcp_settings = resolve_mcp_settings(
            payload.model_copy(
                update={
                    "chat_mode": effective_chat_mode,
                    "messages": help_state.rewritten_live_messages,
                    "mcp": project_mcp_settings,
                }
            )
        )

        response, mcp_execution = call_chat_completion_with_mcp(
            provider_id=effective_provider_id,
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

        if MEMORY_ENABLED:
            ensure_conversation(conversation_id=conversation_id, user_id=user_id, model=payload.model)
            task_update = maybe_update_task_memory(
                conversation_id=conversation_id,
                branch_id=branch_id,
                task_id=effective_task_id,
                chat_mode=effective_chat_mode,
                input_messages=help_state.rewritten_live_messages,
                assistant_response=content,
            )
        else:
            task_update = {
                "task_state": None,
                "task_transition": None,
                "task_transition_error": None,
            }
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
            provider_id=effective_provider_id,
            user_id=user_id,
        )
        if not invariant_check.allowed:
            content = build_invariant_refusal(invariant_check)

    if rag_result.enabled:
        content = enforce_rag_response_contract(content, rag_result)

    if payload.show_task_transition_in_chat and task_note and not task_transition_error:
        content = f"{content.rstrip()}\n\n{task_note}"

    validate_output(content, payload.validation)
    usage = aggregate_usage(mcp_execution.responses)

    if MEMORY_ENABLED:
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
            limit=SUMMARY_MAX_INPUT_MESSAGES,
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
        task_id=effective_task_id,
        provider_id=effective_provider_id,
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
        rag_used=bool(rag_result.chunks),
        rag_chunks_used=len(rag_result.chunks or []),
        rag_strategy=rag_result.strategy,
        rag_chunks=rag_result.chunks or [],
        sources=build_rag_sources(rag_result.chunks or []),
        citations=build_rag_citations(rag_result.chunks or []),
        project_invariants_used=bool(invariants.invariants),
        project_invariants_count=len(invariants.invariants),
        invariant_check_passed=invariant_check.allowed,
        invariant_violations=[item.id for item in invariant_check.violations],
        task_state=task_update["task_state"],
        task_transition=task_update["task_transition"],
        task_transition_error=task_update["task_transition_error"],
        active_mode=help_state.active_mode,
        project_id=help_state.project_id,
        project_help_route=help_state.route if help_state.active_mode == HELP_MODE else None,
        mcp_used=mcp_execution.used,
        mcp_server=mcp_execution.server_script,
        mcp_servers=mcp_execution.servers,
        mcp_tools_offered=mcp_execution.tools_offered,
        mcp_available_tools=mcp_execution.available_tools,
        mcp_tool_calls=mcp_execution.tool_calls,
        mcp_tool_trace=mcp_execution.tool_trace,
    )


def resolve_mcp_empty_execution():
    from llm.client import MCPExecutionResult

    return MCPExecutionResult()


RAG_ROUTE_FALLBACK = "rag"
