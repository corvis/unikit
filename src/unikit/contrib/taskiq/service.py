#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import datetime
from typing import Any

from asgiref.sync import async_to_sync
from taskiq import AsyncBroker, AsyncTaskiqTask, TaskiqResult
from taskiq.depends.progress_tracker import TaskProgress
from taskiq.kicker import AsyncKicker

from unikit.contrib.taskiq.dto import (
    TASKIQ_LABEL_DATE_POSTED,
    TASKIQ_LABEL_SECURITY_CONTEXT,
    TASKIQ_LABEL_TASKNAME,
    TaskiqPostedTask,
)
from unikit.security_context import SecurityContextDto
from unikit.worker import JobStatus, PostedTask, TaskResult, WorkerService


class TaskiqWorkerService(WorkerService):
    """Implementation of WorkerService for Taskiq."""

    def __init__(self, broker: AsyncBroker):
        super().__init__()
        self.broker = broker

    async def aget_task_result(self, job_uuid: str) -> TaskResult:
        """Get task result by UUID."""
        taskiq_result: TaskiqResult | None = None
        try:
            taskiq_result = await self.broker.result_backend.get_result(job_uuid, with_logs=True)
        except Exception:
            progress = await self.broker.result_backend.get_progress(job_uuid)
            if progress:
                return self.__taskiq_progress_to_task_result(job_uuid, progress)
        if taskiq_result is None:
            return TaskResult(uuid=job_uuid, status=JobStatus.PENDING)
        return self.__taskiq_result_to_task_result(job_uuid, taskiq_result)

    async def await_for_task(self, job_uuid: str, timeout: datetime.timedelta | None = None) -> TaskResult:
        """Wait for task by UUID."""
        taskiq_result = await AsyncTaskiqTask(
            task_id=job_uuid,
            result_backend=self.broker.result_backend,
        ).wait_result(timeout=timeout.seconds if timeout else -1.0)
        return self.__taskiq_result_to_task_result(job_uuid, taskiq_result)

    async def apost_task(self, name: str, *args: Any, **kwargs: Any) -> PostedTask:
        """Post task by name."""
        try:
            task = self.broker.find_task(name)
            if task is None:
                raise ValueError(f"Task {name} is not a known task.")
            kicker = task.kicker()
        except ValueError:
            kicker = AsyncKicker(
                task_name=name,
                broker=self.broker,
                labels={},
            )

        kicked_task = await kicker.with_broker(self.broker).kiq(*args, **kwargs)
        return TaskiqPostedTask(
            uuid=kicked_task.task_id, timestamp=datetime.datetime.now(), task=kicked_task, task_name=name
        )

    def get_task_result(self, job_uuid: str) -> TaskResult:
        """Get task result by UUID."""
        return async_to_sync(self.aget_task_result)(job_uuid)

    def wait_for_task(self, job_uuid: str, timeout: datetime.timedelta | None = None) -> TaskResult:
        """Wait for task by UUID."""
        return async_to_sync(self.await_for_task)(job_uuid, timeout)

    def post_task(self, name: str, *args: Any, **kwargs: Any) -> PostedTask:
        """Post task by name."""
        return async_to_sync(self.apost_task)(name, *args, **kwargs)

    def supports_task(self, task_name: str) -> bool:
        """Check if the worker service supports the given task."""
        return self.broker.find_task(task_name) is not None

    def __taskiq_progress_to_task_result(self, uuid: str, progress: TaskProgress[dict[str, Any]]) -> TaskResult:
        labels = progress.meta.get("labels", {}) if progress.meta else {}
        time_posted_str = labels.get(TASKIQ_LABEL_DATE_POSTED)
        time_posted = datetime.datetime.fromisoformat(time_posted_str) if time_posted_str else None
        return TaskResult(
            uuid=uuid,
            status=JobStatus.RUNNING,
            result=progress.meta,
            timestamp=time_posted,
            task_name=labels.get(TASKIQ_LABEL_TASKNAME),
            security_context=SecurityContextDto.from_dict(labels.get(TASKIQ_LABEL_SECURITY_CONTEXT)),
        )

    def __taskiq_result_to_task_result(self, uuid: str, result: TaskiqResult) -> TaskResult:
        time_posted_str = result.labels.get(TASKIQ_LABEL_DATE_POSTED)
        time_posted = datetime.datetime.fromisoformat(time_posted_str) if time_posted_str else None
        return TaskResult(
            uuid=uuid,
            status=JobStatus.FAILED if result.is_err else JobStatus.SUCCESS,
            result=result.return_value,
            duration=datetime.timedelta(seconds=result.execution_time),
            timestamp=time_posted,
            log=result.log,
            error_message=str(result.error) if result.error else None,
            task_name=result.labels.get(TASKIQ_LABEL_TASKNAME),
            security_context=SecurityContextDto.from_dict(result.labels.get(TASKIQ_LABEL_SECURITY_CONTEXT)),
        )
