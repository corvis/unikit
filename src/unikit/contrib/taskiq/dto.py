#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import dataclasses

from taskiq import AsyncTaskiqTask

from unikit.worker import PostedTask


@dataclasses.dataclass(kw_only=True, frozen=True)
class TaskiqPostedTask(PostedTask):
    """TaskiqPostedTask is a DTO for Taskiq task."""

    task: AsyncTaskiqTask


TASKIQ_LABEL_SECURITY_CONTEXT = "unikit_security_context"
TASKIQ_LABEL_TASKNAME = "__taskiq__task_name"
