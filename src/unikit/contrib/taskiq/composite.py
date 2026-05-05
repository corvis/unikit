#
#  Copyright 2026 by Dmitry Berezovsky, MIT License
#
"""Composite progress tracking for parent tasks that spawn subtasks."""

from __future__ import annotations

__all__ = ["TaskiqCompositeProgressTracker"]

from typing import TYPE_CHECKING, Any, Generic

from taskiq.depends.progress_tracker import TaskProgress

from unikit.progress import (
    CompositeProgressTracker,
    ProgressState,
    SubtaskHandle,
    TProgressState,
)
from unikit.utils import dict_utils
from unikit.utils.async_utils import run_coroutine_in_running_loop  # noqa: PLC0415
from unikit.worker import RESULT_KEY_PROGRESS_STATE

if TYPE_CHECKING:
    from unikit.contrib.taskiq.progress import TaskProgressReporter


class TaskiqCompositeProgressTracker(CompositeProgressTracker[TProgressState], Generic[TProgressState]):
    """
    Taskiq-specific composite progress tracker.

    Aggregates progress from subtasks by querying the Taskiq result backend
    for each subtask's progress or final result.
    """

    def __init__(
        self,
        progress_reporter: TaskProgressReporter,
        progress_state: TProgressState,
        report_every_x_updates: int = 1,
        poll_interval_seconds: float = CompositeProgressTracker.DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(progress_state, report_every_x_updates, poll_interval_seconds)
        self._progress_reporter = progress_reporter

    async def ainit(self) -> None:
        """Initialize asynchronous components."""
        await self.afetch_state()

    async def afetch_state(self) -> TProgressState:
        """Fetch state from the backend."""
        state_cls = self._state.__class__
        self._state = await self._progress_reporter.get_object(
            state_cls, key=RESULT_KEY_PROGRESS_STATE, on_missing=self._state
        )
        return self.state

    def fetch_state(self) -> TProgressState:
        """Fetch state from the backend."""
        return run_coroutine_in_running_loop(self.afetch_state())

    def _do_report_update(self) -> None:
        run_coroutine_in_running_loop(self._ado_report_update())

    async def _ado_report_update(self) -> None:
        await self._progress_reporter.set_object(self.state, key=RESULT_KEY_PROGRESS_STATE)

    async def _fetch_subtask_progress(self, handle: SubtaskHandle) -> ProgressState | None:
        """Fetch progress of a subtask from the Taskiq result backend."""
        broker = self._progress_reporter.context.broker

        # First try to get the final result (task completed)
        try:
            result = await broker.result_backend.get_result(handle.task_id, with_logs=False)
            if result is not None and not result.is_err:
                # Task completed successfully - check if result has progress state
                if isinstance(result.return_value, dict):
                    state = dict_utils.get_object(
                        result.return_value, ProgressState, key=RESULT_KEY_PROGRESS_STATE, on_missing=None
                    )
                    if state is not None:
                        return state
                # No progress in result - assume all items done successfully
                return ProgressState(
                    items_total=handle.items_total,
                    items_done=handle.items_total,
                    items_success=handle.items_total,
                    items_failed=0,
                    items_skipped=0,
                )
            elif result is not None and result.is_err:
                # Task failed entirely
                return ProgressState(
                    items_total=handle.items_total,
                    items_done=handle.items_total,
                    items_success=0,
                    items_failed=handle.items_total,
                    items_skipped=0,
                    failed_items={str(handle.task_id): str(result.error) or "Unknown error"},
                )
        except Exception:  # noqa: S110
            # Task might still be running or result backend might be unavailable, it's ok to fail here silently
            pass

        # Task still running - try to get progress
        try:
            progress: TaskProgress[dict[str, Any]] | None = await broker.result_backend.get_progress(handle.task_id)
            if progress is not None and progress.meta:
                state = dict_utils.get_object(
                    progress.meta, ProgressState, key=RESULT_KEY_PROGRESS_STATE, on_missing=None
                )
                if state is not None:
                    return state
        except Exception:
            self.log.warning("Error fetching progress for subtask %s", handle.task_id)

        return None
