#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
from typing import Any, Coroutine, cast

from opentelemetry import context as context_api
from opentelemetry import trace
from opentelemetry.sdk.trace import Span, TracerProvider
from opentelemetry.trace.propagation import _SPAN_KEY
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from unikit.contrib.taskiq.dto import TASKIQ_LABEL_SECURITY_CONTEXT


class OpenTelemetryMiddleware(TaskiqMiddleware):
    """Middleware to inject OpenTelemetry date into Taskiq tasks."""

    INSTRUMENTATION_NAME = "unikit.taskiq"
    TASK_ARGS_LENGTH_LIMIT = 1000
    MSG_SPAN_ATTRIBUTE = "__span"
    MSG_CTX_TOKEN_ATTRIBUTE = "__otlp_ctx_token"

    def __init__(self, tracer_provider: TracerProvider | None = None) -> None:
        if not tracer_provider:
            tracer_provider = cast(TracerProvider, trace.get_tracer_provider())
        self.tracer_provider = tracer_provider
        self.tracer = tracer_provider.get_tracer(self.INSTRUMENTATION_NAME, "0.1.0")

    def __serialize_args_and_kwargs(self, message: TaskiqMessage) -> tuple[str, str]:
        task_args_str = str(message.args)
        if len(task_args_str) > self.TASK_ARGS_LENGTH_LIMIT:
            task_args_str = f"{task_args_str[:self.TASK_ARGS_LENGTH_LIMIT]}..."
        task_kwargs_str = str(message.kwargs)
        if len(task_kwargs_str) > self.TASK_ARGS_LENGTH_LIMIT:
            task_kwargs_str = f"{task_kwargs_str[:self.TASK_ARGS_LENGTH_LIMIT]}..."
        return task_args_str, task_kwargs_str

    def __serialize_labels(self, message: TaskiqMessage) -> str:
        labels_str = str(message.labels)
        if len(labels_str) > self.TASK_ARGS_LENGTH_LIMIT:
            labels_str = f"{labels_str[:self.TASK_ARGS_LENGTH_LIMIT]}..."
        return labels_str

    def __serialize_security_context(self, message: TaskiqMessage) -> str:
        return str(message.labels.get(TASKIQ_LABEL_SECURITY_CONTEXT, "")) or ""

    def pre_send(self, message: TaskiqMessage) -> TaskiqMessage:
        """Pre-send hook to attach task name to Taskiq message."""
        task_args_str, task_kwargs_str = self.__serialize_args_and_kwargs(message)
        span = self.tracer.start_span(
            f"Post Task: {message.task_name}",
            kind=trace.SpanKind.PRODUCER,
            attributes={
                "task.name": message.task_name,
                "task.id": message.task_id,
                "task.args": task_args_str,
                "task.kwargs": task_kwargs_str,
                "messaging.message.id": message.task_id,
            },
        )
        setattr(message, self.MSG_SPAN_ATTRIBUTE, span)
        ctx = span.get_span_context()
        service_name = self.tracer_provider.resource.attributes.get("service.name")
        message.labels["otlp.caller_trace_id"] = format(ctx.trace_id, "032x")
        message.labels["otlp.caller_span_id"] = format(ctx.span_id, "016x")
        message.labels["otlp.caller_service_name"] = service_name
        return message

    def post_send(self, message: TaskiqMessage) -> None:
        """Post-send hook."""
        span: Span | None = getattr(message, self.MSG_SPAN_ATTRIBUTE, None)
        if not span:
            return
        labels_str = self.__serialize_labels(message)
        span.set_attribute("task.labels", labels_str)
        span.set_attribute("unikit.security_context", self.__serialize_security_context(message))
        span.end()
        span.set_status(trace.Status(trace.StatusCode.OK))

    def pre_execute(
        self,
        message: "TaskiqMessage",
    ) -> TaskiqMessage | Coroutine[Any, Any, TaskiqMessage]:
        """Post execute hook."""
        producer_span_id = message.labels.get("otlp.caller_span_id")
        producer_trace_id = message.labels.get("otlp.caller_trace_id")
        producer_context: trace.SpanContext | None = None
        if producer_span_id and producer_trace_id:
            producer_context = trace.SpanContext(
                trace_id=int(producer_trace_id, 16),
                span_id=int(producer_span_id, 16),
                is_remote=True,
            )
        span = self.tracer.start_span(
            f"Handle: {message.task_name} / {message.task_id}",
            kind=trace.SpanKind.CONSUMER,
            links=(
                [
                    trace.Link(
                        producer_context,
                        {
                            "kind": "producer",
                            "caller.service.name": message.labels.get("otlp.caller_service_name", ""),
                            "messaging.message.id": message.task_id,
                        },
                    )
                ]
                if producer_context
                else None
            ),
            attributes={
                "messaging.message.id": message.task_id,
                "task.name": message.task_name,
                "task.id": message.task_id,
                "task.args": str(message.args),
                "task.kwargs": str(message.kwargs),
                "task.labels": str(message.labels),
                "caller.otlp.trace_id": message.labels.get("otlp.caller_trace_id", ""),
                "caller.otlp.span_id": message.labels.get("otlp.caller_span_id", ""),
                "caller.otlp.service.name": message.labels.get("otlp.caller_service_name", ""),
                "unikit.security_context": self.__serialize_security_context(message),
            },
        )

        trace.use_span(span, set_status_on_exception=True)
        context_token = context_api.attach(context_api.set_value(_SPAN_KEY, span))
        setattr(message, self.MSG_SPAN_ATTRIBUTE, span)
        setattr(message, self.MSG_CTX_TOKEN_ATTRIBUTE, context_token)
        return message

    def post_execute(
        self,
        message: "TaskiqMessage",
        result: "TaskiqResult[Any]",
    ) -> None:
        """Post-execute hook."""
        span: Span | None = getattr(message, self.MSG_SPAN_ATTRIBUTE, None)
        ctx_token = getattr(message, self.MSG_CTX_TOKEN_ATTRIBUTE, None)
        if ctx_token:
            context_api.detach(ctx_token)
        if span:
            span.set_status(trace.Status(trace.StatusCode.OK))
            span.end()

    def on_error(self, message: "TaskiqMessage", result: TaskiqResult[Any], exception: BaseException) -> None:
        """On error hook."""
        span: Span | None = getattr(message, self.MSG_SPAN_ATTRIBUTE, None)
        if span:
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(exception)))
            span.end()
        super().on_error(message, result, exception)
