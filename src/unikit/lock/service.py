#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import abc
from contextlib import asynccontextmanager, contextmanager
import datetime
import time
from types import FrameType
from typing import Any, AsyncIterator, Iterator, Never

from unikit.abstract import Abstract, AbstractMeta
from unikit.lock.dto import Lock


class LockService(Abstract, metaclass=AbstractMeta):
    """Abstract base class for lock services."""

    _MAX_CALL_STACK_DEPTH = 5

    @abc.abstractmethod
    def acquire(
        self,
        op_name: str | None = None,
        target: str | None = None,
        op_params: dict[str, Any] | None = None,
        timeout: datetime.timedelta | None = None,
    ) -> Lock | None:
        """
        Acquire a lock synchronously.

        :param op_name: The name of the operation.
        :param target: The target for the lock.
        :param op_params: Additional parameters for the operation.
        :param timeout: The timeout for the lock.
        :return: The acquired lock or None if the lock could not be acquired.
        """
        pass

    @abc.abstractmethod
    async def aacquire(
        self,
        op_name: str | None = None,
        target: str | None = None,
        op_params: dict[str, Any] | None = None,
        timeout: datetime.timedelta | None = None,
    ) -> Lock | None:
        """
        Acquire a lock asynchronously.

        :param op_name: The name of the operation.
        :param target: The target for the lock.
        :param op_params: Additional parameters for the operation.
        :param timeout: The timeout for the lock.
        :return: The acquired lock or None if the lock could not be acquired.
        """
        pass

    @abc.abstractmethod
    def get_lock(
        self,
        op_name: str | None = None,
        target: str | None = None,
        op_params: dict[str, Any] | None = None,
    ) -> Lock | None:
        """
        Retrieve an existing lock synchronously.

        :param op_name: The name of the operation.
        :param target: The target for the lock.
        :param op_params: Additional parameters for the operation.
        :return: The retrieved lock or None if the lock does not exist.
        """
        pass

    @abc.abstractmethod
    async def aget_lock(
        self,
        op_name: str | None = None,
        target: str | None = None,
        op_params: dict[str, Any] | None = None,
    ) -> Lock | None:
        """
        Retrieve an existing lock asynchronously.

        :param op_name: The name of the operation.
        :param target: The target for the lock.
        :param op_params: Additional parameters for the operation.
        :return: The retrieved lock or None if the lock does not exist.
        """
        pass

    @contextmanager
    def wait_and_acquire(
        self,
        op_name: str | None = None,
        target: str | None = None,
        waiting_timeout: datetime.timedelta | None = None,
        timeout: datetime.timedelta | None = None,
        op_params: dict[str, Any] | None = None,
    ) -> Iterator[Never]:
        """
        Context manager to wait and acquire a lock synchronously.

        :param op_name: The name of the operation.
        :param target: The target for the lock.
        :param waiting_timeout: The maximum time to wait for acquiring the lock.
        :param timeout: The timeout for the lock.
        :param op_params: Additional parameters for the operation.
        """
        timeout = timeout or datetime.timedelta(minutes=5)
        start = datetime.datetime.now()
        lock = self.acquire(op_name, target, timeout=timeout, op_params=op_params)
        while not lock:
            if waiting_timeout and datetime.datetime.now() - start > waiting_timeout:
                lock = self.get_lock(op_name, target, op_params)
                owner = lock.get_owner() if lock else None
                raise TimeoutError(
                    f"Cannot acquire lock(op={op_name}, target={target or 'n/a'}) within `{waiting_timeout}` timeout. "
                    f"Lock owner: {owner or 'n/a'}"
                )
            time.sleep(0.2)
            lock = self.acquire(op_name, target, op_params=op_params, timeout=timeout)
        try:
            yield  # type: ignore[misc]
        finally:
            self.release(lock)

    @asynccontextmanager
    async def await_and_acquire(
        self,
        op_name: str | None = None,
        target: str | None = None,
        waiting_timeout: datetime.timedelta | None = None,
        timeout: datetime.timedelta | None = None,
        op_params: dict[str, Any] | None = None,
    ) -> AsyncIterator[Never]:
        """
        Async context manager to wait and acquire a lock asynchronously.

        :param op_name: The name of the operation.
        :param target: The target for the lock.
        :param waiting_timeout: The maximum time to wait for acquiring the lock.
        :param timeout: The timeout for the lock.
        :param op_params: Additional parameters for the operation.
        """
        timeout = timeout or datetime.timedelta(minutes=5)
        start = datetime.datetime.now()
        lock = await self.aacquire(op_name, target, timeout=timeout, op_params=op_params)
        while not lock:
            if waiting_timeout and datetime.datetime.now() - start > waiting_timeout:
                lock = await self.aget_lock(op_name, target, op_params)
                owner = lock.get_owner() if lock else None
                raise TimeoutError(
                    f"Cannot acquire lock(op={op_name}, target={target or 'n/a'}) within `{waiting_timeout}` timeout. "
                    f"Lock owner: {owner or 'n/a'}"
                )
            time.sleep(0.2)
            lock = await self.aacquire(op_name, target, op_params=op_params, timeout=timeout)
        try:
            yield  # type: ignore[misc]
        finally:
            self.release(lock)

    @abc.abstractmethod
    def release(self, lock: Lock) -> None:
        """
        Release a lock synchronously.

        :param lock: The lock to be released.
        """
        pass

    @abc.abstractmethod
    async def arelease(self, lock: Lock) -> None:
        """
        Release a lock asynchronously.

        :param lock: The lock to be released.
        """
        pass

    @abc.abstractmethod
    def clean_all_locks(self) -> None:
        """Clean all locks synchronously."""
        pass

    @abc.abstractmethod
    async def aclean_all_locks(self) -> None:
        """Clean all locks asynchronously."""
        pass

    @classmethod
    def _create_target_id(cls, target: str | None = None) -> str | None:
        tpl = "node__{}"
        if target is None:
            return None
        elif isinstance(target, str):
            return tpl.format(target)
        raise ValueError(f"Unsupported target type: {type(target)}")

    @classmethod
    def _create_op_name(cls, op_name: str | None, op_params: dict[str, Any] | None) -> str | None:
        if not op_name:
            return None
        if not op_params:
            return op_name
        param_list = [f"{param}__{val}" for param, val in op_params.items()]
        return op_name + "|" + "|".join(param_list)

    @classmethod
    def _create_pk_for_lock(cls, op_name: str | None, target_id: str | None) -> str:
        if target_id:
            return f"target:{target_id}"
        elif op_name:
            return f"op:{op_name}"
        raise ValueError("Either name or target must be specified")

    @classmethod
    def _get_own_files_list(cls) -> tuple[str, ...]:
        """Return a list of files which needs to be dropped while scanning call-stack to resolve lock owner."""
        return __file__, "contextlib.py"

    @classmethod
    def _get_lock_owner(cls, frame: FrameType | None, skip_files: tuple[str, ...]) -> str | None:
        """
        Scan call stack to find the caller of `acquire` method outside LockService.

        It will be considered the owner of the lock.

        :param frame: call-stack frame to start analysis from
        :return: string describing the owner of the lock
        """
        depth = 0

        while frame and depth < cls._MAX_CALL_STACK_DEPTH:
            if frame.f_code.co_filename:
                should_skip = False
                for x in skip_files:
                    if frame.f_code.co_filename.endswith(x):
                        should_skip = True
                        break
                if not should_skip:
                    return "{} at {}:{}".format(
                        frame.f_code.co_name, frame.f_code.co_filename, frame.f_code.co_firstlineno
                    )
            frame = frame.f_back
            depth += 1
        return None
