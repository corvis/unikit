#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import asyncio
import functools
from importlib import import_module
from inspect import isfunction, ismethod
import logging
import threading
from typing import Any, Callable, Sequence, cast, get_type_hints

from asgiref.sync import markcoroutinefunction
from django.conf import settings
from django.contrib.sites import management
from django.core.handlers.asgi import ASGIRequest
from django.http import HttpRequest, HttpResponse
from django.template import Engine
from django.urls import URLPattern, URLResolver, get_resolver
from django.views.decorators.csrf import csrf_exempt
from injector import Binder, Injector

from unikit.contrib.django.di.base import BaseDiSupportedApp
from unikit.di import DiModule
from unikit.utils.async_utils import maybe_awaitable

logger = logging.getLogger(__name__)


class _DjangoInjectionApp(BaseDiSupportedApp):
    """
    Django DI app enables DI django lifecycle (views, template processors, etc).

    NEVER USE THIS CLASS DIRECTLY. INSTALL application `unikit.contrib.django.di` in INSTALLED_APPS instead.
    """

    ENABLE_VIEW_INJECTION = True
    ENABLE_TEMPLATE_PROCESSOR_INJECTION = True
    ENABLE_COMMAND_INJECTION = True
    default = False

    def __init__(self, app_name: str, app_module: str) -> None:
        super().__init__(app_name, app_module)
        self.django_module = _DjangoDiModule()
        self._di_container.binder.install(self.django_module)

    def ready(self) -> None:
        """Django callback invoked when application is ready to be used."""
        super().ready()
        if self.ENABLE_COMMAND_INJECTION:
            patch_command_loader(self._di_container)

        if self.ENABLE_VIEW_INJECTION:
            resolver: URLResolver | None = None
            try:
                resolver = get_resolver()
            except Exception:
                logger.debug("Resolver is not configured, skipping.")
            if resolver:
                _process_resolver(resolver, self._di_container)

        if self.ENABLE_TEMPLATE_PROCESSOR_INJECTION:
            engine: Engine | None = None
            try:
                engine = Engine.get_default()
            except Exception:
                logger.debug("Template engine is not configured, skipping.")
            if engine:
                engine.template_context_processors = tuple(
                    _process_list(engine.template_context_processors, self._di_container)
                )


class _DjangoDiModule(DiModule):

    def __init__(self) -> None:
        super().__init__()
        try:
            from asgiref.local import Local

            self._local: Local | threading.local = Local()
        except ImportError:
            self._local = threading.local()

    def set_request(self, request: HttpRequest) -> None:
        """Set the current request in the thread local storage."""
        if isinstance(request, ASGIRequest) and isinstance(self._local, threading.local):
            if settings.DEBUG:
                logger.warning(
                    "Calling DjangoModule.set_request with a ASGIRequest will lead to "
                    "bad results because the asgi handler does not spawn a thread per "
                    "request. Ignoring call to set_request"
                )
            self._local.request = None
            return
        self._local.request = request

    def get_request(self) -> HttpRequest | None:
        """Return the current request from the thread local storage."""
        try:
            return self._local.request
        except AttributeError:
            return None

    def configure(self, binder: Binder) -> None:
        """Configure the DI module."""
        super().configure(binder)
        from django.conf import LazySettings, Settings, settings

        self.register_singleton(Settings, to=settings)
        self.register_singleton(LazySettings, to=settings)
        binder.bind(HttpRequest, to=lambda: self.get_request())


def patch_command_loader(injector: Injector) -> None:
    """Patches the management command loader to allow injection into management commands."""

    # Original at:
    # https://github.com/django/django/blob/master/django/core/management/__init__.py#L33

    def load_command_class(app_name: str, name: str) -> None:
        module = import_module(f"{app_name}.management.commands.{name}")
        return injector.create_object(cast(Any, module).Command)

    management.load_command_class = load_command_class


def _get_before_request_hook(view_obj: Callable | type, request: HttpRequest) -> HttpResponse | None:
    """
    Return the before request hook if it exists.

    If the view object has attached before request hook it will be invoked before actual view logic.
    Hook may perform any some extra logic and either return None (meaning the normal view logic should be executed) or
    HttpResponse (meaning which means the execution must stop and the generated response must be returned).

    This method extracts the hook, if the hook doesn't exist - returns none, if hook exist launches it and returns hook
    result.

    :param view_obj: view function or class
    :param request: incoming http request
    :return: HtpResponse or none
    """
    hook = getattr(view_obj, "_on_before_request", None)
    if isfunction(hook):
        return hook(request)
    return None


