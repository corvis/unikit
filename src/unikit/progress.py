#
#  Copyright 2026 by Dmitry Berezovsky, MIT License
#
import abc
import asyncio
import dataclasses
import datetime
import logging
import time
from typing import Any, Generic, Self, TypeVar

from unikit.utils.async_utils import run_coroutine_in_running_loop
from unikit.utils.logger import LogMixin
from unikit.utils.time_utils import datetime_now

task_progress_logger = logging.getLogger("unikit.progress.ProgressState")


@dataclasses.dataclass(kw_only=True)
class ProgressState:
    """Dto for progress state."""

    pct: float | None = None
    """Percent of completion, if available (1-100)."""
    items_done: int | None = None
    """Number of items processed so far (regardless of the processing outcome), if available."""
    items_success: int | None = None
    """Number of items processed successfully, if available."""
    items_failed: int | None = None
    """Number of items processed with failure, if available."""
    items_skipped: int | None = None
    """Number of items skipped, if available."""
    items_total: int | None = None
    """Total number of which were sent for processing, if available."""
    eta_seconds: int | None = None
    """Estimated time of completion in seconds, if available."""
    failed_items: dict[str, str] = dataclasses.field(default_factory=dict)
    """Dictionary of failed items with their IDs as keys and failure reasons as values."""
    current_status_msg: str | None = None
    """Current status message, if available."""
    ts_started: datetime.datetime | None = dataclasses.field(default_factory=datetime_now)
    """Timestamp when the processing started, if available."""
    meta: dict[str, Any] = dataclasses.field(default_factory=dict)
    """Additional metadata, if needed."""

    def __post_init__(self) -> None:
        if self.ts_started and isinstance(self.ts_started, str):
            try:
                parsed = datetime.datetime.fromisoformat(self.ts_started)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=datetime.UTC)
                self.ts_started = parsed
            except ValueError:
                self.ts_started = None

    @property
    def progress_percent(self) -> float | None:
        """Get the progress percentage."""
        if self.pct is not None:
            return self.pct
        elif self.items_done and self.items_total:
            return (self.items_done / self.items_total) * 100.0
        return None

    @property
    def eta(self) -> datetime.timedelta | None:
        """
        Get the estimated time of completion.

        If :attr:`eta_seconds` is set, it is returned directly. Otherwise, the ETA is estimated
        dynamically from the elapsed time since :attr:`ts_started` and the number of items already
        processed relative to the total, provided both ``items_done`` and ``items_total`` are
        available and at least one item has been processed.

        :return: Estimated remaining time, or ``None`` if it cannot be determined.
        """
        if self.eta_seconds is not None:
            return datetime.timedelta(seconds=self.eta_seconds)
        if self.ts_started and self.items_done and self.items_total and 0 < self.items_done < self.items_total:
            elapsed: datetime.timedelta = datetime_now() - self.ts_started
            rate = elapsed.total_seconds() / self.items_done
            remaining_items = self.items_total - self.items_done
            return datetime.timedelta(seconds=rate * remaining_items)
        return None

    @property
    def speed(self) -> float | None:
        """
        Get the estimated processing speed in items per second.

        Calculated from the elapsed time since :attr:`ts_started` and the number of items already
        processed. Requires both :attr:`ts_started` and :attr:`items_done` to be set and at least
        one item to have been processed.

        :return: Processing speed in items/sec rounded to 1 decimal place, or ``None`` if it cannot
            be determined.
        """
        if self.ts_started and self.items_done and self.items_done > 0:
            elapsed_seconds = (datetime_now() - self.ts_started).total_seconds()
            if elapsed_seconds > 0:
                return round(self.items_done / elapsed_seconds, 1)
        return None

    def register_successful(self, num: int = 1) -> Self:
        """Register successful item."""
        if self.items_done is None:
            self.items_done = 0
        self.items_done += num
        if self.items_success is None:
            self.items_success = 0
        self.items_success += num
        return self

    def register_failed(self, num: int = 1, item_id: str | None = None, fail_reason: str | None = None) -> Self:
        """Register failed item."""
        if self.items_done is None:
            self.items_done = 0
        if self.items_failed is None:
            self.items_failed = 0
        self.items_failed += num
        if item_id:
            self.failed_items[item_id] = fail_reason or ""
        return self

    def register_failed_with_details(self, item_id: str, fail_reason: str | None = None) -> Self:
        """Register failed item with details."""
        if self.items_done is None:
            self.items_done = 0
        self.items_done += 1
        if self.items_failed is None:
            self.items_failed = 0
        self.items_failed += 1
        if item_id:
            self.failed_items[item_id] = fail_reason or ""
        return self

    def register_skipped(self, num: int = 1) -> Self:
        """Register skipped item."""
        if self.items_done is None:
            self.items_done = 0
        self.items_done += num
        if self.items_skipped is None:
            self.items_skipped = 0
        self.items_skipped += num
        return self

    def register_progress(
        self, success: int | None = None, failed: int | None = None, skipped: int | None = None
    ) -> Self:
        """Register progress."""
        self.register_successful(success or 0).register_failed(failed or 0).register_skipped(skipped or 0)
        return self

    def register_percent(self, pct: float) -> Self:
        """Register progress percentage."""
        self.pct = pct
        self.items_done = None
        self.items_total = None
        self.items_failed = None
        self.items_skipped = None
        self.items_success = None
        return self

    def reset_batch_size(self, total_items: int) -> Self:
        """
        Set total items count to 0.

        This also enables percentage tracking based on processed items.
        """
        self.items_total = total_items
        self.items_failed = self.items_done = self.items_skipped = self.items_success = 0
        self.ts_started = datetime_now()
        return self

    def set_status_msg(self, msg: str) -> Self:
        """Set current status message."""
        self.current_status_msg = msg
        task_progress_logger.info("Progress status updated: %s", msg)
        return self

    def clear_status_msg(self) -> Self:
        """Clear current status message."""
        self.current_status_msg = None
        return self

    @property
    def is_empty(self) -> bool:
        """Return True if the progress state is empty."""
        return self.items_total is None and self.pct is None

    @classmethod
    def create_by_items(cls, total_items: int, eta: datetime.timedelta | None = None) -> Self:
        """Create progress state by total items count."""
        return cls(items_total=total_items, items_done=0, eta_seconds=int(eta.total_seconds()) if eta else None)

    def __str__(self) -> str:
        status_msg = ("Status: " + self.current_status_msg if self.current_status_msg else "") + " "
        pct = round(self.progress_percent, 2) if self.progress_percent is not None else "N/A"
        return (
            status_msg + f"Progress(pct={pct}, items_done={self.items_done}, items_success={self.items_success}, "
            f"items_failed={self.items_failed}, items_skipped={self.items_skipped}, items_total={self.items_total}"
            + (f", eta={self.eta}, speed={self.speed} items/sec" if self.eta else "")
            + ")"
        )


