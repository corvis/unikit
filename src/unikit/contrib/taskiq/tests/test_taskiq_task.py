#
#  Copyright 2026 by Dmitry Berezovsky, MIT License
#
"""Unit tests for the BaseTaskiqTask class-based task abstraction."""

import asyncio
import inspect
from typing import Any
import unittest
from unittest.mock import MagicMock, patch

from taskiq import Context

from ..task import _CONTEXT_KWARG, BaseTaskiqTask

# ---------------------------------------------------------------------------
# Minimal concrete implementations used across multiple test cases
# ---------------------------------------------------------------------------


class _SyncTask(BaseTaskiqTask):
    """Sync task with no constructor dependencies."""

    def run(self, value: int, *, label: str = "default") -> str:  # type: ignore[override]
        return f"{label}:{value}"


class _AsyncTask(BaseTaskiqTask):
    """Async task with no constructor dependencies."""

    async def run(self, value: int) -> int:  # type: ignore[override]
        return value * 2


class _ServiceStub:
    """Stub service injected via the DI container."""

    def compute(self, x: int) -> int:
        return x + 10


class _TaskWithDeps(BaseTaskiqTask):
    """Sync task that declares a constructor dependency."""

    def __init__(self, service: _ServiceStub) -> None:
        self._service = service

    def run(self, x: int) -> int:  # type: ignore[override]
        return self._service.compute(x)


class _AsyncTaskWithDeps(BaseTaskiqTask):
    """Async task that declares a constructor dependency."""

    def __init__(self, service: _ServiceStub) -> None:
        self._service = service

    async def run(self, x: int) -> int:  # type: ignore[override]
        return self._service.compute(x)


class _ContextCapturingTask(BaseTaskiqTask):
    """Sync task that records the context it received for assertion in tests."""

    captured_context: Context | None = None

    def run(self, value: int) -> int:  # type: ignore[override]
        _ContextCapturingTask.captured_context = self.context
        return value


