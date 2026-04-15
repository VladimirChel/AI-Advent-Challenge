import json
from llm.schemas import ChatMessage
from memory.models import TaskMemory


def build_working_memory_message(task: TaskMemory | None) -> ChatMessage | None:
    if not task:
        return None

    lines = ["Рабочая память текущей задачи:"]
    if task.goal:
        lines.append(f"- Цель: {task.goal}")
    if task.current_step:
        lines.append(f"- Текущий шаг: {task.current_step}")
    if task.plan:
        lines.append("- План:")
        lines.extend(f"  - {s}" for s in task.plan)
    if task.completed_steps:
        lines.append("- Выполнено:")
        lines.extend(f"  - {s}" for s in task.completed_steps)
    if task.constraints:
        lines.append("- Ограничения:")
        lines.extend(f"  - {s}" for s in task.constraints)
    if task.artifacts:
        lines.append("- Артефакты:")
        for artifact in task.artifacts[:5]:
            lines.append(f"  - {json.dumps(artifact, ensure_ascii=False)}")

    return ChatMessage(role="system", content="\n".join(lines))