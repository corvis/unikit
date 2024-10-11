#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
from django.apps import apps
from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin


class InjectRequestMiddleware(MiddlewareMixin):  # type: ignore[misc]
    """Middleware that injects the current request into the injector."""

    app = apps.get_app_config("django_di")

    def process_request(self, request: HttpRequest) -> None:
        """Set current request to the injector."""
        self.app.django_module.set_request(request)
