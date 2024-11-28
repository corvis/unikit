#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
from contextvars import ContextVar
import dataclasses
import datetime
from enum import StrEnum
import logging
from typing import Any

from injector import Injector, Provider

from unikit.abstract import Abstract, AbstractMeta
from unikit.di import root_container
from unikit.progress import ProgressState
from unikit.registry import Registry
from unikit.security_context import SecurityContextDto
from unikit.utils import dict_utils
from unikit.utils.default import OnErrorDef, raise_or_default
from unikit.utils.type_utils import T

RESULT_KEY_PROGRESS_STATE = "progress_state"


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
    task_name: str | None = None


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
    task_name: str | None = None
    security_context: SecurityContextDto = dataclasses.field(default_factory=SecurityContextDto)

    def get_result_obj(self, target_cls: type[T], key: str | None = None, on_missing: OnErrorDef[Any] = None) -> Any:
        """Get the result object by the given target class."""
        if self.result is None:
            return raise_or_default(on_missing, "Result is not available")
        return dict_utils.get_object(self.result, target_cls, key=key, on_missing=on_missing)

    def get_progress_state(self) -> ProgressState:
        """Get the progress state from the result."""
        default = ProgressState()
        return self.get_result_obj(ProgressState, key=RESULT_KEY_PROGRESS_STATE, on_missing=default)

    @property
    def is_progress_state_available(self) -> bool:
        """Check if the progress state is available."""
        return not self.get_progress_state().is_empty


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


class ContextVarWorkerTaskHolder:
    """A holder which utilizes ContextVar to store current worker task."""

    def __init__(self) -> None:
        self.__current_task = ContextVar[PostedTask | None]("_unikit__current_task", default=None)

    def set_current_task(self, task: PostedTask | None) -> None:
        """Set the current worker task."""
        self.__current_task.set(task)

    def get_current_task(self) -> PostedTask | None:
        """Get the current worker task."""
        return self.__current_task.get()


class ContextVarWorkerTaskProvider(Provider[PostedTask]):
    """
    Provider for Security Context based on ContextVarSecurityContextHolder.

    Target context holder must be passed in constructor. If not passed, default_security_context_holder will be used.
    """

    def __init__(self, context_holder: ContextVarWorkerTaskHolder):
        super().__init__()
        self._context_holder = context_holder

    def get(self, injector: Injector) -> PostedTask:
        """Get Web Security Context."""
        current_task = self._context_holder.get_current_task()
        if current_task is None:
            raise ValueError("Current task is not available.")
        return current_task


class TaskInfoLoggingFilter(logging.Filter):
    """Logging filter to attach information about currently running task to every log record."""

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log record."""
        try:
            task: PostedTask = root_container.get(PostedTask)
            if task:
                setattr(record, self.prefix + "task_uuid", task.uuid)
                if task.task_name:
                    setattr(record, self.prefix + "task_name", task.task_name)
                if task.timestamp:
                    setattr(record, self.prefix + "task_placed_at", task.timestamp)
        except Exception:
            pass  # This filter should never raise an exception
        return True
