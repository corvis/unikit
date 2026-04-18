#
#  Copyright 2026 by Dmitry Berezovsky, MIT License
#
"""Django-aware CPU-bound task helpers for Taskiq.

This module is the Django-specific counterpart to the framework-agnostic
:mod:`unikit.contrib.taskiq.cpu_task`.  It provides:

- :func:`django_subprocess_context_factory` — a
  :class:`~unikit.contrib.taskiq.cpu_task.SubprocessContextFactory` that
  reads ``TASKIQ_RESULT_BACKEND_URL`` from Django settings and builds a minimal
  ``Context`` with a freshly created Redis result-backend.
- :class:`DjangoCpuBoundTaskiqTask` — a convenience subclass of
  :class:`~unikit.contrib.taskiq.cpu_task.CpuBoundTaskiqTask` that
  pre-configures :attr:`subprocess_context_factory` to the Django factory above,
  so Django-based tasks get progress reporting out of the box without any extra
  wiring.
"""

from __future__ import annotations

__all__ = [
    "DjangoCpuBoundTaskiqTask",
    "django_subprocess_context_factory",
]

import abc
import datetime
from types import SimpleNamespace
from typing import Any

from taskiq import AsyncResultBackend, Context

from unikit.contrib.taskiq.cpu_task import CpuBoundTaskiqTask


class _DjangoSubprocessResultBackend:
    """
    Lazily-initialized result backend for use inside a subprocess worker.

    On first async access it reads ``TASKIQ_RESULT_BACKEND_URL`` from Django
    settings and creates a fresh ``RedisAsyncResultBackend``, ensuring that no
    inherited asyncio state from the parent process is reused.

    The class is intentionally self-contained so it can be used without
    importing Django at module load time — the import only happens when the
    first awaited method is called from within the subprocess.
    """

    _backend: AsyncResultBackend | None = None

    async def _get_backend(self) -> AsyncResultBackend:
        if self._backend is None:
            from django.conf import settings  # noqa: PLC0415
            from taskiq_redis import RedisAsyncResultBackend

            if settings.TASKIQ_RESULT_BACKEND_URL.startswith("redis://"):
                self._backend = RedisAsyncResultBackend(
                    redis_url=settings.TASKIQ_RESULT_BACKEND_URL,
                    keep_results=True,
                    result_ex_time=int(datetime.timedelta(days=10).total_seconds()),
                )
            elif settings.TASKIQ_RESULT_BACKEND_URL == "noop://":
                from taskiq.result_backends.dummy import DummyResultBackend

                self._backend = DummyResultBackend()
            else:
                raise ValueError(
                    f"Unsupported result backend scheme for URL `{settings.TASKIQ_RESULT_BACKEND_URL}`. "
                    "Only 'redis://' and 'noop://' are supported."
                )

            await self._backend.startup()
        return self._backend

    async def set_progress(self, task_id: str, progress: Any) -> None:
        """Proxy ``set_progress`` to the lazily-created backend.

        :param task_id: the taskiq task identifier.
        :param progress: progress object to store.
        """
        backend = await self._get_backend()
        await backend.set_progress(task_id, progress)

    async def get_progress(self, task_id: str) -> Any:
        """Proxy ``get_progress`` to the lazily-created backend.

        :param task_id: the taskiq task identifier.
        :return: stored progress object, or ``None`` if not set.
        """
        backend = await self._get_backend()
        return await backend.get_progress(task_id)

    async def shutdown(self) -> None:
        """Shut down the underlying backend if it was created."""
        if self._backend is not None:
            await self._backend.shutdown()
            self._backend = None


def django_subprocess_context_factory(task_id: str) -> Context:
    """
    Build a minimal ``Context`` for use inside a subprocess worker.

    This is a ready-made
    :class:`~unikit.contrib.taskiq.cpu_task.SubprocessContextFactory`
    implementation for Django projects.  It constructs a ``SimpleNamespace``
    that satisfies the ``Context`` interface consumed by
    :class:`~unikit.contrib.taskiq.progress.TaskProgressReporter`:

    - ``context.message.task_id`` — forwarded from the parent process.
    - ``context.broker.result_backend`` — a lazily-initialized
      :class:`_DjangoSubprocessResultBackend` that reads
      ``settings.TASKIQ_RESULT_BACKEND_URL`` on first use.

    You can assign this factory directly to
    :attr:`~unikit.contrib.taskiq.cpu_task.CpuBoundTaskiqTask.subprocess_context_factory`
    on any custom task class, or simply inherit from
    :class:`DjangoCpuBoundTaskiqTask` which does this for you.

    :param task_id: taskiq task identifier passed from the parent process.
    :return: object satisfying the ``Context`` interface.
    """
    result_backend = _DjangoSubprocessResultBackend()
    broker = SimpleNamespace(result_backend=result_backend)
    message = SimpleNamespace(task_id=task_id)
    return SimpleNamespace(broker=broker, message=message)  # type: ignore[return-value]


class DjangoCpuBoundTaskiqTask(CpuBoundTaskiqTask, metaclass=abc.ABCMeta):
    """
    CPU-bound taskiq task base class pre-configured for Django projects.

    Identical to :class:`~unikit.contrib.taskiq.cpu_task.CpuBoundTaskiqTask`
    but sets :attr:`subprocess_context_factory` to
    :func:`django_subprocess_context_factory` so that ``self.progress_reporter``
    and ``self.context`` work automatically inside :meth:`run_cpu_bound` without
    any extra wiring.

    Use this as the base class for all CPU-intensive tasks in Django-based
    services instead of :class:`~unikit.contrib.taskiq.cpu_task.CpuBoundTaskiqTask`::

        from unikit.contrib.django.taskiq.cpu_task import DjangoCpuBoundTaskiqTask

        @heavy_tasks_broker.task(TASK_NAME, queue=QUEUE_HEAVY_TASKS)
        class RunHeavyTask(DjangoCpuBoundTaskiqTask):
            async def run_cpu_bound(self, payload: dict[str, Any]) -> dict[str, Any]:
                tracker = await self.progress_reporter.create_tracker()
                ...
    """

    subprocess_context_factory = django_subprocess_context_factory
