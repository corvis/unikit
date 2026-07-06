#
#  Copyright 2026 by Dmitry Berezovsky, MIT License
#
"""
Process-pool singleton for CPU-bound taskiq tasks.

Usage - wire up once in your ``broker.py``::

    from unikit.contrib.taskiq.cpu_pool import setup_cpu_pool_on_broker
    from taskiq import TaskiqEvents

    setup_cpu_pool_on_broker(default_broker, heavy_tasks_broker, pool_size=4)

Inside a ``CpuBoundTaskiqTask`` subclass the pool is accessed automatically
via :func:`get_cpu_pool`.  You can also call it directly if needed.
"""

from __future__ import annotations

__all__ = [
    "CpuPoolNotInitializedError",
    "get_cpu_pool",
    "init_cpu_pool",
    "setup_cpu_pool_on_broker",
    "shutdown_cpu_pool",
]

from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
import logging
import multiprocessing
from typing import Any

from taskiq import AsyncBroker, TaskiqEvents

logger = logging.getLogger(__name__)

_pool: ProcessPoolExecutor | None = None


class CpuPoolNotInitializedError(RuntimeError):
    """Raised when the CPU process pool is accessed before it has been initialized."""

    def __init__(self) -> None:
        super().__init__(
            "CPU process pool has not been initialized. "
            "Call init_cpu_pool() or setup_cpu_pool_on_broker() during worker startup."
        )


def init_cpu_pool(
    size: int,
    initializer: Callable[..., None] | None = None,
    initargs: tuple[Any, ...] = (),
    mp_context: multiprocessing.context.BaseContext | None = None,
    max_tasks_per_child: int | None = None,
) -> ProcessPoolExecutor:
    """
    Create and store the global ``ProcessPoolExecutor`` used for CPU-bound tasks.

    Safe to call multiple times - subsequent calls replace the old pool after
    shutting it down gracefully (``wait=True``).

    :param size: number of worker processes.  Should match ``--max-async-tasks``
        so that every concurrently running task can always obtain a process slot.
    :param initializer: optional callable that each worker process runs once at
        startup (e.g. to call ``django.setup()``).  Must be picklable (i.e. a
        module-level function) when using ``spawn`` or ``forkserver`` contexts.
        Not needed when using ``fork`` since the child inherits the parent state.
    :param initargs: positional arguments forwarded to *initializer*.
    :param mp_context: multiprocessing context that controls how worker processes
        are started (``fork``, ``spawn``, or ``forkserver``).  Defaults to
        ``multiprocessing.get_context("fork")`` which inherits the parent's
        fully-initialized state (including Django) and requires no *initializer*.
        Use ``spawn`` or ``forkserver`` on platforms where ``fork`` is unsafe, and
        supply an *initializer* to set up Django in each worker.
    :param max_tasks_per_child: recycle each worker process after it has executed
        this many tasks, replacing it with a fresh one.  Bounds the impact of any
        per-task resource accumulation (e.g. leaked connections) inside long-lived
        workers.  ``None`` (default) keeps workers for the pool's whole lifetime.
        Ignored with a warning when the ``fork`` start method is used, since
        ``ProcessPoolExecutor`` does not support recycling under ``fork``.
    :return: the newly created pool.
    :raises ValueError: if *size* is less than 1, or if *max_tasks_per_child* is less than 1.
    """
    if size < 1:
        raise ValueError(f"init_cpu_pool() requires size >= 1, got {size!r}.")
    if max_tasks_per_child is not None and max_tasks_per_child < 1:
        raise ValueError(f"init_cpu_pool() requires max_tasks_per_child >= 1, got {max_tasks_per_child!r}.")
    global _pool
    if _pool is not None:
        logger.warning("CPU pool already initialized - replacing existing pool (size=%d).", size)
        _pool.shutdown(wait=True)
    ctx = mp_context if mp_context is not None else multiprocessing.get_context("fork")
    pool_kwargs: dict[str, Any] = dict(max_workers=size, initializer=initializer or None, initargs=initargs)
    if max_tasks_per_child is not None:
        if ctx.get_start_method() == "fork":
            logger.warning(
                "max_tasks_per_child=%d is not supported with the 'fork' start method and will be ignored. "
                "Use 'forkserver' or 'spawn' to enable worker recycling.",
                max_tasks_per_child,
            )
        else:
            pool_kwargs["max_tasks_per_child"] = max_tasks_per_child
    _pool = ProcessPoolExecutor(mp_context=ctx, **pool_kwargs)
    logger.info(
        "CPU process pool initialized with %d worker(s) (start method: %s, max_tasks_per_child: %s).",
        size,
        ctx.get_start_method(),
        pool_kwargs.get("max_tasks_per_child"),
    )
    return _pool


def get_cpu_pool() -> ProcessPoolExecutor:
    """
    Return the global ``ProcessPoolExecutor``.

    :raises CpuPoolNotInitializedError: if :func:`init_cpu_pool` has not been called yet.
    :return: the active process pool.
    """
    if _pool is None:
        raise CpuPoolNotInitializedError()
    return _pool


def shutdown_cpu_pool(*, wait: bool = True) -> None:
    """
    Shut down the global ``ProcessPoolExecutor``.

    Calling this when no pool exists is a no-op.

    :param wait: if ``True`` (default) block until all running futures complete.
    """
    global _pool
    if _pool is None:
        return
    logger.info("Shutting down CPU process pool.")
    _pool.shutdown(wait=wait)
    _pool = None


def setup_cpu_pool_on_broker(
    *brokers: AsyncBroker,
    pool_size: int,
    initializer: Callable[..., None] | None = None,
    initargs: tuple[Any, ...] = (),
    mp_context: multiprocessing.context.BaseContext | None = None,
) -> None:
    """
    Register ``WORKER_STARTUP`` and ``WORKER_SHUTDOWN`` event handlers on each broker.

    CPU process pool is automatically managed for the lifetime of the worker process.

    Call this once in ``broker.py``, passing the same value you use for
    ``--max-async-tasks`` (or a fraction of it if you want fewer processes than
    concurrent async tasks).

    Example::

        from unikit.contrib.taskiq.cpu_pool import setup_cpu_pool_on_broker

        setup_cpu_pool_on_broker(default_broker, heavy_tasks_broker, pool_size=4)

    :param brokers: one or more :class:`~taskiq.AsyncBroker` instances to attach
        the lifecycle handlers to.
    :param pool_size: number of worker processes in the pool.
    :param initializer: optional callable run once in each worker process at
        startup.  See :func:`init_cpu_pool` for details.
    :param initargs: positional arguments forwarded to *initializer*.
    :param mp_context: multiprocessing context controlling how worker processes
        are started.  See :func:`init_cpu_pool` for details.
    """

    async def _startup(state: Any) -> None:  # noqa: ANN401
        init_cpu_pool(pool_size, initializer=initializer, initargs=initargs, mp_context=mp_context)

    async def _shutdown(state: Any) -> None:  # noqa: ANN401
        shutdown_cpu_pool(wait=True)

    for broker in brokers:
        broker.on_event(TaskiqEvents.WORKER_STARTUP)(_startup)
        broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)(_shutdown)
        logger.debug(
            "CPU pool lifecycle handlers registered on broker %r (pool_size=%d).",
            broker,
            pool_size,
        )
