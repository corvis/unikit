#
#  Copyright 2025 by Dmitry Berezovsky, MIT License
#
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, TypeAlias

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.http import HttpRequest, HttpResponse

AsyncOrSyncCallback: TypeAlias = (
    Callable[[HttpRequest], HttpResponse] | Callable[[HttpRequest], Awaitable[HttpResponse]]
)


class BaseUniversalMiddleware:
    """Base class for universal middleware which supports both sync and async modes."""

    async_capable = True
    sync_capable = True

    def __init__(self, get_response: AsyncOrSyncCallback) -> None:
        self.get_response = get_response
        self._is_async = iscoroutinefunction(get_response)
        if self._is_async:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest) -> Coroutine[Any, Any, HttpResponse] | HttpResponse:
        """Universal entrypoint."""
        if self._is_async:
            return self._call_async(request)
        else:
            return self._call_sync(request)

    def _call_sync(self, request: HttpRequest) -> HttpResponse:
        """Process a request synchronously."""
        early_response = self.process_request_sync(request)
        if early_response:
            return early_response

        response = self.get_response(request)

        return self.process_response_sync(request, response)

    async def _call_async(self, request: HttpRequest) -> HttpResponse:
        """Process a request asynchronously."""
        early = await self.process_request_async(request)
        if early:
            return early

        response = await self.get_response(request)

        return await self.process_response_async(request, response)

    def process_request_sync(self, request: HttpRequest) -> HttpResponse | None:
        """
        A Hook which is called on each sync request before the view.

        Return an HttpResponse to short-circuit or None to continue.
        """  # noqa: D401
        return None

    def process_response_sync(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """A hook will be called on all sync responses."""  # noqa: D401
        return response

    async def process_request_async(self, request: HttpRequest) -> HttpResponse | None:
        """
        A Hook which is called on each sync request before the view.

        Return an HttpResponse to short-circuit or None to continue.
        """  # noqa: D401
        return None

    async def process_response_async(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """A hook will be called on all async responses."""  # noqa: D401
        return response
