#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import dataclasses

from taskiq import AsyncTaskiqTask, TaskiqMessage

from unikit.worker import PostedTask


@dataclasses.dataclass(kw_only=True, frozen=True)
class TaskiqPostedTask(PostedTask):
    """TaskiqPostedTask is a DTO for Taskiq task."""

    task: AsyncTaskiqTask


@dataclasses.dataclass(kw_only=True, frozen=True)
class TaskiqTask(PostedTask):
    """TaskiqTask is a DTO for Taskiq task."""

    message: TaskiqMessage


TASKIQ_LABEL_SECURITY_CONTEXT = "unikit_security_context"
TASKIQ_LABEL_TASKNAME = "__taskiq__task_name"
TASKIQ_LABEL_DATE_POSTED = "__taskiq__date_posted"
