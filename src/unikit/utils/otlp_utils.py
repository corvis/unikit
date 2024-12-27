#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import os

from opentelemetry import trace

__all__ = ["TraceMixin"]

DEFAULT_TRACER_NAME = os.environ.get("OTLP_CUSTOM_TRACER_NAME", "unikit")


class TraceMixin:
    """Mixin to provide OpenTelemetry tracing functionality."""

    def _get_current_span(self) -> trace.Span:
        """Get the current span."""
        return trace.get_current_span()

    def _get_tracer(self) -> trace.Tracer:
        """Get the tracer."""
        return trace.get_tracer(self._get_tracer_name())

    def _set_tracer_name(self, name: str) -> None:
        """Set the tracer name."""
        setattr(self, "_otlp_tracer_name", name)

    def _get_tracer_name(self) -> str:
        """Get the tracer name."""
        return getattr(self, "_otlp_tracer_name", DEFAULT_TRACER_NAME)
