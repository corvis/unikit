#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import injector

from unikit.abstract import Abstract, AbstractMeta
from unikit.contrib.taskiq.dto import TaskiqTask
from unikit.di import DiModule, DiProxy
from unikit.worker import ContextVarWorkerTaskHolder, ContextVarWorkerTaskProvider, PostedTask


class BaseTaskiqDiModule(DiModule, Abstract, metaclass=AbstractMeta):
    """Base DI module for Taskiq."""

    def configure(self, binder: injector.Binder) -> None:
        """Configure DI module."""
        super().configure(binder)

        provider = injector.InstanceProvider(
            PostedTaskProvider(
                ContextVarWorkerTaskProvider(default_current_task_holder), binder.injector  # type: ignore
            )
        )
        binder.bind(PostedTask, provider)
        binder.bind(TaskiqTask, provider)


default_current_task_holder = ContextVarWorkerTaskHolder()


class PostedTaskProvider(DiProxy[TaskiqTask]):
    """Provider for TaskiqPostedTask."""

    pass
