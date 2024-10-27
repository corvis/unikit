#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
from functools import cached_property
from typing import TYPE_CHECKING

from django.apps import apps
from django.core.management import BaseCommand

if TYPE_CHECKING:
    from unikit.contrib.django.taskiq.apps import TaskiqConfig


class BaseTaskiqCommand(BaseCommand):  # type: ignore[misc]
    """Base class for Taskiq management commands."""

    @cached_property
    def taskiq_app(self) -> "TaskiqConfig":
        """Return Taskiq application configuration."""
        return apps.get_app_config("django_taskiq")

    def _get_broker_name(self, args: tuple[str, ...]) -> str:
        if len(args) > 0 and not args[0].startswith("-"):
            broker_name = args[0]
            args = args[1:]
        else:
            broker_name = self.taskiq_app.default_broker_name
        return broker_name

    @staticmethod
    def _to_taskiq_class_path(path: str) -> str:
        return ":".join((path.rsplit(".", 1)))
