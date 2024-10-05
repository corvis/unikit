#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
from typing import Any, Generator, Generic, TypeVar, cast

import injector
from typing_extensions import override

from unikit.dto.interfaces import Nameable

T = TypeVar("T")
D = TypeVar("D")
K = TypeVar("K")
TNameable = TypeVar("TNameable", bound=Nameable)


class AbstractRegistry(Generic[K, T], abc.ABC):
    """Abstract base class for any registry that defines all required interface methods."""

    def __init__(self, injector_: injector.Inject[injector.Injector]) -> None:
        super().__init__()
        self._registry: dict[K, T] = {}
        self._injector = injector_

    def register(self, name: K, obj: T) -> None:
        """Register an object in the registry."""
        self._registry[name] = obj

    @abc.abstractmethod
    def get(self, key: K) -> T | None:
        """Get an object from the registry."""
        pass

    def get_or_raise(self, key: K) -> T:
        """Get an object from the registry or raise a KeyError if it doesn't exist."""
        obj = self.get(key)
        if obj is None:
            raise KeyError(f"Key {key} not found in registry {self.__class__.__name__}")
        return obj

    def get_builder(self, key: K) -> injector.AssistedBuilder[T] | None:
        """Get an object builder from the registry."""
        obj = self._registry.get(key)
        if isinstance(obj, type):
            return self._injector.get(injector.AssistedBuilder[obj])  # type: ignore
        return None

    def get_builder_or_raise(self, key: K) -> injector.AssistedBuilder[T]:
        """Get an object builder from the registry or raise a KeyError if it doesn't exist."""
        obj = self.get_builder(key)
        if obj is None:
            raise KeyError(f"Key {key} not found in registry {self.__class__.__name__}")
        return obj

    def exists(self, key: K) -> bool:
        """Check if a key exists in the registry."""
        return key in self._registry

    @abc.abstractmethod
    def all(self) -> list[T]:
        """Return all registered objects as a list."""
        pass

    @abc.abstractmethod
    def get_all(self) -> Generator[T, T, None]:
        """Return all registered objects as a generator."""
        pass


class Registry(AbstractRegistry[K, T | type[T]], Generic[K, T]):
    """Simple registry implementation that stores objects in a dictionary."""

    def get(self, key: K) -> T | None:
        """Get an object from the registry."""
        obj = self._registry.get(key)
        if isinstance(obj, type):
            return cast(T, self._injector.get(obj))
        return obj

    def get_or_raise(self, key: K) -> T:
        """Get an object from the registry or raise a KeyError if it doesn't exist."""
        return cast(T, super().get_or_raise(key))

    def get_builder(self, key: K) -> injector.AssistedBuilder[T] | None:  # type: ignore[override]
        """Get an object builder from the registry."""
        return cast(injector.AssistedBuilder[T] | None, super().get_builder(key))

    def get_builder_or_raise(self, key: K) -> injector.AssistedBuilder[T]:  # type: ignore[override]
        """Get an object builder from the registry or raise a KeyError if it doesn't exist."""
        return cast(injector.AssistedBuilder[T], super().get_builder_or_raise(key))

    def all(self) -> list[T | type[T]]:
        """
        Return all registered objects.

        IMPORTANT classes won't be instantiated.
        :return: list of all registered objects
        """
        return list(self._registry.values())

    def get_all(self) -> Generator[T, T, None]:  # type: ignore[override]
        """
        Return all registered objects as a generator.

        :return: all registered objects
        """
        for key in self._registry.keys():
            yield self.get_or_raise(key)


class FactoryRegistry(AbstractRegistry[K, type[T]], Generic[K, T]):
    """Registry object which allows to use registered items as a base types for creating new objects."""

    @override
    def get(self, key: K) -> type[T] | None:
        """Get an object class from the registry."""
        obj_type = self._registry.get(key)
        return obj_type

    def build(self, key: K, params: dict[str, Any] | None = None) -> T | None:
        """
        Build the instance of the object from the registry with the given arguments.

        :param key: key of the object in the registry
        :param params: arguments for the object creation.
            None means that `__init__` method doesn't require any arguments except injected ones or defaults.
        """
        obj_type = self.get(key)
        if obj_type is None:
            return None
        return self._injector.create_object(obj_type, additional_kwargs=params)

    def build_or_raise(self, key: K, params: dict[str, Any] | None = None) -> T:
        """
        Build the instance of the object from the registry with the given arguments.

        :param key: key of the object in the registry
        :param params: arguments for the object creation

        Raise a KeyError if the object doesn't exist.
        """
        obj = self.build(key, params)
        if obj is None:
            raise KeyError(f"Key {key} not found in registry {self.__class__.__name__}")
        return obj

    def all(self) -> list[type[T]]:
        """
        Return all registered objects.

        :return: list of all registered objects
        """
        return list(self._registry.values())

    def get_all(self) -> Generator[type[T], type[T], None]:
        """
        Return all registered objects as a generator.

        :return: all registered objects
        """
        for key in self._registry.keys():
            yield self.get_or_raise(key)

    def build_all(self, params: dict[str, Any] | None = None) -> Generator[T, T, None]:
        """
        Build all registered objects with the given arguments.

        :param params: arguments for the object creation
        :return: all registered objects
        """
        for key in self._registry.keys():
            yield self.build_or_raise(key, params)


class NamedRegistry(Registry[str, TNameable], Generic[TNameable]):
    """Registry which allows to register objects by name."""

    def get_names(self) -> set[str]:
        """Return names of all registered objects."""
        return set(self._registry.keys())


class NamedFactoryRegistry(FactoryRegistry[str, TNameable], Generic[TNameable]):
    """Registry which allows to register objects by name."""

    def get_names(self) -> set[str]:
        """Return names of all registered objects."""
        return set(self._registry.keys())


class DefaultAwareMixin(Generic[D], metaclass=abc.ABCMeta):
    """Mixing for registries which have a default value."""

    def __init__(self, default: D | None = None) -> None:
        super().__init__()
        self.__default: D | None = default

    def get_default(self) -> D | None:
        """Return the default value for this registry."""
        return self.__default

    def set_default(self, default: D) -> None:
        """Set the default value for this registry."""
        self.__default = default
