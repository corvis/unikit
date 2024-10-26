#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import datetime
from typing import Any

from asgiref.sync import sync_to_async

from unikit.lock.dto import Lock, SimpleLockDto
from unikit.lock.service import LockService


class NoopLockService(LockService):
    """A lock service that does nothing."""

    def acquire(
        self,
        op_name: str | None = None,
        target: str | None = None,
        op_params: dict[str, Any] | None = None,
        timeout: datetime.timedelta | None = None,
    ) -> Lock | None:
        """Acquire a lock synchronously."""
        timeout = timeout or datetime.timedelta(minutes=5)
        assert op_name or target, "Either op_name or target must be specified"
        target_id = self._create_target_id(target)
        full_op_name = self._create_op_name(op_name, op_params)
        lock_id = self._create_pk_for_lock(full_op_name, target_id)
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        lock = SimpleLockDto(
            lock_id=lock_id,
            operation_name=op_name,
            target_id=target_id,
            ts_acquired=now,
            ts_expires=now + timeout,
            secret="",
            owner=None,
        )
        return lock

    def get_lock(
        self,
        op_name: str | None = None,
        target: str | None = None,
        op_params: dict[str, Any] | None = None,
    ) -> Lock | None:
        """Get a lock synchronously."""
        return None

    def release(self, lock: Lock) -> None:
        """Release a lock synchronously."""
        pass  # noop

    async def aacquire(
        self,
        op_name: str | None = None,
        target: str | None = None,
        op_params: dict[str, Any] | None = None,
        timeout: datetime.timedelta | None = None,
    ) -> Lock | None:
        """Acquire a lock asynchronously."""
        return await sync_to_async(self.acquire)(op_name, target, op_params, timeout)

    async def aget_lock(
        self, op_name: str | None = None, target: str | None = None, op_params: dict[str, Any] | None = None
    ) -> Lock | None:
        """Get a lock asynchronously."""
        return None

    async def arelease(self, lock: Lock) -> None:
        """Release a lock asynchronously."""
        pass

    def clean_all_locks(self) -> None:
        """Clean all locks synchronously."""
        return None

    async def aclean_all_locks(self) -> None:
        """Clean all locks asynchronously."""
        return None
