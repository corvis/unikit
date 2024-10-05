#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
from typing import Any, Generic

from celery import Task
from celery._state import current_task, pop_current_task, push_current_task
import injector

from unikit.utils.types import T


class TaskBodyMeta(abc.ABCMeta):
    """
    Metaclass for TaskBody classes that makes class compatible with Celery's shared_task/task decorator.

    See TaskBody for more information.
    """

    def __new__(mcs, name: str, bases: tuple[type, ...], namespace: dict[str, Any], **kwargs: Any) -> type:
        """Make class compatible with Celery's shared_task/task decorator."""
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if not hasattr(cls, "run"):
            raise ValueError(f"TaskBodyMeta meta must be used with class defining run method. Was used with {name}")
        cls.__call__ = cls.run  # type: ignore[method-assign]
        return cls


class TaskBody(metaclass=TaskBodyMeta):
    """Base class for class based task definitions. Compatible only with TaskWithInjection Celery tasks."""

    @abc.abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Implement in child classes to define task logic."""
        pass


class TaskWithInjection(Task, abc.ABC):  # type: ignore[misc]
    """A Celery task that can use Inject annotations to resolve dependencies prior invocation."""

    def _get_di_container(self) -> injector.Injector:
        container: injector.Injector | None = getattr(self, "di_container", None)
        if not container:
            container = getattr(self.app, "di_container", None)
        if not container:
            raise RuntimeError("DI Container unavailable in Celery context")
        return container

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Inject dependencies and call the run method."""
        push_current_task(self)
        if self.request:
            self.request_stack.push(self.request)
        try:
            if isinstance(self.run, type) and issubclass(self.run, TaskBody):
                runnable = self._get_di_container().create_object(self.run)
                return self._get_di_container().call_with_injection(runnable.run, args=args, kwargs=kwargs)
            else:
                return self._get_di_container().call_with_injection(self.run, args=args, kwargs=kwargs)
        finally:
            self.pop_request()
            pop_current_task()


class TaskRelatedProvider(injector.Provider[T], Generic[T]):
    """
    Resolves the target class from the current task's DI container if it exists.

    This might be useful if you want to define a child DI container for every task with some task-specific dependencies
    and resolve them in the task body.
    To use this provider you have to set DI container to the task instance in the task_prerun signal handler.
    Example:
        @task_prerun.connect
        def my_task_prerun_handler(task_id: str, task: MyBaseTask, kwargs: dict[str, Any], **other: Any) -> None:
            task.di_container = root_container.create_child_injector()
    """

    def __init__(self, target_cls: type[T]) -> None:
        self.target_cls = target_cls

    def get(self, injector_: injector.Injector) -> T:
        """Resolve the target class from the current task's DI container if it exists."""
        if current_task and hasattr(current_task, "di_container"):
            return current_task.di_container.get(self.target_cls)
        raise injector.UnsatisfiedRequirement(None, interface=self.target_cls)
