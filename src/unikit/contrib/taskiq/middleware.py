#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import datetime
from typing import Any, Generic

from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult
from taskiq.depends.progress_tracker import TaskProgress, TaskState

from unikit.contrib.taskiq.di import default_current_task_holder
from unikit.contrib.taskiq.dto import (
    TASKIQ_LABEL_DATE_POSTED,
    TASKIQ_LABEL_SECURITY_CONTEXT,
    TASKIQ_LABEL_TASKNAME,
    TaskiqTask,
)
from unikit.di import root_container
from unikit.security_context import (
    ContextVarSecurityContextHolder,
    SecurityContextDto,
    TBaseSecurityContext,
    default_security_context_holder,
)
from unikit.utils.logger import LogMixin
from unikit.utils.time_utils import datetime_now


class TaskInfoLabelsMiddleware(TaskiqMiddleware):
    """Middleware to attach task name, date posted and other metadata to labels."""

    async def pre_send(self, message: TaskiqMessage) -> TaskiqMessage:
        """Pre-send hook to attach task name to Taskiq message."""
        message.labels[TASKIQ_LABEL_TASKNAME] = message.task_name
        message.labels[TASKIQ_LABEL_DATE_POSTED] = datetime_now().isoformat()
        return message


class TaskInfoDiMiddleware(TaskiqMiddleware, LogMixin):
    """
    Middleware to put current task information into DI context.

    This allows user to inject `TaskiqPostedTask` or `PostedTask` into their services.
    """

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Pre-execute hook to TaskiqTask available in DI context."""
        time_posted_str = message.labels.get(TASKIQ_LABEL_DATE_POSTED)
        time_posted = datetime.datetime.fromisoformat(time_posted_str) if time_posted_str else None
        if time_posted is None:
            self.log.error("Task doesn't have a date posted label. Have you forgot to add TaskInfoLabelsMiddleware?")
        default_current_task_holder.set_current_task(
            TaskiqTask(
                uuid=message.task_id,
                timestamp=time_posted or datetime_now(),
                task_name=message.task_name,
                message=message,
            )
        )
        return message

    async def post_execute(self, message: TaskiqMessage, result: TaskiqResult[Any]) -> None:
        """Post-execute hook to clean up task info."""
        default_current_task_holder.set_current_task(None)

    async def on_error(self, message: TaskiqMessage, result: TaskiqResult[Any], exception: BaseException) -> None:
        """On error hook to clean up task info."""
        default_current_task_holder.set_current_task(None)


class ReportExecutionStartedMiddleware(TaskiqMiddleware):
    """Middleware to report execution start time."""

    def __init__(self, include_labels: bool = True) -> None:
        super().__init__()
        self.include_labels = include_labels

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Pre-execute hook to attach execution start time to Taskiq message."""
        metadata = {}
        if self.include_labels:
            metadata["labels"] = message.labels
        await self.broker.result_backend.set_progress(
            message.task_id, TaskProgress(state=TaskState.STARTED, meta=metadata)
        )
        return message


class SecurityContextMiddleware(TaskiqMiddleware, Generic[TBaseSecurityContext]):
    """Middleware to attach security context to Taskiq messages."""

    def __init__(
        self,
        security_context_interface_cls: type[TBaseSecurityContext],
        security_context_holder: ContextVarSecurityContextHolder | None = None,
    ) -> None:
        self._security_context_interface_cls: type[TBaseSecurityContext] = security_context_interface_cls
        self._security_context_holder = security_context_holder or default_security_context_holder

    async def pre_send(self, message: TaskiqMessage) -> TaskiqMessage:
        """Pre-send hook to attach security context properties to Taskiq message."""
        try:
            security_context = root_container.get(self._security_context_interface_cls)
        except Exception:
            raise Exception(
                "Security context is not available in DI container. Make sure you've registered it "
                "like it is shown in the docs for ContextVarSecurityContextHolder."
            )
        await self._attach_context_to_message(message, security_context)
        return message

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Pre-execute hook to create security context and make it available in DI context."""
        security_context = await self._create_security_context(message)
        default_security_context_holder.set_security_context(security_context)
        return message

    async def post_execute(self, message: TaskiqMessage, result: TaskiqResult[Any]) -> None:
        """Post-execute hook to clean up security context."""
        default_security_context_holder.set_security_context(None)

    async def on_error(self, message: TaskiqMessage, result: TaskiqResult[Any], exception: BaseException) -> None:
        """On error hook to clean up security context."""
        default_security_context_holder.set_security_context(None)

    async def _create_security_context(self, message: TaskiqMessage) -> TBaseSecurityContext:
        return await self._security_context_interface_cls.afrom_dto(
            SecurityContextDto(message.labels.get(TASKIQ_LABEL_SECURITY_CONTEXT, {}))
        )

    async def _attach_context_to_message(
        self, message: TaskiqMessage, security_context: TBaseSecurityContext
    ) -> TaskiqMessage:
        message.labels[TASKIQ_LABEL_SECURITY_CONTEXT] = security_context.to_dto()
        return message
