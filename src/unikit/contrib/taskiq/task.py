#
#  Copyright 2026 by Dmitry Berezovsky, MIT License
#
"""Class-based task abstraction for Taskiq with built-in DI container support."""

from __future__ import annotations

__all__ = ["BaseTaskiqTask"]

import abc
from functools import cached_property, wraps
import inspect
from typing import Annotated, Any

from taskiq import Context, TaskiqDepends

from unikit.contrib.taskiq.progress import TaskProgressReporter
from unikit.di import root_container
from unikit.utils.logger import LogMixin

# Sentinel parameter name used to carry the taskiq Context through __init__.
# DependencyGraph inspects __init__, so this is where the injection must live.
_CONTEXT_KWARG = "__taskiq_context__"


def _wrap_init_with_context_param(original_init: Any) -> Any:
    """
    Wrap a class's __init__ to accept the injected Context.

    Return a new ``__init__`` that accepts ``__taskiq_context__`` as an
    extra keyword-only parameter annotated with ``Annotated[Context,
    TaskiqDepends()]``.

    ``taskiq_dependencies.DependencyGraph`` inspects ``__init__`` when the
    dependency target is a class, so this is the only place where a
    ``TaskiqDepends`` annotation is visible to it.  The wrapper stores the
    injected ``Context`` on ``self._context`` and then delegates to the
    original ``__init__``.

    :param original_init: the ``__init__`` to wrap.
    :return: wrapped ``__init__`` with the extra context parameter.
    """
    # Build the new signature: original params + __taskiq_context__ at the end.
    try:
        orig_sig = inspect.signature(original_init)
    except (ValueError, TypeError):
        return original_init

    # Already wrapped - avoid adding the parameter a second time (e.g. when a
    # concrete subclass of CpuBoundTaskiqTask is processed by the metaclass).
    if _CONTEXT_KWARG in orig_sig.parameters:
        return original_init

    context_param = inspect.Parameter(
        _CONTEXT_KWARG,
        kind=inspect.Parameter.KEYWORD_ONLY,
        default=TaskiqDepends(),
        annotation=Annotated[Context, TaskiqDepends()],
    )
    # Insert before any VAR_KEYWORD (**kwargs) parameter to satisfy Python's
    # parameter ordering rules (keyword-only cannot follow **kwargs).
    orig_params = list(orig_sig.parameters.values())
    insert_at = next(
        (i for i, p in enumerate(orig_params) if p.kind == inspect.Parameter.VAR_KEYWORD),
        len(orig_params),
    )
    new_params = orig_params[:insert_at] + [context_param] + orig_params[insert_at:]
    new_sig = orig_sig.replace(parameters=new_params)

    # Build matching __annotations__ so get_type_hints() also sees the param.
    orig_annotations: dict[str, Any] = getattr(original_init, "__annotations__", {}).copy()
    orig_annotations[_CONTEXT_KWARG] = Annotated[Context, TaskiqDepends()]

    @wraps(original_init)
    def _wrapped_init(self: Any, *args: Any, **kwargs: Any) -> None:
        context: Context | None = kwargs.pop(_CONTEXT_KWARG, None)
        self._context = context
        original_init(self, *args, **kwargs)

    _wrapped_init.__signature__ = new_sig  # type: ignore[attr-defined]
    _wrapped_init.__annotations__ = orig_annotations
    return _wrapped_init


