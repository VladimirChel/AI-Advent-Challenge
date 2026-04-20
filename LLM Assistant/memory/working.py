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

    task_state = task.task_state if isinstance(task.task_state, dict) else {}
    dialog_goal = str(task_state.get("dialog_goal", "") or "").strip()
    if dialog_goal and dialog_goal != (task.goal or "").strip():
        lines.append(f"- Chat goal: {dialog_goal}")

    clarified_points = [str(item).strip() for item in task_state.get("clarified_points", []) if str(item).strip()]
    if clarified_points:
        lines.append("- User clarified:")
        lines.extend(f"  - {item}" for item in clarified_points[:8])

    fixed_terms = [str(item).strip() for item in task_state.get("fixed_terms", []) if str(item).strip()]
    if fixed_terms:
        lines.append("- Fixed terms:")
        lines.extend(f"  - {item}" for item in fixed_terms[:8])

    open_questions = [str(item).strip() for item in task_state.get("open_questions", []) if str(item).strip()]
    if open_questions:
        lines.append("- Open questions:")
        lines.extend(f"  - {item}" for item in open_questions[:6])

    return ChatMessage(role="system", content="\n".join(lines))