TProgressState = TypeVar("TProgressState", bound=ProgressState)


class ProgressTracker(Generic[TProgressState], LogMixin, metaclass=abc.ABCMeta):
    """
    Progress tracker which allows long bulk processing tasks to report execution progress.

    This object establishes abstraction layer between task and result backend which used to capture progress and result.
    Typical usage:

    1. Your task creates an instance of tracker.
    2. You pass an instance as a parameter to your service which does some bulk processing.
    3. Service updates status like `tracker.register_success()`
    4. Service tracks progress by calling `tracker.track()` or `tracker.atrack()`
    """

    def __init__(self, progress_state: TProgressState, report_every_x_updates: int = 5) -> None:
        self._state = progress_state
        self.report_every_x_updates = report_every_x_updates
        self._untracked_updates = 0

    @property
    def state(self) -> TProgressState:
        """Get the current progress state."""
        return self._state

    def track(self) -> None:
        """
        Register progress update.

        This method should be called by the service to report progress updates. Under the hood it invokes storage
        backend to persist progres data.
        """
        self._untracked_updates += 1
        try:
            if self._untracked_updates >= self.report_every_x_updates:
                self._do_report_update()
        finally:
            self._untracked_updates = 0

    async def atrack(self) -> None:
        """
        Register progress update.

        This method should be called by the service to report progress updates. Under the hood it invokes storage
        backend to persist progres data.
        """
        self._untracked_updates += 1
        try:
            if self._untracked_updates >= self.report_every_x_updates:
                await self._ado_report_update()
        finally:
            self._untracked_updates = 0

    async def ainit(self) -> None:
        """
        Initialize the asynchronous components if needed.

        Should be overriden by child class.
        """
        pass

    @abc.abstractmethod
    def fetch_state(self) -> TProgressState:
        """Fetch state from the backend."""
        pass

    @abc.abstractmethod
    async def afetch_state(self) -> TProgressState:
        """Fetch state from the backend."""
        pass

    @abc.abstractmethod
    def _do_report_update(self) -> None:
        pass

    @abc.abstractmethod
    async def _ado_report_update(self) -> None:
        pass


