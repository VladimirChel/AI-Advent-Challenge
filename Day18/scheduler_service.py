from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from config import AGGREGATE_INTERVAL_SECONDS, COLLECT_INTERVAL_SECONDS, SUMMARY_INTERVAL_SECONDS
from repository_jobs import record_job_finish, record_job_start
from scheduler_jobs import aggregate_readings_job, collect_readings_job, generate_summary_job

logger = logging.getLogger("day18.scheduler")


JobCallable = Callable[[], dict[str, Any]]


@dataclass(slots=True)
class ScheduledJob:
    name: str
    interval_seconds: int
    handler: JobCallable
    task: asyncio.Task | None = None


class SchedulerService:
    def __init__(self) -> None:
        self._jobs = [
            ScheduledJob("collect_readings", COLLECT_INTERVAL_SECONDS, collect_readings_job),
            ScheduledJob("aggregate_readings", AGGREGATE_INTERVAL_SECONDS, aggregate_readings_job),
            ScheduledJob("generate_summary", SUMMARY_INTERVAL_SECONDS, generate_summary_job),
        ]
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        self._stopped.clear()
        for job in self._jobs:
            job.task = asyncio.create_task(self._run_job_loop(job), name=f"job:{job.name}")

    async def stop(self) -> None:
        self._stopped.set()
        for job in self._jobs:
            if job.task:
                job.task.cancel()
        for job in self._jobs:
            if job.task:
                try:
                    await job.task
                except asyncio.CancelledError:
                    pass

    async def _run_job_loop(self, job: ScheduledJob) -> None:
        while not self._stopped.is_set():
            started_at = datetime.now(timezone.utc)
            run_id = record_job_start(job.name)
            try:
                result = await asyncio.to_thread(job.handler)
                next_run_at = started_at + timedelta(seconds=job.interval_seconds)
                record_job_finish(
                    run_id,
                    job_name=job.name,
                    status="success",
                    details=result,
                    next_run_at=next_run_at,
                )
            except Exception as exc:  # pragma: no cover
                logger.exception("Scheduled job failed: %s", job.name)
                next_run_at = started_at + timedelta(seconds=job.interval_seconds)
                record_job_finish(
                    run_id,
                    job_name=job.name,
                    status="error",
                    details={},
                    error=str(exc),
                    next_run_at=next_run_at,
                )
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=job.interval_seconds)
            except asyncio.TimeoutError:
                continue
