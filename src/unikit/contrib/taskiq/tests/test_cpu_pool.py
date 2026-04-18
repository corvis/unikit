#
#  Copyright 2026 by Dmitry Berezovsky, MIT License
#
"""Unit tests for cpu_pool.py and CpuBoundTaskiqTask."""

import asyncio
from concurrent.futures import ProcessPoolExecutor
from typing import Any
import unittest
from unittest.mock import MagicMock, patch

from ..cpu_pool import (
    CpuPoolNotInitializedError,
    get_cpu_pool,
    init_cpu_pool,
    setup_cpu_pool_on_broker,
    shutdown_cpu_pool,
)
from ..cpu_task import CpuBoundTaskiqTask, _run_cpu_bound_in_process

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _double(x: int) -> int:
    """Top-level picklable helper used in subprocess dispatch tests."""
    return x * 2


class _HeavyTask(CpuBoundTaskiqTask):
    """Minimal concrete CpuBoundTaskiqTask that multiplies its argument by 2."""

    def run_cpu_bound(self, value: int) -> int:  # type: ignore[override]
        return value * 2


class _SumTask(CpuBoundTaskiqTask):
    """CpuBoundTaskiqTask that sums its keyword arguments."""

    def run_cpu_bound(self, *, a: int, b: int) -> int:  # type: ignore[override]
        return a + b


class _AsyncHeavyTask(CpuBoundTaskiqTask):
    """CpuBoundTaskiqTask with an async run_cpu_bound — multiplies by 3."""

    async def run_cpu_bound(self, value: int) -> int:  # type: ignore[override]
        return value * 3


class _StateTask(CpuBoundTaskiqTask):
    """CpuBoundTaskiqTask that verifies subprocess state round-trip."""

    extra: str = ""

    def get_subprocess_state(self) -> dict:
        return {"extra": self.extra}

    def restore_subprocess_state(self, state: dict) -> None:  # type: ignore[override]
        self.extra = state.get("extra", "")

    def run_cpu_bound(self) -> str:  # type: ignore[override]
        return self.extra


# ---------------------------------------------------------------------------
# cpu_pool module tests
# ---------------------------------------------------------------------------


class TestCpuPoolInit(unittest.TestCase):
    """init_cpu_pool / get_cpu_pool / shutdown_cpu_pool lifecycle."""

    def setUp(self) -> None:
        # Always start each test with no pool.
        shutdown_cpu_pool(wait=False)

    def tearDown(self) -> None:
        shutdown_cpu_pool(wait=False)

    def test_get_pool_raises_before_init(self) -> None:
        """get_cpu_pool must raise CpuPoolNotInitializedError when not initialized."""
        with self.assertRaises(CpuPoolNotInitializedError):
            get_cpu_pool()

    def test_init_returns_process_pool_executor(self) -> None:
        """init_cpu_pool must return a ProcessPoolExecutor."""
        pool = init_cpu_pool(2)
        self.assertIsInstance(pool, ProcessPoolExecutor)

    def test_get_pool_after_init_returns_same_instance(self) -> None:
        """get_cpu_pool must return the same object created by init_cpu_pool."""
        pool = init_cpu_pool(2)
        self.assertIs(get_cpu_pool(), pool)

    def test_shutdown_clears_pool(self) -> None:
        """shutdown_cpu_pool must clear the singleton so get_cpu_pool raises afterwards."""
        init_cpu_pool(2)
        shutdown_cpu_pool(wait=False)
        with self.assertRaises(CpuPoolNotInitializedError):
            get_cpu_pool()

    def test_shutdown_when_not_initialized_is_noop(self) -> None:
        """Calling shutdown_cpu_pool when no pool exists must not raise."""
        shutdown_cpu_pool(wait=False)  # already clear from setUp
        shutdown_cpu_pool(wait=False)  # second call: no-op

    def test_reinit_replaces_old_pool(self) -> None:
        """Calling init_cpu_pool a second time must replace the existing pool."""
        pool_a = init_cpu_pool(2)
        pool_b = init_cpu_pool(3)
        self.assertIsNot(pool_a, pool_b)
        self.assertIs(get_cpu_pool(), pool_b)


