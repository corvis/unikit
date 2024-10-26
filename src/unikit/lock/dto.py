#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
import dataclasses
import datetime

from unikit.abstract import Abstract, AbstractMeta


class Lock(Abstract, metaclass=AbstractMeta):
    """Lock interface."""

    @abc.abstractmethod
    def get_lock_id(self) -> str:
        """Get the lock ID."""
        pass

    @abc.abstractmethod
    def get_operation_name(self) -> str | None:
        """Get the operation name."""
        pass

    @abc.abstractmethod
    def get_target_id(self) -> str | None:
        """Get the target ID."""
        pass

    @abc.abstractmethod
    def get_secret(self) -> str:
        """Get the lock secret."""
        pass

    @abc.abstractmethod
    def get_owner(self) -> str | None:
        """Get the lock owner."""
        pass


@dataclasses.dataclass(kw_only=True)
class SimpleLockDto(Lock):
    """Simple lock data transfer object."""

    lock_id: str
    operation_name: str | None
    target_id: str | None
    secret: str
    owner: str | None
    ts_acquired: datetime.datetime
    ts_expires: datetime.datetime

    def get_lock_id(self) -> str:
        """Get the lock ID."""
        return self.lock_id

    def get_operation_name(self) -> str | None:
        """Get the operation name."""
        return self.operation_name

    def get_target_id(self) -> str | None:
        """Get the target ID."""
        return self.target_id

    def get_secret(self) -> str:
        """Get the lock secret."""
        return self.secret

    def get_owner(self) -> str | None:
        """Get the lock owner."""
        return self.owner
