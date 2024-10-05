#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
from functools import wraps
import importlib
import importlib.util
import inspect
import logging
import typing
from typing import Any, Callable, Generic, Sequence, TypeAlias, TypeVar

import injector
from injector import T

from unikit.dto.interfaces import Bootstrapable, Nameable
from unikit.registry import Registry

logger = logging.getLogger(__name__)

# Types
IT = TypeVar("IT")
BindArg: TypeAlias = IT | Callable[..., IT] | injector.Provider[IT] | type[IT]


class DIContainerSetupError(Exception):
    """Error raised when the DI container setup fails."""

    pass


class DiPlaceholder:
    """Placeholder for the DI container to inject the value."""

    def __getattribute__(self, item: Any) -> Any:
        if item in ("__class__", "__deepcopy__", "__reduce_ex__", "__reduce__", "__getstate__"):
            return super().__getattribute__(item)
        raise RuntimeError(f"This parameter must be injected by DI container (invoked attribute: {item})")

    def __str__(self) -> str:
        return "Should be injected by DI container"

    def __repr__(self) -> str:
        return self.__str__()


PLACEHOLDER: Any = DiPlaceholder()


class InterfaceAwareProvider(injector.Provider[T], Generic[T], abc.ABC):
    """Base class for providers that are aware of the interface they provide."""

    def __init__(self, interface_cls: type[T] | None) -> None:
        self.iface_cls = interface_cls


class ClassListProvider(InterfaceAwareProvider[list[T]], Generic[T]):
    """Provides a list of instances from a given class."""

    def __init__(self, cls: type[T], interface_cls: type[list[T]] | None) -> None:
        """Initialize the provider."""
        self._cls = cls
        super().__init__(interface_cls=interface_cls)

    def get(self, injector: injector.Injector) -> list[T]:
        """Get the list of instances."""
        return [injector.create_object(self._cls)]


class InterfaceAwareClassProvider(InterfaceAwareProvider[T], injector.ClassProvider, Generic[T]):
    """Provides a class instance with the given interface."""

    def __init__(self, cls: type[T], interface_cls: type[T] | None) -> None:
        """Initialize the provider."""
        self._cls = cls
        super().__init__(interface_cls=interface_cls)

    def get(self, injector_: injector.Injector) -> T:  # type: ignore
        """Get the class instance."""
        return injector_.create_object(self._cls)


class MultiBindClassProvider(injector.MultiBindProvider):
    """A provider for a list of instances from a list of classes."""

    def __init__(self, classes: Sequence[type[T]], interface_cls: type[list[T]] | None) -> None:
        super().__init__()
        for cls in classes:
            self.append(ClassListProvider(cls, interface_cls))


class IfaceAwareSingletonScope(injector.SingletonScope):
    """A singleton scope that is aware of the interface of the provided object."""

    @injector.synchronized(injector.lock)
    def get(self, key: type[T], provider: injector.Provider[T]) -> injector.Provider[T]:
        """Get the provider."""

        if key in self._context:
            return self._context[key]
        elif (
            isinstance(provider, InterfaceAwareProvider) and provider.iface_cls and provider.iface_cls in self._context
        ):
            return self._context[provider.iface_cls]
        instance_provider = injector.InstanceProvider(provider.get(self.injector))
        self._context[key] = instance_provider
        if isinstance(provider, injector.MultiBindProvider) and isinstance(instance_provider._instance, list):  # noqa
            for x in instance_provider._instance:  # noqa
                self._context[x.__class__] = injector.InstanceProvider(x)
        if isinstance(provider, InterfaceAwareProvider) and provider.iface_cls:
            self._context[provider.iface_cls] = instance_provider
        return instance_provider


class DiModule(injector.Module):
    """Base class for DI modules."""

    def __init__(self, binder: injector.Binder | None = None) -> None:
        """Initialize the module."""
        super().__init__()
        self.__binder: injector.Binder | None = binder
        if binder:
            super().__call__(binder)

    def configure(self, binder: injector.Binder) -> None:
        """Configure DI container."""
        super().configure(binder)
        self.__binder = binder

    def register_singleton(self, interface: type, to: BindArg | None = None) -> None:
        """
        Register given interface and optionally implementation in DI container with SingletonScope.

        The instance will be created only once per DI container at the moment of first access.

        Skipped `to` argument is equivalent to `register_singleton(ClassA, ClassA)` and must be used in cases when you
        do not have a dedicated interface for the implementation (generally a bad practice).

        Important note: subsequent invocations with the same `interface` argument will __override__ previously set
        implementation.

        :param interface: interface to be registered
        :param to: implementation to be associated with given interface.
        """

        assert self.__binder is not None
        # noinspection PyTypeChecker
        self.__binder.bind(interface, to=to, scope=IfaceAwareSingletonScope)
        if interface and to and interface is not to and isinstance(to, type):
            # noinspection PyTypeChecker
            self.__binder.bind(
                to,
                to=InterfaceAwareClassProvider(to, interface_cls=interface),
                scope=IfaceAwareSingletonScope,
            )

    def register_singleton_impl(self, interface: type, to: Sequence[BindArg] | BindArg) -> None:
        """
        Similar to `register_singleton` but allows to register *multiple* implementations of the same interface.

        To access implementations you __must__ inject a `List` of interfaces, not a single interface.
        """
        assert self.__binder is not None
        if not isinstance(to, (list, tuple)):
            to = [to]
        self.__binder.multibind(
            list[interface],  # type: ignore
            MultiBindClassProvider(to, interface_cls=interface),  # type: ignore
            scope=IfaceAwareSingletonScope,
        )
        for x in to:
            if isinstance(x, type):
                self.register_singleton(interface=x, to=InterfaceAwareClassProvider(x, interface_cls=x))

    def add_to_registry(
        self, registry_cls: type[Registry], obj: BindArg, key: Any = None, skip_container: bool = False
    ) -> None:
        """Add given object to the registry."""
        assert self.__binder is not None
        assert not isinstance(registry_cls, Registry), "Registry class must be a subclass of Registry"
        interface = self.__get_registry_interface(registry_cls)
        try:
            self.__binder.get_binding(registry_cls)
        except injector.UnsatisfiedRequirement:
            self.register_singleton(registry_cls)
        registry = self.__binder.injector.get(registry_cls)
        if not skip_container:
            if interface is not None:
                self.register_singleton_impl(interface, obj)
            else:
                self.register_singleton(obj)  # type: ignore
        if key is None and isinstance(obj, Nameable) or (isinstance(obj, type) and issubclass(obj, Nameable)):
            registry.register(obj.get_name(), obj)
        else:
            if key is None:
                raise ValueError("Key must be provided")
            registry.register(key, obj)

    def __get_registry_interface(self, registry_cls: type[Registry]) -> type | None:
        for parent in registry_cls.mro():
            if not issubclass(parent, Registry):
                continue
            for base_class in getattr(parent, "__orig_bases__", ()):
                type_args = typing.get_args(base_class)
                if len(type_args) == 2:
                    return type_args[1]
                elif len(type_args) == 1:
                    return type_args[0]
        return None


