from llm.schemas import ChatMessage
from memory.models import ExpectedAction, TaskMemory, TaskStage, TaskStatus
from tasks.repository import add_task_transition, get_task_memory, upsert_task_memory
from tasks.state_machine import InvalidTaskTransition, TaskEvent, apply_task_event


def maybe_update_task_memory(
    *,
    conversation_id: str,
    branch_id: str,
    task_id: str | None,
    input_messages: list[ChatMessage],
    assistant_response: str,
) -> bool:
    if not task_id:
        return False

    existing = get_task_memory(conversation_id, branch_id, task_id)
    task = existing or TaskMemory(task_id=task_id)

    user_messages = [m.content.strip() for m in input_messages if m.role == "user" and m.content.strip()]
    if user_messages and not task.goal:
        task.goal = user_messages[-1][:1000]

    if not task.plan:
        task.plan = [
            "Понять запрос",
            "Собрать контекст",
            "Подготовить ответ",
        ]

    event, reason = _infer_task_event(task, user_messages, assistant_response)
    current_step, expected_action = _build_step_context(task, event)

    try:
        task, transition = apply_task_event(
            task,
            event,
            current_step=current_step,
            expected_action=expected_action,
            blocked_reason=reason,
        )
    except InvalidTaskTransition:
        return False

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
    return True


def _infer_task_event(
    task: TaskMemory,
    user_messages: list[str],
    assistant_response: str,
) -> tuple[TaskEvent, str | None]:
    latest_user = user_messages[-1].lower() if user_messages else ""
    latest_response = assistant_response.lower()

    if _is_cancel_request(latest_user):
        return TaskEvent.cancel, "user_requested_cancel"

    if _is_pause_request(latest_user):
        return TaskEvent.pause, "user_requested_pause"

    if task.status == TaskStatus.paused and latest_user:
        return TaskEvent.resume, "user_resumed_task"

    if task.stage == TaskStage.validation:
        if _is_done_confirmation(latest_user):
            return TaskEvent.validation_passed, "user_confirmed_completion"
        if _is_validation_failure(latest_user):
            return TaskEvent.validation_failed, "user_reported_validation_failure"

    if _needs_user_input(latest_response):
        return TaskEvent.request_user_input, "assistant_waiting_for_user"

    if task.stage == TaskStage.planning:
        return TaskEvent.plan_ready, None

    if task.stage == TaskStage.execution:
        if _is_done_confirmation(latest_user) or _looks_finished(latest_response):
            return TaskEvent.submit_for_validation, "candidate_ready_for_validation"
        return TaskEvent.execute_step, None

    if task.stage == TaskStage.validation:
        if _looks_failed(latest_response):
            return TaskEvent.validation_failed, "validation_failed"
        if _looks_finished(latest_response):
            return TaskEvent.validation_passed, "validation_passed"
        return TaskEvent.request_user_input, "validation_needs_confirmation"

    return TaskEvent.validation_passed, "finalized"


def _build_step_context(task: TaskMemory, event: TaskEvent) -> tuple[str, ExpectedAction]:
    if event == TaskEvent.pause:
        return "Задача поставлена на паузу", ExpectedAction.user_reply
    if event == TaskEvent.resume:
        return "Работа по задаче возобновлена", ExpectedAction.assistant_continue
    if event == TaskEvent.request_user_input:
        if task.stage == TaskStage.validation:
            return "Ожидание подтверждения результата", ExpectedAction.user_reply
        return "Ожидание уточнения от пользователя", ExpectedAction.user_reply
    if event == TaskEvent.plan_ready:
        return "План готов, можно переходить к выполнению", ExpectedAction.assistant_continue
    if event == TaskEvent.execute_step:
        return "Выполняется текущий шаг задачи", ExpectedAction.assistant_continue
    if event == TaskEvent.submit_for_validation:
        return "Результат передан на проверку", ExpectedAction.run_validation
    if event == TaskEvent.validation_failed:
        return "Проверка не пройдена, нужно доработать результат", ExpectedAction.assistant_continue
    if event == TaskEvent.validation_passed:
        return "Задача завершена", ExpectedAction.finish
    return "Задача отменена", ExpectedAction.finish


def _needs_user_input(response: str) -> bool:
    return "?" in response or any(token in response for token in ("уточ", "какой", "нужен", "подтверд", "пришли"))


def _looks_finished(response: str) -> bool:
    return any(token in response for token in ("готово", "выполнено", "завершено", "complete", "completed", "проверено"))


def _looks_failed(response: str) -> bool:
    return any(token in response for token in ("ошибка", "не прошло", "доработ", "исправ", "неверно", "failed"))


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


def _is_cancel_request(text: str) -> bool:
    return any(token in text for token in ("отмена", "отмени", "cancel", "прекрати"))


def _is_done_confirmation(text: str) -> bool:
    return any(
        token in text
        for token in (
            "готово",
            "заверши",
            "завершено",
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
