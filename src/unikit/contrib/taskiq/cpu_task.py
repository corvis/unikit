#
#  Copyright 2026 by Dmitry Berezovsky, MIT License
#
"""CPU-bound task base class for Taskiq — no Django dependency."""

from __future__ import annotations

__all__ = [
    "CpuBoundTaskiqTask",
    "SubprocessContextFactory",
]

import abc
import asyncio
import inspect
import threading
from typing import Any, Protocol

from taskiq import Context

from unikit.contrib.taskiq.cpu_pool import get_cpu_pool
from unikit.contrib.taskiq.task import BaseTaskiqTask


class SubprocessContextFactory(Protocol):
    """
    Protocol for callables that build a minimal taskiq ``Context`` inside a subprocess.

    The factory receives the task id forwarded from the parent process and must
    return an object that satisfies the ``Context`` interface required by
    :class:`~unikit.contrib.taskiq.progress.TaskProgressReporter` — at
    minimum ``context.message.task_id`` and ``context.broker.result_backend``.

    Register a concrete factory on :class:`CpuBoundTaskiqTask` subclasses via
    the ``subprocess_context_factory`` class attribute::

        class MyTask(CpuBoundTaskiqTask):
            subprocess_context_factory = my_factory
            ...

    A ready-made Django-aware implementation is provided in
    :mod:`unikit.contrib.django.taskiq.cpu_task`.
    """

    def __call__(self, task_id: str) -> Context:
        """
        Build and return a subprocess context for the given task id.

        :param task_id: taskiq task identifier passed from the parent process.
        :return: object satisfying the ``Context`` interface.
        """
        ...


class CpuBoundTaskiqTask(BaseTaskiqTask, metaclass=abc.ABCMeta):
    """
    Base class for CPU-intensive taskiq tasks that execute work in a dedicated subprocess.

    Subclass this instead of :class:`BaseTaskiqTask` when the task body performs
    CPU-heavy work (e.g. numerical computation, report generation, model evaluation)
    that would otherwise block the asyncio event loop and starve other concurrent tasks.

    The process pool must be initialized before any task runs - do this once in
    your ``broker.py`` using :func:`~unikit.contrib.taskiq.cpu_pool.setup_cpu_pool_on_broker`::

        from unikit.contrib.taskiq.cpu_pool import setup_cpu_pool_on_broker

        setup_cpu_pool_on_broker(default_broker, heavy_tasks_broker, pool_size=4)

    The pool size should equal (or be a sensible fraction of) ``--max-async-tasks``
    so that every concurrently scheduled task can always acquire a process slot.

    Implement :meth:`run_cpu_bound` instead of :meth:`run` — it will be executed
    inside a subprocess.  Both ``def`` and ``async def`` are supported; async
    methods are driven by ``asyncio.run()`` giving the subprocess its own fresh
    event loop.

    ``self.progress_reporter`` and ``self.context`` are available inside
    ``run_cpu_bound`` provided a :attr:`subprocess_context_factory` is set on the
    class.  For Django-based projects use
    :class:`~unikit.contrib.django.taskiq.cpu_task.DjangoCpuBoundTaskiqTask`
    which wires this up automatically.

    .. important::
        Constructor-injected services (DI) are **not** available inside
        ``run_cpu_bound`` because the method runs in a forked process.  Fetch all
        required data *before* dispatching — pass it as arguments.

    Example (non-Django)::

        from unikit.contrib.taskiq.cpu_task import CpuBoundTaskiqTask, SubprocessContextFactory

        def my_context_factory(task_id: str) -> Context:
            ...  # build a minimal Context backed by your result backend

        @broker.task("my_task")
        class MyTask(CpuBoundTaskiqTask):
            subprocess_context_factory: SubprocessContextFactory = my_context_factory

            def run_cpu_bound(self, payload: dict[str, Any]) -> dict[str, Any]:
                ...
    """

    #: Factory that builds a minimal ``Context`` inside the subprocess worker.
    #: Must be set on concrete subclasses that use ``self.progress_reporter`` or
    #: ``self.context`` from within :meth:`run_cpu_bound`.
    #: Leave as ``None`` if progress reporting is not needed.
    subprocess_context_factory: SubprocessContextFactory | None = None

    def get_subprocess_state(self) -> dict[str, Any]:
        """
        Return a picklable snapshot of instance state to forward to the subprocess.

        Called in the **parent** process inside :meth:`run` before dispatching
        work to the process pool.  The returned dict is passed across the process
        boundary and handed to :meth:`restore_subprocess_state` inside the
        subprocess, where it can be used to re-create attributes that are
        normally set up by DI (e.g. a serialised security context).

        The base implementation returns an empty dict.  Override in subclasses
        to include whatever is needed::

            def get_subprocess_state(self) -> dict[str, Any]:
                return {"security_ctx_dto": self._security_context.to_dto()}

        :return: picklable dict forwarded to the subprocess.
        """
        return {}

    def restore_subprocess_state(self, state: dict[str, Any]) -> None:
        """
        Restore instance attributes from the snapshot produced by :meth:`get_subprocess_state`.

        Called in the **subprocess** after ``__new__`` and context injection,
        before :meth:`run_cpu_bound` is invoked.  Override to rebuild any
        attributes that were serialised in :meth:`get_subprocess_state`::

            def restore_subprocess_state(self, state: dict[str, Any]) -> None:
                self._security_context = MySecurityContext.from_dto(state["security_ctx_dto"])

        :param state: the dict returned by :meth:`get_subprocess_state` in the
            parent process.
        """

    @abc.abstractmethod
    def run_cpu_bound(self, *args: Any, **kwargs: Any) -> Any:
        """
        Implement the CPU-intensive task body here.

        Runs inside a subprocess from the global
        :class:`~concurrent.futures.ProcessPoolExecutor`.  All arguments and
        the return value must be picklable.

        Both ``def`` and ``async def`` are supported.  Async implementations are
        executed via ``asyncio.run()`` inside the subprocess.

        ``self.progress_reporter``, ``self.context``, and any attributes
        restored by :meth:`restore_subprocess_state` are available here.
        Constructor-injected services that are **not** forwarded via
        :meth:`get_subprocess_state` are **not** available.
        """

    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """
        Dispatch ``run_cpu_bound`` to the process pool and await its result.

        Extracts the task id from the current execution context and the
        subprocess state snapshot, and forwards both to the subprocess.
        """
        task_id = self.context.message.task_id
        subprocess_state = self.get_subprocess_state()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            get_cpu_pool(),
            _run_cpu_bound_in_process,
            self.__class__,
            task_id,
            subprocess_state,
            args,
            kwargs,
        )


