#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import datetime
from typing import Any

from asgiref.sync import async_to_sync
from taskiq import AsyncBroker, AsyncTaskiqTask, TaskiqResult
from taskiq.kicker import AsyncKicker

from unikit.contrib.taskiq.dto import TaskiqPostedTask
from unikit.worker import JobStatus, PostedTask, TaskResult, WorkerService


class TaskiqWorkerService(WorkerService):
    """Implementation of WorkerService for Taskiq."""

    def __init__(self, broker: AsyncBroker):
        super().__init__()
        self.broker = broker

    async def aget_task_result(self, job_uuid: str) -> TaskResult:
        """Get task result by UUID."""
        taskiq_result = await AsyncTaskiqTask(
            task_id=job_uuid,
            result_backend=self.broker.result_backend,
        ).get_result()
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
        return TaskiqPostedTask(uuid=kicked_task.task_id, timestamp=datetime.datetime.now(), task=kicked_task)

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

    def __taskiq_result_to_task_result(self, uuid: str, result: TaskiqResult) -> TaskResult:
        return TaskResult(
            uuid=uuid,
            status=JobStatus.FAILED if result.is_err else JobStatus.SUCCESS,
            result=result.return_value,
            duration=datetime.timedelta(seconds=result.execution_time),
            log=result.log,
            error_message=str(result.error) if result.error else None,
        )
