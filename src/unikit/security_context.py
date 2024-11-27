#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
from contextvars import ContextVar
import logging
from typing import Any, Self, TypeVar

from injector import Injector, Provider

from unikit.abstract import Abstract, AbstractMeta
from unikit.di import DiProxy, root_container


class SecurityContextDto(dict[str, Any]):
    """Dto representing serializable SecurityContext."""

    @property
    def principal_id(self) -> str | None:
        """Get principal ID."""
        return self.get(BaseSecurityContext.KEY_PRINCIPAL_ID)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self:
        """Create SecurityContextDto from dictionary."""
        return cls(data or {})


class BaseSecurityContext(Abstract, metaclass=AbstractMeta):
    """Base class for Security Context."""

    KEY_PRINCIPAL_ID = "principal_id"

    @abc.abstractmethod
    def get_principal_id(self) -> str | None:
        """Get principal ID."""
        pass

    @classmethod
    @abc.abstractmethod
    def from_dto(cls, dto: SecurityContextDto) -> Self:
        """Create Security Context from serializable dto."""
        pass

    @classmethod
    @abc.abstractmethod
    async def afrom_dto(cls, dto: SecurityContextDto) -> Self:
        """Create Security Context from serializable dto."""
        pass

    def to_dto(self) -> SecurityContextDto:
        """Convert Security Context to serializable dictionary."""
        return SecurityContextDto({self.KEY_PRINCIPAL_ID: self.get_principal_id()})

    def __str__(self) -> str:
        return f"SecurityContext(principal_id={self.get_principal_id()})"


TBaseSecurityContext = TypeVar("TBaseSecurityContext", bound=BaseSecurityContext)


class SecurityContextProxy(DiProxy[BaseSecurityContext]):
    """DiProxy for Security Context."""

    pass


class ContextVarSecurityContextHolder:
    """
    A holder which utilizes ContextVar to store Security Context.

    It can be used to store security context in coroutine bound container. This can be useful to make Security Context
    available across your workers for example.

    Typical usage with DI:
        class _Module(DiModule):

            def configure(self, binder: injector.Binder):
                super().configure(binder)
                self.register_security_context(MySecurityContextInterface, ContextVarSecurityContextProvider)
    """

    def __init__(self) -> None:
        self.__security_context = ContextVar[BaseSecurityContext | None]("_unikit__security_context", default=None)

    def set_security_context(self, security_context: BaseSecurityContext | None) -> None:
        """Set Security Context."""
        self.__security_context.set(security_context)

    def get_security_context(self) -> BaseSecurityContext | None:
        """Get Security Context."""
        return self.__security_context.get()


default_security_context_holder = ContextVarSecurityContextHolder()


class ContextVarSecurityContextProvider(Provider[BaseSecurityContext]):
    """
    Provider for Security Context based on ContextVarSecurityContextHolder.

    Target context holder must be passed in constructor. If not passed, default_security_context_holder will be used.
    """

    def __init__(self, context_holder: ContextVarSecurityContextHolder | None = None):
        super().__init__()
        self._context_holder = context_holder or default_security_context_holder

    def get(self, injector: Injector) -> BaseSecurityContext:
        """Get Web Security Context."""
        security_context = self._context_holder.get_security_context()
        if security_context is None:
            raise ValueError("Security Context is not available.")
        return security_context


class SecurityContextLoggingFilter(logging.Filter):
    """Logging filter to attach Security Context entries to every log record."""

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log record."""
        try:
            security_context = root_container.get(BaseSecurityContext)  # type: ignore[type-abstract]
            if security_context:
                dto = security_context.to_dto()
                for k, v in dto.items():
                    setattr(record, self.prefix + k, v)
        except Exception:
            pass  # This filter should never raise an exception
        return True