def _run_loop_forever(loop: asyncio.AbstractEventLoop) -> None:
    """Run *loop* until :meth:`~asyncio.AbstractEventLoop.stop` is called.

    Intended to be executed in a daemon background thread so that synchronous
    :meth:`~CpuBoundTaskiqTask.run_cpu_bound` implementations can schedule
    coroutines onto it via :func:`~unikit.utils.async_utils.run_coroutine_in_running_loop`.

    :param loop: The event loop to run.
    """
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _run_cpu_bound_in_process(
    task_cls: type[CpuBoundTaskiqTask],
    task_id: str,
    subprocess_state: dict[str, Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """
    Entry point executed inside the subprocess.

    Creates a bare instance of ``task_cls``, optionally injects a subprocess
    context via :attr:`~CpuBoundTaskiqTask.subprocess_context_factory`, restores
    extra instance state via :meth:`~CpuBoundTaskiqTask.restore_subprocess_state`,
    then calls :meth:`~CpuBoundTaskiqTask.run_cpu_bound`.

    Both synchronous and ``async def`` implementations are supported.  Async
    methods are driven by ``asyncio.run()``, which creates a fresh event loop in
    the subprocess.

    This is a **module-level** function so that ``ProcessPoolExecutor`` can
    pickle it.

    :param task_cls: the concrete :class:`CpuBoundTaskiqTask` subclass.
    :param task_id: taskiq task identifier, used to reconstruct the subprocess context.
    :param subprocess_state: picklable state dict from
        :meth:`~CpuBoundTaskiqTask.get_subprocess_state`, used to restore DI
        attributes (e.g. a serialised security context) inside the subprocess.
    :param args: positional arguments forwarded to ``run_cpu_bound``.
    :param kwargs: keyword arguments forwarded to ``run_cpu_bound``.
    :return: return value of ``run_cpu_bound``.
    """
    instance = task_cls.__new__(task_cls)
    factory = task_cls.subprocess_context_factory
    if factory is not None:
        instance._context = factory(task_id)
    instance.restore_subprocess_state(subprocess_state)

    if inspect.iscoroutinefunction(instance.run_cpu_bound):
        # Async implementation — asyncio.run() gives the subprocess its own fresh loop.
        return asyncio.run(instance.run_cpu_bound(*args, **kwargs))

    # Sync implementation — spin up a background event loop so that any call to
    # run_coroutine_in_running_loop() inside run_cpu_bound() can schedule work on it.
    loop = asyncio.new_event_loop()
    _background_loop_thread = threading.Thread(
        target=_run_loop_forever, args=(loop,), daemon=True, name="cpu-task-bg-loop"
    )
    _background_loop_thread.start()
    try:
        from unikit.utils.async_utils import set_asyncio_worker_loop

        set_asyncio_worker_loop(loop)
        return instance.run_cpu_bound(*args, **kwargs)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        _background_loop_thread.join()
