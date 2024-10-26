#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import os
import unittest

from unikit.contrib.redis.lock.async_ import AsyncRedisLockService
from unikit.contrib.redis.lock.sync import RedisLockService
from unikit.lock.service import LockService
from unikit.lock.test_lock import BaseLockServiceTest


@unittest.skipIf(os.environ.get("REDIS_CACHE_URL") is None, "Redis is not available, set REDIS_CACHE_URL env var")
class RedisLockServiceTest(BaseLockServiceTest):
    __test__ = True

    def _create_service(self) -> LockService:
        return RedisLockService(redis_url=os.environ.get("REDIS_CACHE_URL", "redis://localhost:1979/0"))


@unittest.skipIf(os.environ.get("REDIS_CACHE_URL") is None, "Redis is not available, set REDIS_CACHE_URL env var")
class AsyncRedisLockServiceTest(BaseLockServiceTest):
    __test__ = True

    def _create_service(self) -> LockService:
        return AsyncRedisLockService(redis_url=os.environ.get("REDIS_CACHE_URL", "redis://localhost:1979/0"))
