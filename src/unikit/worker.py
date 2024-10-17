#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
import dataclasses
import datetime
from enum import StrEnum
from typing import Any

from unikit.abstract import Abstract, AbstractMeta
from unikit.registry import Registry


class JobStatus(StrEnum):
    """Enumeration of possible job statuses."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclasses.dataclass(kw_only=True, frozen=True)
class PostedTask:
    """DTO for posted task."""

    uuid: str
    timestamp: datetime.datetime


@dataclasses.dataclass(kw_only=True)
class TaskResult:
    """DTO for task result."""

    uuid: str
    status: JobStatus
    result: Any = None
    timestamp: datetime.datetime | None = None
    error_message: str | None = None
    log: str | None = None
    duration: datetime.timedelta | None = None


class WorkerService(Abstract, metaclass=AbstractMeta):
    """Worker service interface."""

    def prepare_for_serialization(self, obj: Any) -> Any:
        """Prepare the object for serialization."""
        if hasattr("to_dict", obj):
            return obj.to_dict()
        elif hasattr("serialize", obj):
            return obj.serialize()
        else:
            return obj

    @abc.abstractmethod
    def get_task_result(self, job_uuid: str) -> TaskResult:
        """Get the task result by the given job UUID."""
        pass

    @abc.abstractmethod
    async def aget_task_result(self, job_uuid: str) -> TaskResult:
        """Get the task result by the given job UUID asynchronously."""
        pass

    @abc.abstractmethod
    def wait_for_task(self, job_uuid: str, timeout: datetime.timedelta | None = None) -> TaskResult:
        """Wait for the task by the given job UUID."""
        pass

    @abc.abstractmethod
    async def await_for_task(self, job_uuid: str, timeout: datetime.timedelta | None = None) -> TaskResult:
        """Wait for the task by the given job UUID asynchronously."""
        pass

    @abc.abstractmethod
    def post_task(self, name: str, *args: Any, **kwargs: Any) -> PostedTask:
        """Post the task by the given name."""
        pass

    @abc.abstractmethod
    async def apost_task(self, name: str, *args: Any, **kwargs: Any) -> PostedTask:
        """Post the task by the given name asynchronously."""
        pass

    @abc.abstractmethod
    def supports_task(self, task_name: str) -> bool:
        """
        Check if the worker service supports the given task.

        :param task_name: name of the task
        :return: True if the worker service supports the task, False otherwise
        """
        pass


class WorkerServiceRegistry(Registry[str, WorkerService]):
    """A registry for WorkerService objects."""

    def get_for_task(self, task_name: str) -> WorkerService:
        """
        Get the worker service for the given task name.

        :param task_name: name of the task
        :return: worker service for the task
        """
        for ws in self.get_all():
            ws.supports_task(task_name)
            return ws
        raise KeyError(f"Worker service for task `{task_name}` not found in registry.")

    def get_for_task_or_default(self, task_name: str) -> WorkerService:
        """Get the worker service for the given task name or default."""
        try:
            return self.get_for_task(task_name)
        except KeyError:
            return self.get_default()

    def get_default(self) -> WorkerService:
        """
        Get the default worker service.

        :return: default worker service
        """
        return next(self.get_all())

    def get_task_result(self, job_uuid: str) -> TaskResult:
        """Get the task result by the given job UUID."""
        return self.get_default().get_task_result(job_uuid)

    async def aget_task_result(self, job_uuid: str) -> TaskResult:
        """Get the task result by the given job UUID asynchronously."""
        return await self.get_default().aget_task_result(job_uuid)

    def wait_for_task(self, job_uuid: str, timeout: datetime.timedelta | None = None) -> TaskResult:
        """Wait for the task by the given job UUID."""
        return self.get_default().wait_for_task(job_uuid, timeout)

    async def await_for_task(self, job_uuid: str, timeout: datetime.timedelta | None = None) -> TaskResult:
        """Wait for the task by the given job UUID asynchronously."""
        return await self.get_default().await_for_task(job_uuid, timeout)

    def post_task(self, name: str, *args: Any, fallback_to_default: bool = True, **kwargs: Any) -> PostedTask:
        """Post the task by the given name."""
        service = self.get_for_task_or_default(name) if fallback_to_default else self.get_for_task(name)
        return service.post_task(name, *args, **kwargs)

    async def apost_task(self, name: str, *args: Any, fallback_to_default: bool = True, **kwargs: Any) -> PostedTask:
        """Post the task by the given name asynchronously."""
        service = self.get_for_task_or_default(name) if fallback_to_default else self.get_for_task(name)
        return await service.apost_task(name, *args, **kwargs)