class DiInjector(injector.Injector):
    """Extended injector with additional functionality."""

    def autodiscover_modules(self, packages: Sequence[str] | str) -> None:
        """Autodiscover modules in given packages and install them in DI container."""
        if isinstance(packages, str):
            packages = (packages,)
        for target_package_name in packages:
            self.__discover_module(target_package_name)

    def __discover_module(self, target_package_name: str) -> None:
        spec = importlib.util.find_spec(".di_context", target_package_name)
        if spec:
            try:
                module = importlib.import_module(spec.name)
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, DiModule) and obj is not DiModule and not inspect.isabstract(obj):
                        logger.info("Installing DI module %s at %s", name, spec.name)
                        self.binder.install(obj)
            except Exception as e:
                raise DIContainerSetupError(f"Unable to bootstrap DI container for {target_package_name}") from e

    def find_boostrapable(self) -> list[type[Bootstrapable]]:
        """Find all bootstrapable classes in DI container."""
        result: list[type[Bootstrapable]] = []
        for _, bindings in self.binder._bindings.items():
            for x in bindings:
                try:
                    if inspect.isclass(x) and issubclass(x, Bootstrapable):
                        result.append(x)
                except TypeError:
                    pass
        return result


class Initializable(abc.ABC):
    """
    Interface for objects that need to be initialized after creation.

    This might be useful if you have to create class instance before without DI context and have to inject
    dependencies later.
    """

    def __init__(self) -> None:
        super().__init__()
        self.__initialized = False

    def initialize(self, injector_: injector.Inject[injector.Injector]) -> None:
        """Initialize object."""
        injector_.call_with_injection(self._do_initialize)
        self.__initialized = True

    @abc.abstractmethod
    def _do_initialize(self, **kwargs: Any) -> None:
        pass

    @property
    def is_initialized(self) -> bool:
        """Return true if object is initialized."""
        return self.__initialized


root_container = DiInjector(auto_bind=False)
root_container.binder.bind(DiInjector, injector.InstanceProvider(root_container), scope=injector.SingletonScope)


def with_injection(fn: Callable[..., Any]) -> Callable[..., Any]:
    """
    Wrap given function with root_container.call_with_injection.

    INTENDED TO BE USED IN TESTS ONLY!
    :param fn: target function
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return root_container.call_with_injection(fn, args=args, kwargs=kwargs)

    return wrapper


def has_inject_marker(v: type) -> bool:
    """
    Return true if given type/type annotation is marked for injection.

    :param v: type to test
    :return: true if injector marker is present
    """
    return (
        injector._is_specialization(v, typing.Annotated)
        and injector._inject_marker in v.__metadata__  # type: ignore[attr-defined]
    )


class DiProxy(Generic[T]):
    """Proxy object that delegates all calls to the underlying object."""

    _OWN_PROPERTIES = ("_proxy_di_provider", "_proxy_injector")

    def __init__(self, di_provider: injector.Provider[T], injector: injector.Injector) -> None:
        self._proxy_di_provider = di_provider
        self._proxy_injector = injector

    @property
    def underlying_object(self) -> T:
        """Return the underlying object."""
        return self._proxy_di_provider.get(self._proxy_injector)

    def __getattr__(self, item: str) -> Any:
        if item in DiProxy._OWN_PROPERTIES:
            return super().__getattr__(item)  # type: ignore
        return getattr(self.underlying_object, item)

    def __setattr__(self, key: str, value: Any) -> None:
        if key in DiProxy._OWN_PROPERTIES:
            return super().__setattr__(key, value)
        return setattr(self.underlying_object, key, value)

    def __delattr__(self, item: str) -> None:
        if item in DiProxy._OWN_PROPERTIES:
            return super().__delattr__(item)
        return delattr(self.underlying_object, item)

    def __dir__(self) -> typing.Iterable[str]:
        return dir(self.underlying_object)

    def __str__(self) -> str:
        return f"Proxy<{str(self.underlying_object)}>"

    def __hasattr__(self, item: str) -> bool:
        return hasattr(self.underlying_object, item)

    def __eq__(self, other: Any) -> bool:
        return self.underlying_object == other
