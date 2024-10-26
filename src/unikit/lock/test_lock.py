#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
import datetime
import time
import unittest

from unikit.lock.service import LockService


class BaseLockServiceTest(unittest.TestCase, metaclass=abc.ABCMeta):
    __test__ = False

    lock_service: LockService

    def setUp(self):
        self.lock_service = self._create_service()
        self.lock_service.clean_all_locks()

    @abc.abstractmethod
    def _create_service(self) -> LockService:
        pass

    def test_simple_acquire(self):
        lock1 = self.lock_service.acquire("my_key_1")
        self.assertIsNotNone(lock1)
        lock2 = self.lock_service.acquire("my_key_2")
        self.assertIsNotNone(lock2)
        self.assertNotEqual(lock1, lock2)

    def test_cant_acquire_twice_with_same_key(self):
        lock1 = self.lock_service.acquire("my_key")
        self.assertIsNotNone(lock1)
        lock2 = self.lock_service.acquire("my_key", timeout=datetime.timedelta(seconds=1))
        self.assertIsNone(lock2)

    def test_release(self):
        lock = self.lock_service.acquire("my_key")
        self.assertIsNotNone(lock)
        self.lock_service.release(lock)
        lock2 = self.lock_service.acquire("my_key")
        self.assertIsNotNone(lock2)

    def test_lock_expiration(self):
        lock = self.lock_service.acquire("my_key", timeout=datetime.timedelta(seconds=0.3))
        self.assertIsNotNone(lock)
        time.sleep(0.5)
        lock2 = self.lock_service.acquire("my_key")
        self.assertIsNotNone(lock2)

    def test_get_lock(self):
        lock = self.lock_service.acquire("my_key")
        self.assertIsNotNone(lock)
        lock2 = self.lock_service.get_lock("my_key")
        self.assertIsNotNone(lock2)
        self.assertEqual(lock, lock2)
        lock3 = self.lock_service.get_lock("my_key_2")
        self.assertIsNone(lock3)

    def test_wait_and_acquire_raise_timeout_error(self):
        lock = self.lock_service.acquire("test")
        self.assertIsNotNone(lock)
        with self.assertRaises(TimeoutError) as context:
            with self.lock_service.wait_and_acquire("test", waiting_timeout=datetime.timedelta(milliseconds=500)):
                pass
        self.assertIn("Cannot acquire lock", str(context.exception))
