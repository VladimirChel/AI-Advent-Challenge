from typing import Any

from llm.schemas import ChatMessage
from memory.models import ExpectedAction, TaskMemory, TaskStage, TaskStatus
from tasks.repository import add_task_transition, get_task_memory, upsert_task_memory
from tasks.state_machine import (
    InvalidTaskTransition,
    TaskEvent,
    apply_task_event,
    get_allowed_task_events,
)


def maybe_update_task_memory(
    *,
    conversation_id: str,
    branch_id: str,
    task_id: str | None,
    input_messages: list[ChatMessage],
    assistant_response: str,
) -> dict[str, Any]:
    if not task_id:
        return {
            "task_state": None,
            "task_transition": None,
            "task_transition_error": None,
        }

    existing = get_task_memory(conversation_id, branch_id, task_id)
    task = existing or TaskMemory(task_id=task_id)
    task.task_state = _normalize_task_state(task.task_state)

    user_messages = [m.content.strip() for m in input_messages if m.role == "user" and m.content.strip()]
    if user_messages and not task.goal:
        task.goal = user_messages[-1][:1000]

    if not task.plan:
        task.plan = [
            "Understand the request",
            "Collect the relevant context",
            "Prepare the response",
        ]

    event, reason, metadata = _infer_task_event(task, user_messages, assistant_response)
    if event is None:
        return {
            "task_state": _build_task_state_payload(task),
            "task_transition": {
                "applied": False,
                "event": None,
                "reason": reason,
            },
            "task_transition_error": None,
        }

    current_step, expected_action = _build_step_context(task, event)

    try:
        task, transition = apply_task_event(
            task,
            event,
            current_step=current_step,
            expected_action=expected_action,
            blocked_reason=reason,
            metadata=metadata,
        )
    except InvalidTaskTransition as exc:
        return {
            "task_state": _build_task_state_payload(task),
            "task_transition": {
                "applied": False,
                "event": event.value,
                "reason": reason,
            },
            "task_transition_error": {
                "code": "invalid_task_transition",
                "message": str(exc),
            },
        }

    task.task_state["last_response_preview"] = assistant_response[:500]

    upsert_task_memory(conversation_id, branch_id, task)
    add_task_transition(
        conversation_id,
        branch_id,
        task.task_id,
        from_status=transition["from_status"],
        to_status=transition["to_status"],
        from_stage=transition["from_stage"],
        to_stage=transition["to_stage"],
        event=transition["event"],
        reason=reason,
        payload={"state_version": transition["state_version"]},
    )
    return {
        "task_state": _build_task_state_payload(task),
        "task_transition": {
            "applied": True,
            **transition,
            "reason": reason,
        },
        "task_transition_error": None,
    }


def build_task_transition_chat_note(task_update: dict[str, Any] | None) -> str:
    if not task_update:
        return ""

    transition = task_update.get("task_transition") or {}
    error = task_update.get("task_transition_error") or {}
    task_state = task_update.get("task_state") or {}

    if error:
        message = error.get("message") or "Task transition is not allowed."
        return f"System: task state was not changed. {message}"

    if not transition.get("applied"):
        return ""

    from_stage = transition.get("from_stage")
    to_stage = transition.get("to_stage")
    event = transition.get("event")
    expected_action = task_state.get("expected_action")
    allowed_events = ", ".join(task_state.get("allowed_events") or [])

    if from_stage and to_stage and from_stage != to_stage:
        return (
            f"System: task stage changed from '{from_stage}' to '{to_stage}' "
            f"(event: {event}, next action: {expected_action}, allowed next events: {allowed_events})."
        )

    if event:
        return (
            f"System: task state updated "
            f"(stage: {task_state.get('stage')}, event: {event}, next action: {expected_action}, "
            f"allowed next events: {allowed_events})."
        )

    return ""


def _build_task_state_payload(task: TaskMemory) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "status": task.status.value if hasattr(task.status, "value") else str(task.status),
        "stage": task.stage.value if hasattr(task.stage, "value") else str(task.stage),
        "expected_action": task.expected_action.value if hasattr(task.expected_action, "value") else str(task.expected_action),
        "current_step": task.current_step,
        "blocked_reason": task.blocked_reason,
        "allowed_events": [event.value for event in get_allowed_task_events(task)],
    }


