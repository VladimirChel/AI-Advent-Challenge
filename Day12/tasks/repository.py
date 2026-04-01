import json
from datetime import timezone
from db import get_db_connection
from memory.models import TaskMemory


def get_task_memory(conversation_id: str, branch_id: str, task_id: str) -> TaskMemory | None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT task_id, status, goal, current_step, plan, completed_steps,
                       constraints, artifacts, task_state, created_at, updated_at
                FROM task_memory
                WHERE conversation_id = %s AND branch_id = %s AND task_id = %s
                """,
                (conversation_id, branch_id, task_id),
            )
            row = cur.fetchone()

    if not row:
        return None

    return TaskMemory(
        task_id=row[0],
        status=row[1],
        goal=row[2],
        current_step=row[3],
        plan=row[4] or [],
        completed_steps=row[5] or [],
        constraints=row[6] or [],
        artifacts=row[7] or [],
        task_state=row[8] or {},
        created_at=row[9].replace(tzinfo=timezone.utc).isoformat() if row[9] else None,
        updated_at=row[10].replace(tzinfo=timezone.utc).isoformat() if row[10] else None,
    )


def upsert_task_memory(conversation_id: str, branch_id: str, task: TaskMemory) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO task_memory (
                    conversation_id, branch_id, task_id, status, goal, current_step,
                    plan, completed_steps, constraints, artifacts, task_state,
                    created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, NOW(), NOW())
                ON CONFLICT (conversation_id, branch_id, task_id)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    goal = EXCLUDED.goal,
                    current_step = EXCLUDED.current_step,
                    plan = EXCLUDED.plan,
                    completed_steps = EXCLUDED.completed_steps,
                    constraints = EXCLUDED.constraints,
                    artifacts = EXCLUDED.artifacts,
                    task_state = EXCLUDED.task_state,
                    updated_at = NOW()
                """,
                (
                    conversation_id,
                    branch_id,
                    task.task_id,
                    task.status.value if hasattr(task.status, "value") else str(task.status),
                    task.goal,
                    task.current_step,
                    json.dumps(task.plan, ensure_ascii=False),
                    json.dumps(task.completed_steps, ensure_ascii=False),
                    json.dumps(task.constraints, ensure_ascii=False),
                    json.dumps(task.artifacts, ensure_ascii=False),
                    json.dumps(task.task_state, ensure_ascii=False),
                ),
            )
        conn.commit()