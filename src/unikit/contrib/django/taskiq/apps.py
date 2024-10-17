#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import asyncio
from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string
from taskiq import AsyncBroker

from unikit.contrib.django.di.base import BaseDiSupportedApp
from unikit.contrib.taskiq.service import TaskiqWorkerService
from unikit.di import root_container
from unikit.utils.list_utils import ensure_list
from unikit.utils.logger import LogMixin
from unikit.worker import WorkerServiceRegistry


class TaskiqConfig(BaseDiSupportedApp, LogMixin):
    """
    TaskiqConfig is a Django application configuration for Taskiq.

    Supported Settings:
       - TASKIQ_BROKER_DEFINITION: str - Dotted path to the broker object instance to use,
        if ommited the new one will be created.
       - TASKIQ_BROKER_URL: str - URL to the broker.
       - TASKIQ_TASK_DISCOVERY_PATTERN: str - Glob pattern to discover tasks, default: `**/tasks.py`.
       - TASKIQ_RESULT_BACKEND_URL: str - URL to the result backend.
       - TASKIQ_RESULT_BACKEND_URL: str - URL to the result backend.
    """

    name = "unikit.contrib.django.taskiq"
    label = "django_taskiq"
    default = True

    def __init__(self, app_name: str, app_module: Any) -> None:
        super().__init__(app_name, app_module)
        self.broker_paths: dict[str, str] = {}
        self.brokers: dict[str, AsyncBroker] = {}
        self.task_discovery_pattern = "**/tasks.py"

    @property
    def default_broker_name(self) -> str:
        """Default broker name."""
        return next(iter(self.broker_paths))

    @property
    def default_broker_path(self) -> str:
        """Default broker path."""
        return self.broker_paths[self.default_broker_name]

    @property
    def default_broker(self) -> AsyncBroker:
        """Default broker instance."""
        return self.brokers[self.default_broker_name]

    def ready(self) -> None:
        """Django callback invoked when application is ready to be used."""
        super().ready()

        self.task_discovery_pattern = getattr(settings, "TASKIQ_TASK_DISCOVERY_PATTERN", self.task_discovery_pattern)

        broker_object_paths = getattr(settings, "TASKIQ_BROKER_DEFINITION", None)
        if broker_object_paths is not None:
            broker_object_paths = ensure_list(broker_object_paths)
            for bp in broker_object_paths:
                broker: AsyncBroker = import_string(bp)
                _, broker_name = bp.rsplit(".", 1)
                self.broker_paths[broker_name] = bp
                self.brokers[broker_name] = broker

        if not self.brokers:
            raise ValueError("TASKIQ_BROKER_OBJECT is not set, please provide a broker object.")

        broker_registry = root_container.get(WorkerServiceRegistry)
        for name, b in self.brokers.items():
            broker_registry.register(name, TaskiqWorkerService(b))

        asyncio.get_event_loop().run_until_complete(self._init_brokers())

    async def _init_brokers(self) -> None:
        await asyncio.gather(*[b.startup() for b in self.brokers.values()])