class SimpleProgressTracker(ProgressTracker[TProgressState], Generic[TProgressState]):
    """Simple progress tracker which does not publish progres, just allows tracking internal state."""

    def fetch_state(self) -> TProgressState:
        """Noop."""
        return self.state

    async def afetch_state(self) -> TProgressState:
        """Noop."""
        return self.state

    def _do_report_update(self) -> None:
        pass

    async def _ado_report_update(self) -> None:
        pass

    @classmethod
    def create(cls) -> "SimpleProgressTracker[ProgressState]":
        """Create a new instance of the progress tracker with default Progres State implementation attached."""
        return SimpleProgressTracker[ProgressState](ProgressState())


@dataclasses.dataclass(kw_only=True)
class SubtaskHandle:
    """Represents a registered subtask for composite progress tracking."""

    task_id: str
    """Unique identifier of the subtask."""
    items_total: int = 1
    """Number of items this subtask is responsible for processing."""


class CompositeProgressTracker(ProgressTracker[TProgressState], Generic[TProgressState], metaclass=abc.ABCMeta):
    """
    A progress tracker that aggregates progress from multiple subtasks.

    This tracker is used by parent tasks that spawn child (sub) tasks and need to present
    a unified progress view to the caller. The parent registers subtask handles, and this
    tracker periodically polls their progress and aggregates it into the parent's ProgressState.

    Subclasses must implement :meth:`_fetch_subtask_progress` to retrieve the progress
    state of individual subtasks from the specific backend.
    """

    DEFAULT_POLL_INTERVAL_SECONDS: float = 2.0

    def __init__(
        self,
        progress_state: TProgressState,
        report_every_x_updates: int = 5,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(progress_state, report_every_x_updates)
        self._subtasks: list[SubtaskHandle] = []
        self._poll_interval_seconds = poll_interval_seconds

    @property
    def subtasks(self) -> list[SubtaskHandle]:
        """Get the list of registered subtask handles."""
        return self._subtasks

    def register_subtask(self, task_id: str, items_total: int = 1) -> SubtaskHandle:
        """
        Register a subtask for progress aggregation.

        :param task_id: unique identifier of the subtask.
        :param items_total: number of items this subtask is responsible for.
        :return: the created SubtaskHandle.
        """
        handle = SubtaskHandle(task_id=task_id, items_total=items_total)
        self._subtasks.append(handle)
        return handle

    def register_subtasks(self, task_ids: list[str], items_per_task: int = 1) -> list[SubtaskHandle]:
        """
        Batch-register multiple subtasks.

        :param task_ids: list of subtask identifiers.
        :param items_per_task: number of items each subtask is responsible for.
        :return: list of created SubtaskHandle objects.
        """
        return [self.register_subtask(tid, items_per_task) for tid in task_ids]

    @abc.abstractmethod
    async def _fetch_subtask_progress(self, handle: SubtaskHandle) -> ProgressState | None:
        """
        Fetch the progress state of a single subtask.

        Implementations should return the subtask's current ProgressState, or None if not available.
        If the subtask has completed (successfully or with failure) but no progress is available,
        implementation should return a ProgressState with items_done == handle.items_total.

        :param handle: the subtask handle to fetch progress for.
        :return: the subtask's progress state, or None if unavailable.
        """
        pass

    async def aaggregate(self, max_concurrency: int | None = 10) -> None:
        """
        Fetch progress from all subtasks concurrently and aggregate into the parent's ProgressState (async).

        This updates items_done, items_success, items_failed, items_skipped, items_total,
        and failed_items on the parent state.

        :param max_concurrency: maximum number of concurrent backend fetches. If None, all subtasks
            are fetched simultaneously via :func:`asyncio.gather`. Pass a positive integer to limit
            parallelism (e.g. when hitting a rate-limited backend).
        """
        total, done, success, failed, skipped = 0, 0, 0, 0, 0
        failed_items: dict[str, str] = {}

        async def _fetch(handle: SubtaskHandle) -> tuple[SubtaskHandle, ProgressState | None]:
            return handle, await self._fetch_subtask_progress(handle)

        if max_concurrency is None:
            results = await asyncio.gather(*(_fetch(h) for h in self._subtasks))
        else:
            semaphore = asyncio.Semaphore(max_concurrency)

            async def _fetch_limited(handle: SubtaskHandle) -> tuple[SubtaskHandle, ProgressState | None]:
                async with semaphore:
                    return await _fetch(handle)

            results = await asyncio.gather(*(_fetch_limited(h) for h in self._subtasks))

        for handle, sub_state in results:
            total += handle.items_total
            if sub_state is None:
                continue
            done += sub_state.items_done or 0
            success += sub_state.items_success or 0
            failed += sub_state.items_failed or 0
            skipped += sub_state.items_skipped or 0
            if sub_state.failed_items:
                failed_items.update(sub_state.failed_items)

        self._state.items_total = total
        self._state.items_done = done
        self._state.items_success = success
        self._state.items_failed = failed
        self._state.items_skipped = skipped
        self._state.failed_items = failed_items
        self._state.pct = None  # let progress_percent compute from items

    def aggregate(self, max_concurrency: int | None = 10) -> None:
        """
        Fetch progress from all subtasks and aggregate into the parent's ProgressState (sync).

        This is a synchronous wrapper around :meth:`aaggregate`.

        :param max_concurrency: maximum number of concurrent backend fetches. If None, all subtasks
            are fetched simultaneously via :func:`asyncio.gather`. Pass a positive integer to limit
            parallelism (e.g. when hitting a rate-limited backend).
        """
        run_coroutine_in_running_loop(self.aaggregate(max_concurrency))

    @property
    def all_subtasks_complete(self) -> bool:
        """Return True if all subtasks have completed (items_done >= items_total)."""
        if not self._subtasks:
            return True
        total = sum(h.items_total for h in self._subtasks)
        return (self._state.items_done or 0) >= total

    async def await_for_subtasks(self, poll_interval: float | None = None, max_concurrency: int | None = 10) -> None:
        """
        Poll subtask progress until all subtasks are complete, reporting progress along the way (async).

        :param poll_interval: seconds between polls; defaults to poll_interval_seconds set at init.
        :param max_concurrency: maximum concurrent backend fetches per poll cycle; None means unlimited.
        """
        interval = poll_interval if poll_interval is not None else self._poll_interval_seconds
        while not self.all_subtasks_complete:
            await self.aaggregate(max_concurrency=max_concurrency)
            await self._ado_report_update()
            await asyncio.sleep(interval)

    def wait_for_subtasks(self, poll_interval: float | None = None, max_concurrency: int | None = 10) -> None:
        """
        Poll subtask progress until all subtasks are complete, reporting progress along the way (sync).

        :param poll_interval: seconds between polls; defaults to poll_interval_seconds set at init.
        :param max_concurrency: maximum concurrent backend fetches per poll cycle; None means unlimited.
        """
        interval = poll_interval if poll_interval is not None else self._poll_interval_seconds
        while not self.all_subtasks_complete:
            time.sleep(interval)
            run_coroutine_in_running_loop(self.aaggregate(max_concurrency=max_concurrency))
            self._do_report_update()
