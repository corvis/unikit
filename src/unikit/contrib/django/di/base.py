#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
import logging
from typing import Any

from django.apps import AppConfig

from unikit.di import root_container

logger = logging.getLogger(__name__)


class BaseDiSupportedApp(AppConfig, abc.ABC):  # type: ignore[misc]
    """Base class for applications that support Dependency Injection."""

    default = False

    def __init__(self, app_name: str, app_module: Any) -> None:
        super().__init__(app_name, app_module)
        self._di_container = root_container

    def _install_di_modules(self) -> None:
        """Scan current application for DI Module declaration and install discovered modules into root container."""
        logger.debug("Discovering DI modules for app %s", self.name)
        target_package_name = ".".join(self.__module__.split(".")[:-1])
        self._di_container.autodiscover_modules(target_package_name)

    def ready(self) -> None:
        """Django callback invoked when application is ready to be used."""
        super().ready()
        # Import DI context if any
        self._install_di_modules()