class _AsyncContextCapturingTask(BaseTaskiqTask):
    """Async task that records the context it received for assertion in tests."""

    captured_context: Context | None = None

    async def run(self, value: int) -> int:  # type: ignore[override]
        _AsyncContextCapturingTask.captured_context = self.context
        return value


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestBaseTaskiqTaskSignatureExposure(unittest.TestCase):
    """BaseTaskiqTask must expose the run() signature as the class-level __call__."""

    def test_inspect_signature_reflects_run(self) -> None:
        """inspect.signature on the class must match the run() parameters."""
        sig = inspect.signature(_SyncTask)
        params = list(sig.parameters.keys())
        self.assertIn("value", params)
        self.assertIn("label", params)
        self.assertNotIn("self", params)

    def test_inspect_signature_reflects_async_run(self) -> None:
        """inspect.signature on an async task class must match run() parameters."""
        sig = inspect.signature(_AsyncTask)
        self.assertIn("value", sig.parameters)

    def test_signature_contains_hidden_context_param(self) -> None:
        """The wrapped __init__ signature must include the hidden context injection param."""
        sig = inspect.signature(_SyncTask.__init__)
        self.assertIn(_CONTEXT_KWARG, sig.parameters)
        param = sig.parameters[_CONTEXT_KWARG]
        self.assertEqual(param.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_init_annotations_contain_context_param(self) -> None:
        """__init__.__annotations__ must expose Annotated[Context, TaskiqDepends()] for DependencyGraph."""
        from typing import get_type_hints

        hints = get_type_hints(_SyncTask.__init__, include_extras=True)
        self.assertIn(_CONTEXT_KWARG, hints)

    def test_class_signature_does_not_contain_context_param(self) -> None:
        """The class-level __signature__ (run params) must NOT expose the context param."""
        sig = inspect.signature(_SyncTask)
        self.assertNotIn(_CONTEXT_KWARG, sig.parameters)

    def test_type_hints_reflect_run(self) -> None:
        """get_type_hints on the class must return run()'s annotations."""
        from typing import get_type_hints

        hints = get_type_hints(_SyncTask)
        self.assertEqual(hints.get("value"), int)
        self.assertEqual(hints.get("label"), str)
        self.assertEqual(hints.get("return"), str)


class TestBaseTaskiqTaskExecution(unittest.TestCase):
    """BaseTaskiqTask.__call__ must resolve instances via root_container and call run()."""

    def _make_mock_container(self, task_cls: type, instance: Any) -> MagicMock:
        mock_container = MagicMock()
        mock_container.create_object.return_value = instance
        return mock_container

    def test_sync_task_called_directly(self) -> None:
        """Calling a concrete sync task class should resolve an instance and return run()'s result."""
        stub_instance = _SyncTask.__new__(_SyncTask)
        mock_container = self._make_mock_container(_SyncTask, stub_instance)

        with patch("unikit.contrib.taskiq.task.root_container", mock_container):
            result = _SyncTask(3, label="x")  # type: ignore[call-arg]

        mock_container.create_object.assert_called_once_with(_SyncTask)
        self.assertEqual(result, "x:3")

    def test_async_task_called_directly(self) -> None:
        """Calling a concrete async task class should return a coroutine that yields run()'s result."""
        stub_instance = _AsyncTask.__new__(_AsyncTask)
        mock_container = self._make_mock_container(_AsyncTask, stub_instance)

        with patch("unikit.contrib.taskiq.task.root_container", mock_container):
            coro = _AsyncTask(7)  # type: ignore[call-arg]

        self.assertTrue(
            inspect.iscoroutine(coro),
            "Calling an async BaseTaskiqTask class must return a coroutine",
        )
        result = asyncio.get_event_loop().run_until_complete(coro)
        self.assertEqual(result, 14)

    def test_sync_task_with_di_deps(self) -> None:
        """Constructor dependencies are resolved by root_container.create_object."""
        service_stub = _ServiceStub()
        task_instance = _TaskWithDeps.__new__(_TaskWithDeps)
        task_instance._service = service_stub

        mock_container = self._make_mock_container(_TaskWithDeps, task_instance)

        with patch("unikit.contrib.taskiq.task.root_container", mock_container):
            result = _TaskWithDeps(5)  # type: ignore[call-arg]

        mock_container.create_object.assert_called_once_with(_TaskWithDeps)
        self.assertEqual(result, 15)

    def test_async_task_with_di_deps(self) -> None:
        """Async task with DI deps resolves instance and returns coroutine."""
        service_stub = _ServiceStub()
        task_instance = _AsyncTaskWithDeps.__new__(_AsyncTaskWithDeps)
        task_instance._service = service_stub

        mock_container = self._make_mock_container(_AsyncTaskWithDeps, task_instance)

        with patch("unikit.contrib.taskiq.task.root_container", mock_container):
            coro = _AsyncTaskWithDeps(5)  # type: ignore[call-arg]

        self.assertTrue(inspect.iscoroutine(coro))
        result = asyncio.get_event_loop().run_until_complete(coro)
        self.assertEqual(result, 15)

    def test_create_object_called_fresh_per_invocation(self) -> None:
        """A new instance is created via root_container for every task call."""
        instances = [_SyncTask.__new__(_SyncTask), _SyncTask.__new__(_SyncTask)]
        call_count = 0

        def side_effect(cls: type) -> Any:
            nonlocal call_count
            result = instances[call_count]
            call_count += 1
            return result

        mock_container = MagicMock()
        mock_container.create_object.side_effect = side_effect

        with patch("unikit.contrib.taskiq.task.root_container", mock_container):
            _SyncTask(1)  # type: ignore[call-arg]
            _SyncTask(2)  # type: ignore[call-arg]

        self.assertEqual(mock_container.create_object.call_count, 2)


class TestBaseTaskiqTaskAbstract(unittest.TestCase):
    """BaseTaskiqTask must enforce that run() is implemented."""

    def test_cannot_call_without_run(self) -> None:
        """Calling a subclass that doesn't implement run must raise TypeError."""

        class _NoRun(BaseTaskiqTask):
            pass

        with self.assertRaises(TypeError):
            _NoRun()  # type: ignore[abstract]

    def test_abstract_intermediate_class(self) -> None:
        """An intermediate abstract class raises TypeError when called directly."""
        import abc

        class _AbstractMiddle(BaseTaskiqTask, metaclass=abc.ABCMeta):
            @abc.abstractmethod
            def helper(self) -> None:
                pass

        with self.assertRaises(TypeError):
            _AbstractMiddle()  # type: ignore[abstract]


class TestBaseTaskiqTaskLogMixin(unittest.TestCase):
    """BaseTaskiqTask subclasses inherit LogMixin and can use self.log."""

    def test_log_property_returns_logger(self) -> None:
        """self.log must return a stdlib logger named after the concrete class."""
        import logging

        task = _SyncTask.__new__(_SyncTask)
        self.assertIsInstance(task.log, logging.Logger)
        self.assertIn("_SyncTask", task.log.name)


class TestBaseTaskiqTaskContext(unittest.TestCase):
    """The context property must reflect the injected taskiq Context."""

    def _make_mock_context(self) -> MagicMock:
        """Return a minimal mock that looks like a taskiq Context."""
        ctx = MagicMock(spec=Context)
        ctx.message = MagicMock()
        ctx.message.task_id = "test-task-id"
        return ctx

    def test_context_set_on_instance_before_run(self) -> None:
        """The Context stored via __init__ must be on the instance when run() executes."""
        mock_ctx = self._make_mock_context()
        stub_instance = _ContextCapturingTask.__new__(_ContextCapturingTask)
        stub_instance._context = mock_ctx  # simulate __init__ wrapper having stored it
        _ContextCapturingTask.captured_context = None

        mock_container = MagicMock()
        mock_container.create_object.return_value = stub_instance

        with patch("unikit.contrib.taskiq.task.root_container", mock_container):
            _ContextCapturingTask(42)  # type: ignore[call-arg]

        self.assertIs(_ContextCapturingTask.captured_context, mock_ctx)

    def test_async_context_set_on_instance_before_run(self) -> None:
        """Context is available via self.context inside an async run() method."""
        mock_ctx = self._make_mock_context()
        stub_instance = _AsyncContextCapturingTask.__new__(_AsyncContextCapturingTask)
        stub_instance._context = mock_ctx
        _AsyncContextCapturingTask.captured_context = None

        mock_container = MagicMock()
        mock_container.create_object.return_value = stub_instance

        with patch("unikit.contrib.taskiq.task.root_container", mock_container):
            coro = _AsyncContextCapturingTask(7)  # type: ignore[call-arg]

        asyncio.get_event_loop().run_until_complete(coro)
        self.assertIs(_AsyncContextCapturingTask.captured_context, mock_ctx)

    def test_context_not_forwarded_to_run_kwargs(self) -> None:
        """The hidden __taskiq_context__ must be consumed by __init__ and never reach run()."""
        from typing import get_type_hints

        # Verify the param is in __init__ but not in run's signature.
        init_hints = get_type_hints(_SyncTask.__init__, include_extras=True)
        run_hints = get_type_hints(_SyncTask.run, include_extras=True)
        self.assertIn(_CONTEXT_KWARG, init_hints)
        self.assertNotIn(_CONTEXT_KWARG, run_hints)

    def test_init_wrapper_stores_context_on_instance(self) -> None:
        """Calling the wrapped __init__ directly must store the context on the instance."""
        mock_ctx = self._make_mock_context()
        task = _SyncTask.__new__(_SyncTask)
        _SyncTask.__init__(task, **{_CONTEXT_KWARG: mock_ctx})  # type: ignore[call-arg]
        self.assertIs(task._context, mock_ctx)  # type: ignore[attr-defined]

    def test_init_wrapper_stores_none_when_context_absent(self) -> None:
        """Calling the wrapped __init__ without the context kwarg stores None."""
        task = _SyncTask.__new__(_SyncTask)
        _SyncTask.__init__(task)  # type: ignore[call-arg]
        self.assertIsNone(task._context)  # type: ignore[attr-defined]

    def test_context_property_raises_outside_execution(self) -> None:
        """Accessing self.context on a bare instance (no execution) must raise RuntimeError."""
        task = _SyncTask.__new__(_SyncTask)
        task._context = None  # type: ignore[attr-defined]
        with self.assertRaises(RuntimeError):
            _ = task.context

    def test_context_property_none_when_not_injected(self) -> None:
        """If __taskiq_context__ is absent from kwargs, context raises RuntimeError (not AttributeError)."""
        stub_instance = _SyncTask.__new__(_SyncTask)
        stub_instance._context = None  # type: ignore[attr-defined]

        mock_container = MagicMock()
        mock_container.create_object.return_value = stub_instance

        with patch("unikit.contrib.taskiq.task.root_container", mock_container):
            _SyncTask(1, label="x")  # type: ignore[call-arg]

        with self.assertRaises(RuntimeError):
            _ = stub_instance.context

    def test_progress_reporter_created_from_context(self) -> None:
        """progress_reporter must return a TaskProgressReporter wrapping the current context."""
        from unikit.contrib.taskiq.progress import TaskProgressReporter

        mock_ctx = self._make_mock_context()
        task = _SyncTask.__new__(_SyncTask)
        task._context = mock_ctx  # type: ignore[attr-defined]

        reporter = task.progress_reporter
        self.assertIsInstance(reporter, TaskProgressReporter)
        self.assertIs(reporter.context, mock_ctx)

    def test_progress_reporter_is_cached(self) -> None:
        """progress_reporter must return the same instance on repeated access."""
        mock_ctx = self._make_mock_context()
        task = _SyncTask.__new__(_SyncTask)
        task._context = mock_ctx  # type: ignore[attr-defined]

        self.assertIs(task.progress_reporter, task.progress_reporter)

    def test_progress_reporter_raises_without_context(self) -> None:
        """progress_reporter must raise RuntimeError when context is not set."""
        task = _SyncTask.__new__(_SyncTask)
        task._context = None  # type: ignore[attr-defined]

        with self.assertRaises(RuntimeError):
            _ = task.progress_reporter
