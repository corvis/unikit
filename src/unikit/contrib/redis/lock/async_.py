#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import datetime
import json
from typing import Any

from redis.asyncio import StrictRedis

from unikit.contrib.redis.lock.base import BaseRedisLockService
from unikit.contrib.redis.lock.dto import RedisLock
from unikit.lock.dto import Lock
from unikit.utils.async_utils import run_async


class AsyncRedisLockService(BaseRedisLockService):
    """Redis lock implementation based on async Redis client."""

    def __init__(self, redis_url: str) -> None:
        super().__init__()
        self.__redis = StrictRedis.from_url(redis_url)
        self.__skip_files = self._get_own_files_list() + (__file__,)

    async def aacquire(
        self,
        op_name: str | None = None,
        target: str | None = None,
        op_params: dict[str, Any] | None = None,
        timeout: datetime.timedelta | None = None,
    ) -> Lock | None:
        """Acquire a lock asynchronously."""
        lock = self._build_new_lock(op_name, target, op_params, timeout)
        return await self.__acquire_lock(lock)

    async def aget_lock(
        self, op_name: str | None = None, target: str | None = None, op_params: dict[str, Any] | None = None
    ) -> Lock | None:
        """Get a lock asynchronously."""
        full_op_name = self._create_op_name(op_name, op_params)
        target_id = self._create_target_id(target)
        lock_id = self._create_pk_for_lock(full_op_name, target_id)
        return await self.__get_lock(lock_id, keep_secret=False)

    async def arelease(self, lock: Lock) -> None:
        """Release a lock asynchronously."""
        existing_lock = await self.__get_lock(lock_id=lock.get_lock_id(), keep_secret=True)
        if existing_lock:
            if existing_lock.get_secret() != lock.get_secret():
                raise ValueError("Only lock owner can release the lock")
            await self.__redis.delete(lock.get_lock_id())

    async def aclean_all_locks(self) -> None:
        """Clean all locks asynchronously."""
        await self.__redis.flushdb()

    def acquire(
        self,
        op_name: str | None = None,
        target: str | None = None,
        op_params: dict[str, Any] | None = None,
        timeout: datetime.timedelta | None = None,
    ) -> Lock | None:
        """Acquire a lock synchronously."""
        return run_async(self.aacquire(op_name=op_name, target=target, op_params=op_params, timeout=timeout))

    def get_lock(
        self, op_name: str | None = None, target: str | None = None, op_params: dict[str, Any] | None = None
    ) -> Lock | None:
        """Get a lock synchronously."""
        return run_async(self.aget_lock(op_name=op_name, target=target, op_params=op_params))

    def release(self, lock: Lock) -> None:
        """Release a lock synchronously."""
        run_async(self.arelease(lock))

    def clean_all_locks(self) -> None:
        """Clean all locks synchronously."""
        run_async(self.aclean_all_locks())

    async def dispose(self) -> None:
        """Dispose the service."""
        await self.__redis.aclose()

    async def __acquire_lock(self, lock: RedisLock) -> RedisLock | None:
        acquired = await self.__redis.set(
            lock.get_lock_id(), value=json.dumps(lock.to_dict()), nx=True, pxat=lock.get_ts_expires()
        )
        return lock if acquired else None

    async def __get_lock(self, lock_id: str, keep_secret: bool = False) -> RedisLock | None:
        return self._parse_lock(
            await self.__redis.get(lock_id),
            keep_secret=keep_secret,
        )
