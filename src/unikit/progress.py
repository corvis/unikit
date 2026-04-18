#
#  Copyright 2026 by Dmitry Berezovsky, MIT License
#
import abc
import dataclasses
import datetime
import logging
from typing import Any, Generic, Self, TypeVar

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