def _infer_task_event(
    task: TaskMemory,
    user_messages: list[str],
    assistant_response: str,
) -> tuple[TaskEvent | None, str | None, dict[str, Any] | None]:
    latest_user = user_messages[-1].lower() if user_messages else ""
    latest_response = assistant_response.lower()
    task_state = task.task_state if isinstance(task.task_state, dict) else {}
    plan_proposed = bool(task_state.get("plan_proposed"))
    plan_approved = bool(task_state.get("plan_approved"))

    if _is_cancel_request(latest_user):
        return TaskEvent.cancel, "user_requested_cancel", None

    if _is_pause_request(latest_user):
        return TaskEvent.pause, "user_requested_pause", None

    if task.status == TaskStatus.paused and latest_user:
        if _is_resume_request(latest_user):
            return TaskEvent.resume, "user_resumed_task", None
        return None, None, None

    if task.stage == TaskStage.validation:
        if _is_done_confirmation(latest_user):
            return TaskEvent.validation_passed, "user_confirmed_completion", None
        if _is_validation_failure(latest_user):
            return TaskEvent.validation_failed, "user_reported_validation_failure", None

    if task.stage == TaskStage.planning:
        if _is_plan_request(latest_user):
            if _looks_like_plan(latest_response):
                return (
                    TaskEvent.request_user_input,
                    "plan_proposed_waiting_for_approval",
                    {"plan_proposed": True, "plan_approved": False},
                )
            return TaskEvent.request_user_input, "planning_requires_user_input", None

        if _is_plan_approval(latest_user):
            if not plan_proposed:
                return TaskEvent.plan_ready, "plan_approval_requested_before_plan_exists", None
            return TaskEvent.plan_ready, "user_approved_plan", {"plan_approved": True}

        if _looks_finished(latest_response):
            return TaskEvent.submit_for_validation, "cannot_finish_task_before_plan_approval", None

        if _looks_execution_work(latest_response) and not plan_approved:
            return TaskEvent.execute_step, "cannot_start_implementation_before_plan_approval", None

        if _looks_like_plan(latest_response):
            return (
                TaskEvent.request_user_input,
                "plan_proposed_waiting_for_approval",
                {"plan_proposed": True, "plan_approved": False},
            )

        return TaskEvent.request_user_input, "planning_requires_user_input", None

    if task.stage == TaskStage.execution:
        if _is_done_confirmation(latest_user) or _looks_finished(latest_response):
            return TaskEvent.submit_for_validation, "candidate_ready_for_validation", None
        if _needs_user_input(latest_response):
            return TaskEvent.request_user_input, "assistant_waiting_for_user", None
        return TaskEvent.execute_step, None, None

    if task.stage == TaskStage.validation:
        if _looks_failed(latest_response):
            return TaskEvent.validation_failed, "validation_failed", None
        return TaskEvent.request_user_input, "validation_needs_confirmation", None

    return TaskEvent.validation_passed, "finalized", None


def _build_step_context(task: TaskMemory, event: TaskEvent) -> tuple[str, ExpectedAction]:
    if event == TaskEvent.pause:
        return "Task is paused", ExpectedAction.user_reply
    if event == TaskEvent.resume:
        return "Task execution resumed", ExpectedAction.assistant_continue
    if event == TaskEvent.request_user_input:
        if task.stage == TaskStage.validation:
            return "Waiting for validation result", ExpectedAction.user_reply
        return "Waiting for user input or plan approval", ExpectedAction.user_reply
    if event == TaskEvent.plan_ready:
        return "Plan approved, execution may start", ExpectedAction.assistant_continue
    if event == TaskEvent.execute_step:
        return "Execution is in progress", ExpectedAction.assistant_continue
    if event == TaskEvent.submit_for_validation:
        return "Result submitted for validation", ExpectedAction.run_validation
    if event == TaskEvent.validation_failed:
        return "Validation failed, more work is required", ExpectedAction.assistant_continue
    if event == TaskEvent.validation_passed:
        return "Task is completed", ExpectedAction.finish
    return "Task is cancelled", ExpectedAction.finish


def _needs_user_input(response: str) -> bool:
    return "?" in response or any(
        token in response
        for token in (
            "уточ",
            "какой",
            "нужен",
            "подтверд",
            "пришли",
            "approve",
            "confirm",
        )
    )


def _looks_finished(response: str) -> bool:
    return any(
        token in response
        for token in (
            "complete",
            "completed",
            "done",
            "готово",
            "выполнено",
            "завершено",
            "завершена",
            "проверено",
        )
    )


def _looks_failed(response: str) -> bool:
    return any(
        token in response
        for token in (
            "ошибка",
            "не прошло",
            "доработ",
            "исправ",
            "неверно",
            "failed",
        )
    )


def _is_pause_request(text: str) -> bool:
    return any(
        token in text
        for token in (
            "пауза",
            "на паузу",
            "поставь на паузу",
            "приостанов",
            "остановись",
            "pause",
        )
    )


def _is_resume_request(text: str) -> bool:
    return any(
        token in text
        for token in (
            "resume",
            "продолжай",
            "возобнови",
            "сними с паузы",
            "поехали дальше",
        )
    )


def _is_cancel_request(text: str) -> bool:
    return any(token in text for token in ("отмена", "отмени", "cancel", "прекрати"))


def _is_done_confirmation(text: str) -> bool:
    return any(
        token in text
        for token in (
            "готово",
            "заверши",
            "завершено",
            "завершена",
            "закончи",
            "выполнено",
            "подтверждаю",
            "всё ок",
            "все ок",
            "done",
            "complete",
        )
    )


def _is_validation_failure(text: str) -> bool:
    return any(
        token in text
        for token in (
            "не готово",
            "не выполнено",
            "неверно",
            "ошибка",
            "доработ",
            "исправ",
            "failed",
        )
    )


def _is_plan_approval(text: str) -> bool:
    return any(
        token in text
        for token in (
            "план утвержден",
            "план утверждён",
            "утверждаю план",
            "одобряю план",
            "план ок",
            "approve plan",
            "plan approved",
        )
    )


def _is_plan_request(text: str) -> bool:
    return any(
        token in text
        for token in (
            "напиши план",
            "составь план",
            "план из",
            "нужен план",
            "покажи план",
            "plan",
        )
    )


def _looks_like_plan(response: str) -> bool:
    return any(
        token in response
        for token in (
            "план",
            "step 1",
            "1.",
            "2.",
            "шаг 1",
            "шаг 2",
            "этап 1",
            "этап 2",
        )
    )


def _looks_execution_work(response: str) -> bool:
    return any(
        token in response
        for token in (
            "реализ",
            "имплемент",
            "написал код",
            "внес изменения",
            "обновил код",
            "implementation",
            "implemented",
            "updated the code",
            "made the changes",
        )
    )


def _normalize_task_state(task_state: dict[str, Any] | None) -> dict[str, Any]:
    state = dict(task_state or {})
    state.setdefault("plan_proposed", False)
    state.setdefault("plan_approved", False)
    state.setdefault("validation_requested", False)
    state.setdefault("validation_passed", False)
    state.setdefault("waiting_for_user", False)
    return state
