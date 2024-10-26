#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
import inspect
from typing import Any, Awaitable, Callable, Coroutine

from unikit.registry import T
from unikit.utils.types import R

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
