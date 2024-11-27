#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
import logging
from typing import TYPE_CHECKING, Any, Generic, Self, TypeVar

from django.apps import AppConfig
from django.http import HttpRequest
from injector import Injector, Provider

from unikit.abstract import Abstract, AbstractMeta
from unikit.di import root_container
from unikit.security_context import BaseSecurityContext

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

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


TDjangoUser = TypeVar("TDjangoUser", bound="AbstractUser")


class BaseDjangoSecurityContext(BaseSecurityContext, Generic[TDjangoUser], Abstract, metaclass=AbstractMeta):
    """Base class for Django Security Context."""

    @abc.abstractmethod
    def get_current_user(self) -> TDjangoUser | None:
        """Get current user or None if context is anonymous."""
        pass

    def get_current_user_id(self) -> str:
        """
        Return serializable identifier of the current user.

        This identifier will be used to pass user identity between services e.g. via message broker.
        """
        user = self.get_current_user()
        return str(user.pk) if user else ""

    def get_principal_id(self) -> str | None:
        """Get principal ID."""
        return self.get_current_user_id()

    def __str__(self) -> str:
        return f"SecurityContext(user={self.get_current_user()})"


class BaseWebSecurityContext(BaseDjangoSecurityContext, metaclass=abc.ABCMeta):
    """Base class for Web Security Context."""

    @classmethod
    @abc.abstractmethod
    def from_http_request(cls, request: HttpRequest) -> Self:
        """Create Web Security Context from HTTP Request."""
        pass


class WebSecurityContextProvider(Provider[BaseWebSecurityContext]):
    """Provider for Web Security Context."""

    def __init__(self, context_cls: type[BaseWebSecurityContext]):
        super().__init__()
        self._context_cls = context_cls

    def get(self, injector: Injector) -> BaseWebSecurityContext:
        """Get Web Security Context."""
        request = injector.get(HttpRequest)
        if request is None:
            raise ValueError(
                "HttpRequest is not available in DI context. "
                "Have you installed `django_di` and "
                "added `unikit.contrib.django.di.middleware.InjectRequestMiddleware` middleware?"
            )
        return self._context_cls.from_http_request(request)