def _get_after_request_hook(view_obj: Callable | type, response: HttpResponse) -> HttpResponse:
    """
    Return after request hook if it exists.

    If the view object has attached after request hook it will be invoked after view logic but before sending the
    http response to the further processing.

    Hook may perform any some extra logic and modify the response. The valid use case is to modify headers.

    This method extracts the hook, if the hook doesn't exist - returns original response,
    if hook exist launches it and returns result of the hook. Hook MUST return the HttpResponse.
    result.

    :param view_obj: view function or class
    :param response: response generated by view or before_request_hook
    :return: HtpResponse or none
    """
    hook = getattr(view_obj, "_on_after_request", None)
    if isfunction(hook):
        return hook(response)
    return response


# Code below is based on open-source project django_injector distributed under BSD-2 License
# and hosted at https://github.com/blubber/django_injector
# Bellow is a copy of original license
#
# BSD 2-Clause License
#
# Copyright (c) 2019, Tiemo
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


def _process_list(lst: Sequence, injector: Injector) -> list:
    return [__wrap_fun(f, injector) for f in lst]


def _process_resolver(resolver: URLResolver, injector: Injector) -> None:
    if resolver.callback:
        resolver.callback = __wrap_fun(resolver.callback, injector)

    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLPattern) and pattern.callback:
            pattern.callback = __wrap_fun(pattern.callback, injector)
        elif isinstance(pattern, URLResolver):
            _process_resolver(pattern, injector)

    if resolver._populated:
        resolver._populate()


def __check_existing_csrf_exempt(fun: Callable, wrapper: Callable) -> Callable:
    if hasattr(fun, "csrf_exempt") and fun.csrf_exempt:
        # Graphene-Django common solution for csrf_exempt is already applied in urls
        wrapper.csrf_exempt = True  # type: ignore
    return wrapper


def __wrap_function(fun: Callable, injector: Injector) -> Callable:
    @functools.wraps(fun)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if asyncio.iscoroutine(fun):
            return maybe_awaitable(injector.call_with_injection(callable=fun, args=args, kwargs=kwargs))
        return injector.call_with_injection(callable=fun, args=args, kwargs=kwargs)

    if asyncio.iscoroutine(fun):
        markcoroutinefunction(wrapper)

    return __check_existing_csrf_exempt(fun, wrapper)


def __instance_method_wrapper(im: Callable) -> Callable:
    @functools.wraps(im)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return im(*args, **kwargs)

    return wrapper


def __wrap_class_based_view(fun: Callable, injector: Injector) -> Callable:
    cls = cast(Any, fun).view_class

    try:
        initkwargs = cast(Any, fun).view_initkwargs
    except AttributeError:
        return fun

    # Code copied from Django's django.views.generic.base.View
    # to enable injection into class based view constructors.
    def view(request: Any, *args: Any, **kwargs: Any) -> Any:
        hook_result = _get_before_request_hook(fun, request)
        if hook_result:
            return hook_result

        self = injector.create_object(cls, additional_kwargs=initkwargs)
        injector.call_with_injection(
            callable=self.setup,
            args=(request,) + args,
            kwargs=kwargs,
        )
        if not hasattr(self, "request"):
            raise AttributeError(
                "%s instance has no 'request' attribute. Did you override "
                "setup() and forget to call super()?" % cls.__name__
            )
        return _get_after_request_hook(fun, self.dispatch(request, *args, **kwargs))

    cast(Any, view).view_class = cls
    cast(Any, view).view_initkwargs = initkwargs
    # masking our view for resolver match so we can understand what underlying
    # class-based view is there
    cast(Any, view).__module__ = cls.__module__
    cast(Any, view).__name__ = cls.__name__

    if hasattr(fun, "cls"):
        # Django Rest Framework APIView's as_view returns a callable with a cls attribute
        # instead of view_class. If the original callable has a cls attribute, assume it's
        # DRF. In addition, DRF views are csrf exempt by default, the SessionAuthentication
        # auth backend will selectively apply CSRF protection.
        cast(Any, view).cls = cls
        cast(Any, view).initkwargs = initkwargs
        view = csrf_exempt(view)

    if hasattr(cls, "view_is_async") and cls.view_is_async:
        markcoroutinefunction(view)

    return __check_existing_csrf_exempt(fun, view)


def __wrap_fun(fun: Callable, injector: Injector) -> Callable:
    if ismethod(fun):
        fun = __instance_method_wrapper(fun)

    # This blocks needs to come before the block that checks for __call__
    # to prevent infinite recursion.
    if hasattr(fun, "__bindings__"):
        return __wrap_function(fun, injector)

    if hasattr(fun, "view_class"):
        return __wrap_class_based_view(fun, injector)

    if callable(fun) and not isinstance(fun, type):
        try:
            type_hints = get_type_hints(fun)
        except (AttributeError, TypeError):
            # Some callables are not supported by get_type_hints:
            # https://github.com/alecthomas/flask_injector/blob/master/flask_injector/__init__.py#L75
            wrap_it = False
        else:
            type_hints.pop("return", None)
            wrap_it = type_hints != {}
        if wrap_it:
            return __wrap_function(fun, injector)  # Original: return wrap_fun(inject(fun), injector)

    return fun
