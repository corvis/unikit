#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
from typing import Any, Generic, cast, overload

from taskiq import Context
from taskiq.depends.progress_tracker import TaskProgress, TaskState
from taskiq.kicker import _T
from taskiq_dependencies import Depends

from unikit.progress import ProgressState, ProgressTracker, TProgressState
from unikit.utils import dict_utils
from unikit.utils.default import OnErrorDef, raise_or_default
from unikit.worker import RESULT_KEY_PROGRESS_STATE


class TaskiqProgressTracker(ProgressTracker[TProgressState], Generic[TProgressState]):
    """Implementation of the ProgressTracker which reports progress to Taskiq."""

    def __init__(
        self,
        progress_reporter: "TaskProgressReporter",
        progress_state: TProgressState,
        report_every_x_updates: int = 5,
    ):
        super().__init__(progress_state, report_every_x_updates)
        self._progress_reporter = progress_reporter
        self._state_cls = self.state.__class__

    async def init(self) -> None:
        """Initialize asynchronous components."""
        await self.afetch_state()

    async def afetch_state(self) -> TProgressState:
        """Fetch state from the backend."""
        self._state = await self._progress_reporter.get_object(
            self._state_cls, key=RESULT_KEY_PROGRESS_STATE, on_missing=self._state
        )
        return self.state

    def fetch_state(self) -> TProgressState:
        """NOT IMPLEMENTED FOR TASKIQ."""
        raise NotImplementedError("Taskiq doesn't support sync operations")

    def _do_report_update(self) -> None:
        """NOT IMPLEMENTED FOR TASKIQ."""
        raise NotImplementedError("Taskiq doesn't support sync operations")

    async def _ado_report_update(self) -> None:
        await self._progress_reporter.set_object(self.state, key=RESULT_KEY_PROGRESS_STATE)
        await self.afetch_state()


class TaskProgressReporter:
    """Task's dependency to set progress."""

    def __init__(
        self,
        context: Context = Depends(),
    ) -> None:
        self.context = context

    async def set_object(self, *objects: Any, key: str | None = None) -> None:
        """Set object to progress."""
        progress = await self.get_progress()
        if progress is None:
            progress = TaskProgress(state=TaskState.STARTED, meta={})
        if progress.meta is None:
            progress.meta = {}
        dict_utils.set_objects(progress.meta, *objects, key=key)
        await self.context.broker.result_backend.set_progress(
            self.context.message.task_id,
            progress,
        )

    async def get_object(self, target_cls: type[_T], key: str | None = None, on_missing: OnErrorDef[Any] = None) -> Any:
        """Get object from progress."""
        progress = await self.get_progress()
        if progress is None:
            return raise_or_default(on_missing, "Progress is not available")
        if progress.meta is None:
            progress.meta = {}
        return dict_utils.get_object(progress.meta, target_cls, key=key, on_missing=on_missing)

    async def set_progress(
        self,
        state: TaskState | str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Set progress."""
        if meta is None:
            progress = await self.get_progress()
            meta = progress.meta if progress else None

        progress = TaskProgress(state=state, meta=meta)

        await self.context.broker.result_backend.set_progress(
            self.context.message.task_id,
            progress,
        )

    async def get_progress(self) -> TaskProgress[dict[str, Any]] | None:
        """Get progress."""
        return await self.context.broker.result_backend.get_progress(
            self.context.message.task_id,
        )

    @overload
    async def create_tracker(self, *, report_every_x_updates: int = 5) -> TaskiqProgressTracker[ProgressState]:
        pass

    @overload
    async def create_tracker(
        self, progress_state: TProgressState, report_every_x_updates: int = 5
    ) -> TaskiqProgressTracker[TProgressState]:
        pass

    async def create_tracker(
        self, progress_state: TProgressState | None = None, report_every_x_updates: int = 5
    ) -> TaskiqProgressTracker[TProgressState]:
        """Create a new progress tracker."""
        actual_progress_state: TProgressState | ProgressState
        if progress_state is None:
            actual_progress_state = ProgressState()
        else:
            actual_progress_state = progress_state
        tracker = TaskiqProgressTracker(self, actual_progress_state, report_every_x_updates)
        await tracker.init()
        return cast(TaskiqProgressTracker[TProgressState], tracker)