class _TaskiqTaskMeta(abc.ABCMeta):
    """
    Metaclass for TaskiqTask subclasses.

    Makes the class directly usable as a taskiq task callable by:

    - Wrapping ``__init__`` on every concrete subclass to accept a hidden
      ``__taskiq_context__`` keyword-only parameter annotated with
      ``Annotated[Context, TaskiqDepends()]``.  ``taskiq_dependencies``
      inspects ``__init__`` when the dependency target is a class, so this is
      the only place the injection is visible to it.
    - Exposing ``run``'s signature as ``cls.__signature__`` (minus ``self``) so
      that ``inspect.signature(MyTask)`` and ``get_type_hints(MyTask)`` return
      the real task-parameter metadata taskiq uses for param parsing and
      return-type detection.
    - Overriding the metaclass ``__call__`` so that calling the class (what
      taskiq does at execution time) resolves a fresh instance via
      ``root_container`` - which triggers the wrapped ``__init__`` and
      therefore stores the injected ``Context`` - then dispatches to ``run``.
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> type:
        """Create a new TaskiqTask subclass with the correct callable signature."""
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # Walk the MRO to find the most-derived *concrete* definition of run()
        # (skip the abstract placeholder on TaskiqTask itself).
        run_fn: Any = None
        for klass in cls.__mro__:
            if klass is object:
                continue
            local_run = klass.__dict__.get("run")
            if local_run is not None and not getattr(local_run, "__isabstractmethod__", False):
                run_fn = local_run
                break

        if run_fn is not None:
            # ----------------------------------------------------------------
            # 1. Wrap __init__ so DependencyGraph finds the context injection
            #    parameter when it inspects the class constructor.
            # ----------------------------------------------------------------
            original_init = cls.__dict__.get("__init__") or next(
                (k.__dict__["__init__"] for k in cls.__mro__ if "__init__" in k.__dict__ and k is not object),
                object.__init__,
            )
            cls.__init__ = _wrap_init_with_context_param(original_init)  # type: ignore[misc]

            # ----------------------------------------------------------------
            # 2. Expose run()'s signature as cls.__signature__ so that
            #    inspect.signature(MyTask) returns the task parameters (used
            #    by taskiq's param parser and the receiver).
            #    get_type_hints(MyTask) is covered by copying __annotations__.
            #
            #    Important: we resolve the annotations via get_type_hints()
            #    rather than copying __annotations__ raw.  run_fn may live in a
            #    module that uses ``from __future__ import annotations``, turning
            #    all annotations into strings.  If we stored those strings on
            #    cls, Python would later evaluate them in *cls*'s module globals,
            #    which might not import the referenced names (e.g. ``Any``),
            #    causing a NameError inside taskiq's get_type_hints(cls) call.
            #    get_type_hints() resolves strings using run_fn's own globals,
            #    giving us real type objects that are safe to re-export.
            # ----------------------------------------------------------------
            try:
                from typing import get_type_hints as _get_type_hints  # noqa: PLC0415

                resolved_hints = _get_type_hints(run_fn)
            except Exception:
                resolved_hints = getattr(run_fn, "__annotations__", {})
            cls.__annotations__ = resolved_hints
            try:
                raw_sig = inspect.signature(run_fn)
                params = [p for pname, p in raw_sig.parameters.items() if pname != "self"]
                cls.__signature__ = raw_sig.replace(parameters=params)  # type: ignore[attr-defined]
            except (ValueError, TypeError):
                pass

        return cls

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """
        Resolve a fresh instance from the DI container and dispatch to ``run``.

        Invoked when taskiq calls the class as ``MyTask(*args, **kwargs)``
        during task execution.  ``root_container.create_object`` calls the
        wrapped ``__init__``, which receives the ``Context`` injected by
        taskiq's dependency resolver and stores it on ``self._context``.

        Supports both sync and async ``run`` implementations transparently.
        """
        if cls.__abstractmethods__:
            raise TypeError(
                f"Can't call abstract class {cls.__name__!r} - "
                f"implement abstract methods: {', '.join(sorted(cls.__abstractmethods__))}"
            )
        instance: BaseTaskiqTask = root_container.create_object(cls)  # type: ignore[arg-type]
        context = kwargs.pop(_CONTEXT_KWARG, None)
        if context is not None:
            instance._context = context
        return instance.run(*args, **kwargs)


class BaseTaskiqTask(LogMixin, metaclass=_TaskiqTaskMeta):
    """
    Base class for class-based Taskiq tasks with automatic DI container support.

    Subclass this, declare constructor dependencies using ``injector.Inject``
    annotations, and implement ``run()`` with the actual task parameters.
    Then annotate the class with ``@default_broker.task(...)`` exactly as you
    would annotate a plain function.

    Both **sync** and **async** ``run`` methods are supported.  Taskiq will
    detect the coroutine nature of the call automatically.

    The taskiq ``Context`` (carrying the message, broker, and state) is
    automatically injected via ``__init__`` and accessible via the
    ``self.context`` read-only property inside ``run``.

    Example (sync)::

        @default_broker.task(const.TASK_NAME_MY_TASK, queue=QUEUE_HEAVY_TASKS)
        class MyTask(TaskiqTask):
            def __init__(self, my_service: Inject[MyService]) -> None:
                self._my_service = my_service

            def run(self, project_id: str, *, force: bool = False) -> None:
                self.log.info(
                    "Running task for project %s (task_id=%s)",
                    project_id,
                    self.context.message.task_id,
                )
                self._my_service.do_something(project_id, force=force)

    Example (async)::

        @default_broker.task(const.TASK_NAME_MY_ASYNC_TASK)
        class MyAsyncTask(TaskiqTask):
            def __init__(self, my_service: Inject[MyService]) -> None:
                self._my_service = my_service

            async def run(self, project_id: str) -> dict[str, Any]:
                self.log.info(
                    "Running async task for project %s (task_id=%s)",
                    project_id,
                    self.context.message.task_id,
                )
                return await self._my_service.fetch_result(project_id)
    """

    _context: Context | None = None

    @property
    def context(self) -> Context:
        """
        Return the taskiq execution context for the current task invocation.

        Provides access to ``context.message`` (task id, name, args, kwargs,
        labels), ``context.broker``, and ``context.state``.

        :raises RuntimeError: if accessed outside of a task invocation (e.g.
            in tests that instantiate the task directly without going through
            the broker).
        """
        if self._context is None:
            raise RuntimeError(
                f"{self.__class__.__name__}.context is only available during task execution. "
                "If you are testing, pass a Context instance via the mock container."
            )
        return self._context

    @cached_property
    def progress_reporter(self) -> TaskProgressReporter:
        """
        Return a ``TaskProgressReporter`` bound to the current task execution context.

        The reporter is created once per invocation and cached for the lifetime
        of the task instance.  Use it to report progress, set state, or store
        metadata that is visible to the caller via the result backend.

        :raises RuntimeError: if accessed outside of a task invocation (i.e.
            when ``self.context`` is not available).
        """
        return self.create_progress_reporter()

    def create_progress_reporter(self) -> TaskProgressReporter:
        """
        Create a new ``TaskProgressReporter`` bound to the current task execution context.

        Override this if you want to define a custom subclass of ``TaskProgressReporter`` with additional methods or
        custom behavior.  By default, this just instantiates a plain ``TaskProgressReporter``.

        :raises RuntimeError: if accessed outside of a task invocation (i.e.
            when ``self.context`` is not available).
        """
        return TaskProgressReporter(context=self.context)

    @abc.abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> Any:
        """
        Implement task logic in subclasses.

        Task parameters go here; constructor is reserved for injected services.
        May be either a regular function or an ``async def`` coroutine.
        Use ``self.context`` to access the taskiq execution context.
        """