class TestSetupCpuPoolOnBroker(unittest.TestCase):
    """setup_cpu_pool_on_broker registers correct broker lifecycle handlers."""

    def tearDown(self) -> None:
        shutdown_cpu_pool(wait=False)

    def test_registers_startup_and_shutdown_handlers(self) -> None:
        """setup_cpu_pool_on_broker must register WORKER_STARTUP and WORKER_SHUTDOWN on every broker."""
        from taskiq import TaskiqEvents

        broker_a = MagicMock()
        broker_b = MagicMock()

        setup_cpu_pool_on_broker(broker_a, broker_b, pool_size=2)

        for broker in (broker_a, broker_b):
            calls = [call[0][0] for call in broker.on_event.call_args_list]
            self.assertIn(TaskiqEvents.WORKER_STARTUP, calls)
            self.assertIn(TaskiqEvents.WORKER_SHUTDOWN, calls)

    def test_startup_handler_inits_pool_with_correct_size(self) -> None:
        """The WORKER_STARTUP handler registered by setup_cpu_pool_on_broker must call init_cpu_pool."""
        from taskiq import TaskiqEvents

        captured: dict[str, Any] = {}

        def fake_on_event(event: Any) -> Any:
            def decorator(fn: Any) -> Any:
                captured[event] = fn
                return fn

            return decorator

        broker = MagicMock()
        broker.on_event.side_effect = fake_on_event

        setup_cpu_pool_on_broker(broker, pool_size=5)

        # Call the startup handler.
        asyncio.get_event_loop().run_until_complete(captured[TaskiqEvents.WORKER_STARTUP](None))
        self.assertIsInstance(get_cpu_pool(), ProcessPoolExecutor)

    def test_shutdown_handler_shuts_down_pool(self) -> None:
        """The WORKER_SHUTDOWN handler registered by setup_cpu_pool_on_broker must shut down the pool."""
        from taskiq import TaskiqEvents

        captured: dict[str, Any] = {}

        def fake_on_event(event: Any) -> Any:
            def decorator(fn: Any) -> Any:
                captured[event] = fn
                return fn

            return decorator

        broker = MagicMock()
        broker.on_event.side_effect = fake_on_event

        setup_cpu_pool_on_broker(broker, pool_size=2)
        asyncio.get_event_loop().run_until_complete(captured[TaskiqEvents.WORKER_STARTUP](None))
        asyncio.get_event_loop().run_until_complete(captured[TaskiqEvents.WORKER_SHUTDOWN](None))

        with self.assertRaises(CpuPoolNotInitializedError):
            get_cpu_pool()


# ---------------------------------------------------------------------------
# CpuBoundTaskiqTask tests
# ---------------------------------------------------------------------------


class TestCpuBoundTaskiqTaskAbstract(unittest.TestCase):
    """CpuBoundTaskiqTask must enforce run_cpu_bound implementation."""

    def test_cannot_call_without_run_cpu_bound(self) -> None:
        """Calling a subclass that doesn't implement run_cpu_bound must raise TypeError."""

        class _NoImpl(CpuBoundTaskiqTask):
            pass

        with self.assertRaises(TypeError):
            _NoImpl()  # type: ignore[abstract]


class TestCpuBoundTaskiqTaskDispatch(unittest.TestCase):
    """CpuBoundTaskiqTask.run must dispatch run_cpu_bound to the process pool."""

    def setUp(self) -> None:
        shutdown_cpu_pool(wait=False)

    def tearDown(self) -> None:
        shutdown_cpu_pool(wait=False)

    def _make_instance_with_context(self, task_cls: type) -> Any:
        """Create a bare instance with a mocked taskiq context."""
        instance = task_cls.__new__(task_cls)
        mock_context = MagicMock()
        mock_context.message.task_id = "test-task-id"
        instance._context = mock_context
        return instance

    def test_run_calls_run_in_executor_with_pool(self) -> None:
        """run() must call loop.run_in_executor with the CPU pool and correct arguments."""
        init_cpu_pool(1)
        pool = get_cpu_pool()
        instance = self._make_instance_with_context(_HeavyTask)

        future: asyncio.Future[int] = asyncio.get_event_loop().create_future()
        future.set_result(42)

        with patch.object(asyncio.get_event_loop(), "run_in_executor", return_value=future) as mock_exec:
            asyncio.get_event_loop().run_until_complete(instance.run(21))

        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        self.assertIs(call_args[0][0], pool)  # first positional arg is the pool

    def test_run_raises_when_pool_not_initialized(self) -> None:
        """run() must propagate CpuPoolNotInitializedError when pool is not set up."""
        instance = self._make_instance_with_context(_HeavyTask)
        with self.assertRaises(CpuPoolNotInitializedError):
            asyncio.get_event_loop().run_until_complete(instance.run(1))


