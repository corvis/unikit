#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
import datetime
import inspect
import json
import random
from typing import Any

from unikit.lock.service import LockService
from unikit.utils.types import none_raises

from .dto import CHARACTERS, DEFAULT_LOCK_TIMEOUT, RedisLock


class BaseRedisLockService(LockService, metaclass=abc.ABCMeta):
    """Base class for Redis lock services."""

    @classmethod
    def _parse_lock(cls, lock_obj_str: str | None, keep_secret: bool = False) -> RedisLock | None:
        if lock_obj_str is None:
            return None
        try:
            lock_obj: dict[str, Any] = json.loads(lock_obj_str)
            if "s" in lock_obj and not keep_secret:
                del lock_obj["s"]
        except Exception as e:
            raise ValueError(f"Invalid redis lock object: {e}") from e

        return RedisLock.from_dict(lock_obj)

    @classmethod
    def _random_secret(cls) -> str:
        return "".join(random.choice(CHARACTERS) for _ in range(22))

    @classmethod
    def _build_new_lock(
        cls,
        op_name: str | None = None,
        target: str | None = None,
        op_params: dict[str, Any] | None = None,
        timeout: datetime.timedelta | None = None,
    ) -> RedisLock:
        timeout = timeout or DEFAULT_LOCK_TIMEOUT
        assert op_name or target, "Either op_name or target must be specified"
        target_id = cls._create_target_id(target)
        full_op_name = cls._create_op_name(op_name, op_params)
        lock_id = cls._create_pk_for_lock(full_op_name, target_id)
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        lock = RedisLock(
            lock_id=lock_id,
            op_name=op_name,
            target_id=target_id,
            ts_acquired=now,
            ts_expires=now + timeout,
            lock_owner=cls._get_lock_owner(none_raises(inspect.currentframe()).f_back, cls._get_own_files_list()),
            secret=cls._random_secret(),
        )
        return lock

    @classmethod
    def _get_own_files_list(cls) -> tuple[str, ...]:
        return super()._get_own_files_list() + (__file__,)
