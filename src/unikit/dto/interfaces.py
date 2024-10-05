#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
from hashlib import sha1
from typing import Any


class Nameable(abc.ABC):
    """Represent the object which has a name."""

    @classmethod
    @abc.abstractmethod
    def get_name(cls) -> str:
        """Get the name of the object."""
        pass


class Hashable(abc.ABC):
    """Represent the object which can be hashed."""

    @abc.abstractmethod
    def get_hash(self) -> str:
        """Calculate hash for this object."""
        pass


class HashableHelper(Hashable, metaclass=abc.ABCMeta):
    """Helper class to implement Hashable interface."""

    def get_hash(self) -> str:
        """Calculate hash for this object."""
        return sha1(self._get_hashable_input().encode("utf-8")).hexdigest()

    @abc.abstractmethod
    def _get_hashable_input(self) -> str:
        """Get the input for hash calculation."""
        pass


class Bootstrapable(abc.ABC):
    """Represent the object which requires some heavy initialization before it can be used."""

    @classmethod
    @abc.abstractmethod
    def bootstrap(cls, *args: Any, **kwargs: Any) -> bool:
        """
        Bootstrap the object. This method is called in build time to ensure all required resources are loaded.

        :return: True if bootstrap has been performed, False if bootstrap is not required
        :raises: Exception if bootstrap has failed
        """
        pass
