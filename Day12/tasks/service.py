from llm.schemas import ChatMessage
from memory.models import TaskMemory
from tasks.repository import get_task_memory, upsert_task_memory


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

    task.current_step = "Ожидание следующего шага пользователя"
    task.task_state["last_response_preview"] = assistant_response[:500]

    upsert_task_memory(conversation_id, branch_id, task)
    return True