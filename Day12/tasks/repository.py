import json
from datetime import timezone
from db import get_db_connection
from memory.models import TaskMemory


def get_task_memory(conversation_id: str, branch_id: str, task_id: str) -> TaskMemory | None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT task_id, status, stage, goal, current_step, expected_action, blocked_reason,
                       plan, completed_steps, constraints, artifacts, state_version, last_event,
                       task_state, created_at, updated_at
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
        stage=row[2],
        goal=row[3],
        current_step=row[4],
        expected_action=row[5],
        blocked_reason=row[6],
        plan=row[7] or [],
        completed_steps=row[8] or [],
        constraints=row[9] or [],
        artifacts=row[10] or [],
        state_version=row[11] or 1,
        last_event=row[12],
        task_state=row[13] or {},
        created_at=row[14].replace(tzinfo=timezone.utc).isoformat() if row[14] else None,
        updated_at=row[15].replace(tzinfo=timezone.utc).isoformat() if row[15] else None,
    )


def upsert_task_memory(conversation_id: str, branch_id: str, task: TaskMemory) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO task_memory (
                    conversation_id, branch_id, task_id, status, stage, goal, current_step,
                    expected_action, blocked_reason, plan, completed_steps, constraints, artifacts,
                    state_version, last_event, task_state,
                    created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb, NOW(), NOW()
                )
                ON CONFLICT (conversation_id, branch_id, task_id)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    stage = EXCLUDED.stage,
                    goal = EXCLUDED.goal,
                    current_step = EXCLUDED.current_step,
                    expected_action = EXCLUDED.expected_action,
                    blocked_reason = EXCLUDED.blocked_reason,
                    plan = EXCLUDED.plan,
                    completed_steps = EXCLUDED.completed_steps,
                    constraints = EXCLUDED.constraints,
                    artifacts = EXCLUDED.artifacts,
                    state_version = EXCLUDED.state_version,
                    last_event = EXCLUDED.last_event,
                    task_state = EXCLUDED.task_state,
                    updated_at = NOW()
                """,
                (
                    conversation_id,
                    branch_id,
                    task.task_id,
                    task.status.value if hasattr(task.status, "value") else str(task.status),
                    task.stage.value if hasattr(task.stage, "value") else str(task.stage),
                    task.goal,
                    task.current_step,
                    task.expected_action.value if hasattr(task.expected_action, "value") else str(task.expected_action),
                    task.blocked_reason,
                    json.dumps(task.plan, ensure_ascii=False),
                    json.dumps(task.completed_steps, ensure_ascii=False),
                    json.dumps(task.constraints, ensure_ascii=False),
                    json.dumps(task.artifacts, ensure_ascii=False),
                    task.state_version,
                    task.last_event,
                    json.dumps(task.task_state, ensure_ascii=False),
                ),
            )
        conn.commit()


def add_task_transition(
    conversation_id: str,
    branch_id: str,
    task_id: str,
    *,
    from_status: str | None,
    to_status: str,
    from_stage: str | None,
    to_stage: str | None,
    event: str,
    reason: str | None = None,
    payload: dict | None = None,
) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO task_transitions (
                    conversation_id, branch_id, task_id, from_status, to_status,
                    from_stage, to_stage, event, reason, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    conversation_id,
                    branch_id,
                    task_id,
                    from_status,
                    to_status,
                    from_stage,
                    to_stage,
                    event,
                    reason,
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )
        conn.commit()
