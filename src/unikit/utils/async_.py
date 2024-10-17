#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import asyncio
import inspect
from typing import Any, Awaitable, Coroutine

from asgiref.sync import async_to_sync

from unikit.registry import T


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
