#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import datetime
import json
from typing import Any, Sequence

from asgiref.sync import sync_to_async
from redis import StrictRedis

from unikit.lock.dto import Lock

from .base import BaseRedisLockService
from .dto import RedisLock


class RedisLockService(BaseRedisLockService):
    """Redis lock implementation based on sync Redis client."""

    def __init__(self, redis_url: str) -> None:
        super().__init__()
        self.__redis = StrictRedis.from_url(redis_url)

    def acquire(
        self,
        op_name: str | None = None,
        target: str | None = None,
        op_params: dict[str, Any] | None = None,
        timeout: datetime.timedelta | None = None,
    ) -> Lock | None:
        """Acquire a lock synchronously."""
        lock = self._build_new_lock(op_name, target, op_params, timeout)
        return self.__acquire_lock(lock)

    def release(self, lock: Lock) -> None:
        """Release a lock synchronously."""
        existing_lock = self.__get_lock(lock_id=lock.get_lock_id(), keep_secret=True)
        if existing_lock:
            if existing_lock.get_secret() != lock.get_secret():
                raise ValueError("Only lock owner can release the lock")
            self.__redis.delete(lock.get_lock_id())

    def delete(self, lock_id: str) -> None:
        """Delete a lock synchronously."""
        self.__redis.delete(lock_id)

    def get_all(self) -> Sequence[Lock]:
        """Get all locks synchronously."""
        result: list[Lock] = []
        keys = self.__redis.keys("*")
        for k in keys:  # type: ignore[union-attr]
            lock = self.__get_lock(str(k, encoding="utf-8"))
            if lock:
                result.append(lock)
        return result

    def clean_all_locks(self) -> None:
        """Clean all locks synchronously."""
        self.__redis.flushdb()

    def get_lock(
        self,
        op_name: str | None = None,
        target: str | None = None,
        op_params: dict[str, Any] | None = None,
    ) -> Lock | None:
        """Get a lock synchronously."""
        full_op_name = self._create_op_name(op_name, op_params)
        target_id = self._create_target_id(target)
        lock_id = self._create_pk_for_lock(full_op_name, target_id)
        return self.__get_lock(lock_id, keep_secret=False)

    def extend_lock(self, lock: RedisLock, new_expiration_ts: datetime.datetime) -> Lock:
        """Extend a lock synchronously."""
        lock_id = lock.get_lock_id()
        existing_lock = self._parse_lock(self.__redis.get(lock_id), keep_secret=True)  # type: ignore
        if existing_lock and existing_lock.get_secret() == lock.get_secret():
            self.__redis.pexpireat(lock_id, new_expiration_ts)
            return lock.clone(ts_expires=new_expiration_ts)
        else:
            raise ValueError(
                f"Unable to extend lock {lock_id}. Lock doesn't exist, already expired or you do "
                f"not have permissions"
            )

    async def aacquire(
        self,
        op_name: str | None = None,
        target: str | None = None,
        op_params: dict[str, Any] | None = None,
        timeout: datetime.timedelta | None = None,
    ) -> Lock | None:
        """Acquire a lock asynchronously."""
        return await sync_to_async(self.acquire)(op_name=op_name, target=target, op_params=op_params, timeout=timeout)

    async def aget_lock(
        self, op_name: str | None = None, target: str | None = None, op_params: dict[str, Any] | None = None
    ) -> Lock | None:
        """Get a lock asynchronously."""
        return await sync_to_async(self.get_lock)(op_name=op_name, target=target, op_params=op_params)

    async def arelease(self, lock: Lock) -> None:
        """Release a lock asynchronously."""
        return await sync_to_async(self.release)(lock)

    async def aclean_all_locks(self) -> None:
        """Clean all locks asynchronously."""
        return await sync_to_async(self.clean_all_locks)()

    def __get_lock(self, lock_id: str, keep_secret: bool = False) -> RedisLock | None:
        return self._parse_lock(
            self.__redis.get(lock_id),  # type: ignore[arg-type]
            keep_secret=keep_secret,
        )

    def __acquire_lock(self, lock: RedisLock) -> RedisLock | None:
        acquired = self.__redis.set(
            lock.get_lock_id(), value=json.dumps(lock.to_dict()), nx=True, pxat=lock.get_ts_expires()
        )
        return lock if acquired else None

    @classmethod
    def _get_own_files_list(cls) -> tuple[str, ...]:
        return super()._get_own_files_list() + (__file__,)
