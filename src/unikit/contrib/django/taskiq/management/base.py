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
