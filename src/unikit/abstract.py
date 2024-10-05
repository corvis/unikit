#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
from typing import Any


class Abstract:
    """
    Marker class to mark a class as abstract.

    This object makes no sense without the `AbstractMeta` metaclass.
    See the `AbstractMeta` for usage instructions.
    """

    __slots__ = ()


class AbstractMeta(abc.ABCMeta):
    """
    Improved version of the standard ABCMeta metaclass for defining abstract classes.

    This object inherits the standard behavior of the ABCMeta but also allows to define abstract classes
    WITHOUT any ABSTRACT methods. This is particularly useful when you want to override just static fields in the
    descendants.

    Python standard considers class as abstract if it defines at least one abstract method. So if you want just a marker
    interface to be abstract, you have to define a dummy abstract method and then override it in the descendants.

    This meta actually does exactly the same behind the scene - when you mark you class with `Abstract` by adding this
    class into the list of baseclasses it will add a dummy abstract method to the class, if `Abstract` is not in the
    list of direct parents, it will be implemented automatically.

    It is safe to use this metaclass as a drop-in replacement for ABCMeta even if you don't need `Abstract` marker.

    Usage:

    ```python

    class MyAbstractClass(Abstract, metaclass=AbstractMeta):
        pass

    class MyImpl(MyAbstractClass):
        pass

    isabstract(MyAbstractClass)     # Is True
    isabstract(MyImpl)              # Is False
    ```
    """

    def __new__(
        mcls, name: str, bases: tuple[type, ...], namespace: dict[str, Any], /, **kwargs: Any
    ) -> "AbstractMeta":
        """See class description."""
        result = super().__new__(mcls, name, bases, namespace, **kwargs)
        from _abc import _abc_init  # type: ignore

        if Abstract in bases:
            result._abstract_dummy_abstract_method = lambda: None  # type: ignore
            result._abstract_dummy_abstract_method.__isabstractmethod__ = True  # type: ignore
            _abc_init(result)
        elif hasattr(result, "_abstract_dummy_abstract_method"):
            result._abstract_dummy_abstract_method = lambda: None
            _abc_init(result)
        return result
