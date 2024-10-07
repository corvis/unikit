#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
from typing import Any, Callable

from django.apps import apps
from django.http import HttpRequest


def inject_request_middleware(get_response: Callable) -> Callable:
    """Middleware that injects the current request into the injector."""
    app = apps.get_app_config("django_di")

    def middleware(request: HttpRequest) -> Any:
        """Middleware that injects the current request into the injector."""
        app.django_module.set_request(request)
        return get_response(request)

    return middleware
