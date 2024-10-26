#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import datetime
import logging
import string
from typing import Self

from unikit.lock.dto import Lock
from unikit.utils.types import none_raises

logger = logging.getLogger(__name__)

DEFAULT_LOCK_TIMEOUT = datetime.timedelta(minutes=5)
CHARACTERS = string.ascii_letters + string.digits


class RedisLock(Lock):
    """Redis lock object."""

    def __init__(
        self,
        lock_id: str,
        op_name: str | None,
        target_id: str | None,
        ts_acquired: datetime.datetime | None = None,
        ts_expires: datetime.datetime | None = None,
        lock_owner: str | None = None,
        secret: str | None = None,
    ) -> None:
        super().__init__()
        self.__secret = secret
        self.__lock_id = lock_id
        self.__op_name = op_name
        self.__lock_owner = lock_owner
        self.__target_id = target_id
        self.__ts_acquired = ts_acquired or datetime.datetime.now(tz=datetime.timezone.utc)
        self.__ts_expires = ts_expires or self.__ts_acquired + DEFAULT_LOCK_TIMEOUT

    def __str__(self) -> str:
        data = f"ObjectLock({self.get_target_id()}" if self.get_target_id() else f"OpLock({self.get_operation_name()}"
        data += f", expires at {self.get_ts_expires().isoformat()})"
        return data

    @classmethod
    def from_dict(cls, d: dict[str, str | None]) -> Self:
        """Create a lock object from a dictionary."""
        try:
            return cls(
                lock_id=none_raises(d["id"]),
                op_name=d.get("op"),
                target_id=d.get("t"),
                ts_acquired=datetime.datetime.fromisoformat(none_raises(d["acq"])),
                ts_expires=datetime.datetime.fromisoformat(none_raises(d["exp"])),
                secret=d.get("s"),
                lock_owner=d.get("own"),
            )
        except KeyError as e:
            raise ValueError(f"Invalid redis lock object. Missing field {e}. Object: {d}")
        except ValueError as e:
            raise ValueError(f"Invalid redis lock object. Invalid timestamp: {e}") from e

    def get_lock_id(self) -> str:
        """Get the lock ID."""
        return self.__lock_id

    def get_operation_name(self) -> str | None:
        """Get the operation name."""
        return self.__op_name

    def get_target_id(self) -> str | None:
        """Get the target ID."""
        return self.__target_id

    def get_ts_acquired(self) -> datetime.datetime:
        """Get the timestamp when the lock was acquired."""
        return self.__ts_acquired

    def get_ts_expires(self) -> datetime.datetime:
        """Get the timestamp when the lock expires."""
        return self.__ts_expires

    def get_secret(self) -> str:
        """Get the lock secret."""
        return none_raises(self.__secret)

    def get_owner(self) -> str | None:
        """Get the lock owner."""
        return self.__lock_owner

    def to_dict(self) -> dict[str, str | None]:
        """Convert the lock object to a dictionary."""
        return dict(
            id=self.get_lock_id(),
            op=self.get_operation_name(),
            t=self.get_target_id(),
            acq=self.get_ts_acquired().isoformat(),
            exp=self.get_ts_expires().isoformat(),
            s=self.__secret,
            own=self.__lock_owner,
        )

    def clone(
        self,
        ts_acquired: datetime.datetime | None = None,
        ts_expires: datetime.datetime | None = None,
    ) -> Self:
        """Clone the lock object with new timestamps."""
        return self.__class__(
            lock_id=self.get_lock_id(),
            op_name=self.get_operation_name(),
            target_id=self.get_target_id(),
            ts_acquired=ts_acquired or self.get_ts_acquired(),
            ts_expires=ts_expires or self.get_ts_expires(),
            lock_owner=self.get_owner(),
            secret=self.get_secret(),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RedisLock):
            return False
        return self.get_lock_id() == other.get_lock_id() and self.get_ts_acquired() == other.get_ts_acquired()
