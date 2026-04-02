from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Any

from memory.models import ExpectedAction, TaskMemory, TaskStage, TaskStatus


class TaskEvent(str, Enum):
    plan_ready = "plan_ready"
    execute_step = "execute_step"
    request_user_input = "request_user_input"
    submit_for_validation = "submit_for_validation"
    validation_passed = "validation_passed"
    validation_failed = "validation_failed"
    pause = "pause"
    resume = "resume"
    cancel = "cancel"


class InvalidTaskTransition(ValueError):
    pass


_STATUS_TRANSITIONS: dict[TaskStatus, dict[TaskEvent, TaskStatus]] = {
    TaskStatus.active: {
        TaskEvent.plan_ready: TaskStatus.active,
        TaskEvent.execute_step: TaskStatus.active,
        TaskEvent.request_user_input: TaskStatus.active,
        TaskEvent.submit_for_validation: TaskStatus.active,
        TaskEvent.validation_passed: TaskStatus.done,
        TaskEvent.validation_failed: TaskStatus.active,
        TaskEvent.pause: TaskStatus.paused,
        TaskEvent.cancel: TaskStatus.cancelled,
    },
    TaskStatus.paused: {
        TaskEvent.resume: TaskStatus.active,
        TaskEvent.cancel: TaskStatus.cancelled,
    },
    TaskStatus.done: {},
    TaskStatus.cancelled: {},
}

_STAGE_TRANSITIONS: dict[TaskStage, dict[TaskEvent, TaskStage]] = {
    TaskStage.planning: {
        TaskEvent.request_user_input: TaskStage.planning,
        TaskEvent.plan_ready: TaskStage.execution,
        TaskEvent.pause: TaskStage.planning,
        TaskEvent.cancel: TaskStage.planning,
    },
    TaskStage.execution: {
        TaskEvent.execute_step: TaskStage.execution,
        TaskEvent.request_user_input: TaskStage.execution,
        TaskEvent.submit_for_validation: TaskStage.validation,
        TaskEvent.pause: TaskStage.execution,
        TaskEvent.cancel: TaskStage.execution,
    },
    TaskStage.validation: {
        TaskEvent.request_user_input: TaskStage.validation,
        TaskEvent.validation_failed: TaskStage.execution,
        TaskEvent.validation_passed: TaskStage.done,
        TaskEvent.pause: TaskStage.validation,
        TaskEvent.cancel: TaskStage.validation,
    },
    TaskStage.done: {},
}

_EXPECTED_ACTION_BY_EVENT: dict[TaskEvent, ExpectedAction] = {
    TaskEvent.plan_ready: ExpectedAction.assistant_continue,
    TaskEvent.execute_step: ExpectedAction.assistant_continue,
    TaskEvent.request_user_input: ExpectedAction.user_reply,
    TaskEvent.submit_for_validation: ExpectedAction.run_validation,
    TaskEvent.validation_passed: ExpectedAction.finish,
    TaskEvent.validation_failed: ExpectedAction.assistant_continue,
    TaskEvent.pause: ExpectedAction.user_reply,
    TaskEvent.resume: ExpectedAction.assistant_continue,
    TaskEvent.cancel: ExpectedAction.finish,
}


def apply_task_event(
    task: TaskMemory,
    event: TaskEvent,
    *,
    current_step: str | None = None,
    expected_action: ExpectedAction | None = None,
    blocked_reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[TaskMemory, dict[str, Any]]:
    allowed_status = _STATUS_TRANSITIONS.get(task.status, {})
    if event not in allowed_status:
        raise InvalidTaskTransition(f"Event '{event.value}' is not allowed from status '{task.status.value}'")

    if event == TaskEvent.resume:
        target_stage = task.task_state.get("resume_stage") or TaskStage.execution.value
        try:
            next_stage = TaskStage(target_stage)
        except ValueError as exc:
            raise InvalidTaskTransition(f"Unknown resume stage '{target_stage}'") from exc
    else:
        allowed_stage = _STAGE_TRANSITIONS.get(task.stage, {})
        if event not in allowed_stage:
            raise InvalidTaskTransition(f"Event '{event.value}' is not allowed from stage '{task.stage.value}'")
        next_stage = allowed_stage[event]

    updated = task.model_copy(deep=True)
    previous_status = updated.status
    previous_stage = updated.stage

    updated.status = allowed_status[event]
    updated.stage = next_stage
    updated.last_event = event.value
    updated.state_version += 1

    if current_step is not None:
        updated.current_step = current_step

    updated.expected_action = expected_action or _EXPECTED_ACTION_BY_EVENT[event]

    updated.task_state = deepcopy(updated.task_state)
    updated.task_state["waiting_for_user"] = updated.expected_action == ExpectedAction.user_reply

    if event == TaskEvent.pause:
        updated.task_state["resume_stage"] = previous_stage.value
        updated.blocked_reason = blocked_reason or updated.blocked_reason
    else:
        updated.task_state.pop("resume_stage", None)
        if event != TaskEvent.request_user_input:
            updated.blocked_reason = None

    if event == TaskEvent.request_user_input and blocked_reason:
        updated.blocked_reason = blocked_reason

    if metadata:
        existing_metadata = updated.task_state.get("metadata")
        if not isinstance(existing_metadata, dict):
            existing_metadata = {}
        updated.task_state["metadata"] = {**existing_metadata, **metadata}

    transition = {
        "from_status": previous_status.value,
        "to_status": updated.status.value,
        "from_stage": previous_stage.value,
        "to_stage": updated.stage.value,
        "event": event.value,
        "state_version": updated.state_version,
    }
    return updated, transition
