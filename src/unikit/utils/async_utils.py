#
#  Copyright 2026 by Dmitry Berezovsky, MIT License
#
import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
import inspect
from typing import Any, TypeVar

from unikit.registry import T
from unikit.utils.type_utils import R

_HAS_ASGIREF = True
try:
    from asgiref.sync import async_to_sync as asgiref_async_to_sync
    from asgiref.sync import sync_to_async as asgiref_sync_to_async
except ImportError:
    _HAS_ASGIREF = False


async def maybe_awaitable(
    possible_coroutine: T | Coroutine[Any, Any, T] | Awaitable[T],
) -> T:
    """
    Awaits coroutine if needed.

    This function allows run function
    that may return coroutine.

    It not awaitable value passed, it
    returned immediately.

    :param possible_coroutine: some value.
    :return: value.
    """
    if inspect.isawaitable(possible_coroutine):
        return await possible_coroutine
    return possible_coroutine


def await_if_awaitable(possible_coroutine: T | Coroutine[Any, Any, T] | Awaitable[T]) -> T:
    """
    Awaits coroutine if needed.

    This function allows run function
    that may return coroutine.

    It not awaitable value passed, it
    returned immediately.

    :param possible_coroutine: some value.
    :return: value.
    """
    if inspect.isawaitable(possible_coroutine):
        if is_async_context():
            return asyncio.run(possible_coroutine)  # type: ignore
        else:

            async def _wrap() -> Any:
                return await possible_coroutine

            return async_to_sync(_wrap)()
    return possible_coroutine


def is_async_context() -> bool:
    """
    Check if current context is async.

    :return: True if async, False otherwise.
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def async_to_sync(async_func: Callable[..., Awaitable[R]], force_new_loop: bool = False) -> Callable[..., R]:
    """Convert an asynchronous function to a synchronous one."""

    if _HAS_ASGIREF:
        return asgiref_async_to_sync(async_func, force_new_loop=force_new_loop)

    @wraps(async_func)
    def sync_func(*args: T, **kwargs: T) -> R:
        loop = asyncio.new_event_loop() if force_new_loop else asyncio.get_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(async_func(*args, **kwargs))
        finally:
            loop.close()

    return sync_func


def sync_to_async(sync_func: Callable[..., R]) -> Callable[..., Awaitable[R]]:
    """Convert a synchronous function to an asynchronous one."""
    if _HAS_ASGIREF:
        return asgiref_sync_to_async(sync_func, thread_sensitive=True)

    @wraps(sync_func)
    async def async_func(*args: T, **kwargs: T) -> R:
        loop = asyncio.get_event_loop()
        # Run in executor to avoid blocking the event loop
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, sync_func, *args, **kwargs)

    return async_func


def run_async(coroutine: Coroutine[Any, Any, R], force_new_loop: bool = False) -> R:
    """
    Run coroutine in async context.

    :param coroutine: coroutine.
    :param force_new_loop: force new loop.
    :return: result of coroutine.
    """
    if is_async_context():
        return asyncio.run(coroutine)

    loop = asyncio.new_event_loop() if force_new_loop else asyncio.get_event_loop()
    if force_new_loop:
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coroutine)


# Python 3.12 deprecates asyncio.iscoroutinefunction() as an alias for
# inspect.iscoroutinefunction(), whilst also removing the _is_coroutine marker.
# The latter is replaced with the inspect.markcoroutinefunction decorator.
# Until 3.12 is the minimum supported Python version, provide a shim.
_F = TypeVar("_F", bound=Callable[..., Any])

if hasattr(inspect, "markcoroutinefunction"):
    iscoroutinefunction = inspect.iscoroutinefunction
    markcoroutinefunction: Callable[[_F], _F] = inspect.markcoroutinefunction
else:
    iscoroutinefunction = asyncio.iscoroutinefunction  # type: ignore[assignment]

    def markcoroutinefunction(func: _F) -> _F:  # noqa D103
        func._is_coroutine = asyncio.coroutines._is_coroutine  # type: ignore
        return func


_asyncio_worker_loop: asyncio.AbstractEventLoop | None = None


def set_asyncio_worker_loop(loop: asyncio.AbstractEventLoop | None = None, ignore_if_already_set: bool = False) -> None:
    """
    Register the event loop to be used by :func:`run_coroutine_in_running_loop`.

    Call this once from an async context at worker startup (e.g. a broker
    ``on_startup`` handler).  When *loop* is ``None`` the currently running loop
    is captured via :func:`asyncio.get_running_loop`.

    :param loop: The loop to register, or ``None`` to capture the running loop.
    :param ignore_if_already_set: If ``True``, do not overwrite an already registered loop.  Default is ``False``.
    :raises RuntimeError: If *loop* is ``None`` and there is no running loop.
    """
    global _asyncio_worker_loop
    if _asyncio_worker_loop is not None and ignore_if_already_set:
        return
    _asyncio_worker_loop = loop if loop is not None else asyncio.get_running_loop()


def get_worker_loop() -> asyncio.AbstractEventLoop | None:
    """
    Return the loop registered via :func:`set_worker_loop`, or ``None``.

    :returns: The registered loop, or ``None`` if :func:`set_worker_loop` was never called.
    """
    return _asyncio_worker_loop


def _find_running_loop() -> asyncio.AbstractEventLoop:
    """
    Locate the running event loop from any thread.

    Strategy (in order):

    1. Module-level registry set by :func:`set_worker_loop` — the explicit,
       reliable path for sync tasks running inside an async worker.
    2. :func:`asyncio.get_running_loop` — works when called directly from async
       code (fast path for coroutines that end up here).

    :returns: The running :class:`asyncio.AbstractEventLoop`.
    :raises RuntimeError: If no running loop can be found.
    """
    # Prefer the explicitly registered worker loop (valid from any thread).
    if _asyncio_worker_loop is not None and _asyncio_worker_loop.is_running():
        return _asyncio_worker_loop

    # Fallback: we may be inside an async context ourselves.
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        pass

    raise RuntimeError(
        "run_coroutine_in_running_loop requires a running event loop. "
        "Either call set_asyncio_worker_loop() at worker startup or use this function "
        "from within an async context."
    )


def run_coroutine_in_running_loop(coroutine: Coroutine[Any, Any, T], timeout: float | None = None) -> T:
    """
    Run a coroutine on the already-running event loop from a synchronous context.

    This is the correct way to call async code from a synchronous taskiq task (or any
    sync code running inside an async worker process).  Unlike
    :func:`asgiref.sync.async_to_sync`, this function does **not** create a new event
    loop; instead it schedules the coroutine on the loop that is already running in
    another thread (the worker's main loop) via
    :func:`asyncio.run_coroutine_threadsafe` and blocks the calling thread until the
    result is available.

    This avoids the *"got Future attached to a different loop"* error that occurs when
    async resources (e.g. Redis connection pools) were created on one loop and are
    then awaited inside a freshly-created loop.

    .. note::
        This function must only be called from a **non-async** thread while another
        thread is running an event loop.  If there is no running loop a
        :class:`RuntimeError` is raised.

    :param coroutine: The coroutine to schedule on the running loop.
    :param timeout: Optional timeout in seconds passed to :meth:`concurrent.futures.Future.result`.
        When ``None`` (default) the call blocks indefinitely.
    :returns: The value returned by the coroutine.
    :raises RuntimeError: If no running event loop can be found in any live thread.
    """
    loop = _find_running_loop()
    future = asyncio.run_coroutine_threadsafe(coroutine, loop)
    return future.result(timeout)