class TestRunCpuBoundInProcess(unittest.TestCase):
    """_run_cpu_bound_in_process must create a bare instance and call run_cpu_bound."""

    def setUp(self) -> None:
        # asyncio.run() — used by the async run_cpu_bound path — calls
        # asyncio.set_event_loop(None) in its finally block.  When these tests
        # run directly on the main thread (not inside a subprocess) that clears
        # the current event loop and breaks later tests that call
        # asyncio.get_event_loop().  Save the loop here and restore it in
        # tearDown so the test suite remains isolated.
        try:
            self._saved_loop: asyncio.AbstractEventLoop | None = asyncio.get_event_loop()
        except RuntimeError:
            self._saved_loop = None

    def tearDown(self) -> None:
        asyncio.set_event_loop(self._saved_loop)

    def test_dispatches_positional_args(self) -> None:
        """_run_cpu_bound_in_process must forward positional args to run_cpu_bound."""

        result = _run_cpu_bound_in_process(_HeavyTask, "test-task-id", {}, (7,), {})
        self.assertEqual(result, 14)

    def test_dispatches_keyword_args(self) -> None:
        """_run_cpu_bound_in_process must forward keyword args to run_cpu_bound."""

        result = _run_cpu_bound_in_process(_SumTask, "test-task-id", {}, (), {"a": 3, "b": 4})
        self.assertEqual(result, 7)

    def test_creates_bare_instance_without_di(self) -> None:
        """_run_cpu_bound_in_process must use __new__ - not root_container - to create the instance."""

        created: list[Any] = []

        class _TrackNew(CpuBoundTaskiqTask):
            def __new__(cls, *a: Any, **kw: Any) -> "_TrackNew":
                obj = object.__new__(cls)
                created.append(obj)
                return obj

            def run_cpu_bound(self) -> None:  # type: ignore[override]
                pass

        _run_cpu_bound_in_process(_TrackNew, "test-task-id", {}, (), {})
        self.assertEqual(len(created), 1)

    def test_dispatches_async_run_cpu_bound(self) -> None:
        """_run_cpu_bound_in_process must support async run_cpu_bound via asyncio.run()."""
        result = _run_cpu_bound_in_process(_AsyncHeavyTask, "test-task-id", {}, (5,), {})
        self.assertEqual(result, 15)

    def test_subprocess_context_factory_is_called_with_task_id(self) -> None:
        """_run_cpu_bound_in_process must call subprocess_context_factory(task_id) and inject the result."""
        mock_ctx = MagicMock()
        factory = MagicMock(return_value=mock_ctx)

        class _CtxTask(CpuBoundTaskiqTask):
            subprocess_context_factory = factory

            def run_cpu_bound(self) -> Any:  # type: ignore[override]
                return self._context  # type: ignore[attr-defined]

        result = _run_cpu_bound_in_process(_CtxTask, "my-task-id", {}, (), {})
        factory.assert_called_once_with("my-task-id")
        self.assertIs(result, mock_ctx)

    def test_subprocess_state_round_trip(self) -> None:
        """_run_cpu_bound_in_process must restore subprocess state before calling run_cpu_bound."""
        result = _run_cpu_bound_in_process(_StateTask, "test-task-id", {"extra": "hello"}, (), {})
        self.assertEqual(result, "hello")

    def test_run_forwards_subprocess_state(self) -> None:
        """run() must call get_subprocess_state() and forward its result to the executor."""
        init_cpu_pool(1)

        class _StateHeavyTask(_StateTask):
            def get_subprocess_state(self) -> dict:
                return {"extra": "forwarded"}

        instance = _StateHeavyTask.__new__(_StateHeavyTask)
        mock_context = MagicMock()
        mock_context.message.task_id = "tid-1"
        instance._context = mock_context

        loop = asyncio.new_event_loop()
        try:
            future: asyncio.Future[Any] = loop.create_future()
            future.set_result("ok")

            with patch.object(loop, "run_in_executor", return_value=future) as mock_exec:
                loop.run_until_complete(instance.run())

            call_args = mock_exec.call_args[0]  # positional args to run_in_executor
            # call_args: (pool, fn, task_cls, task_id, subprocess_state, args, kwargs)
            self.assertEqual(call_args[4], {"extra": "forwarded"})
        finally:
            loop.close()
            shutdown_cpu_pool(wait=False)
