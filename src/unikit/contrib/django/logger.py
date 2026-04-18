#
#  Copyright 2026 by Dmitry Berezovsky, MIT License
#
from collections.abc import Callable
import logging
from os import environ
from uuid import uuid4

from django.http import HttpRequest, HttpResponse

from unikit.contrib.django.middleware import (
    AsyncOrSyncCallback,
    BaseUniversalMiddleware,
)
from unikit.di import root_container
from unikit.utils.stats_utils import PerfExecutionTimer
from unikit.utils.type_utils import none_raises


class TraceIdFromRequestLoggingFilter(logging.Filter):
    """Logging filter which adds Global Trace ID to every log record."""

    def __init__(
        self,
        trace_id_header_name: str,
        log_field_name: str = "trace_id",
        is_enabled: bool = True,
        generate_trace_id_if_missing: bool = True,
    ) -> None:
        super().__init__()
        self.trace_id_header_name = trace_id_header_name
        self.is_enabled = is_enabled
        self.log_field_name = log_field_name
        self.generate_trace_id_if_missing = generate_trace_id_if_missing
        self._trace_id_rq_attr = "_rq_trace_id"

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log record."""
        if not self.is_enabled:
            return True
        try:
            request = root_container.get(HttpRequest)
            if request:
                trace_id = getattr(request, self._trace_id_rq_attr, None)
                if not trace_id:
                    trace_id = request.headers.get(self.trace_id_header_name, None)
                    if trace_id:
                        setattr(request, self._trace_id_rq_attr, trace_id)
                if not trace_id and self.generate_trace_id_if_missing:
                    trace_id = str(uuid4()) + "-" + str(uuid4())
                    setattr(request, self._trace_id_rq_attr, trace_id)
                if trace_id:
                    setattr(record, self.log_field_name, trace_id)
        except Exception:  # noqa: S110
            pass  # This filter should never raise an exception
        return True


class RequestLoggingMiddleware(BaseUniversalMiddleware):
    """Middleware to log request information."""

    async_capable = True
    sync_capable = True

    def __init__(self, get_response: AsyncOrSyncCallback) -> None:
        super().__init__(get_response)
        logger_prefix = environ.get("HTTP_REQUEST_LOGGER", "http")
        self._logger_request = logging.getLogger(logger_prefix + ".request")
        self._logger_response = logging.getLogger(logger_prefix + ".response")
        self._logger = logging.getLogger(logger_prefix)
        self._get_ip_function: Callable[[HttpRequest], str | None]
        try:
            from ipware import get_client_ip

            self._get_ip_function = lambda x: get_client_ip(x)[0]
        except ImportError:
            self._get_ip_function = RequestLoggingMiddleware._simple_resolve_ip

    def _call_sync(self, request: HttpRequest) -> HttpResponse:
        """Process a request synchronously."""
        log_data = self._capture_request_info_and_log(request)
        timer = PerfExecutionTimer(start=True)
        response = self.get_response(request)
        timer.stop()
        log_data.update(self._capture_response_info_and_log(request, response, none_raises(timer.elapsed_sec)))
        self._logger.info(
            "%s %s - %i, %.3f sec",
            request.method,
            request.path,
            response.status_code,  # type: ignore[union-attr]
            timer.elapsed_sec,
            extra=log_data,
        )
        return response

    async def _call_async(self, request: HttpRequest) -> HttpResponse:
        """Process a request asynchronously."""
        log_data = self._capture_request_info_and_log(request)
        timer = PerfExecutionTimer(start=True)
        response = await self.get_response(request)
        timer.stop()
        log_data.update(self._capture_response_info_and_log(request, response, none_raises(timer.elapsed_sec)))
        self._logger.info(
            "%s %s - %i, %.3f sec",
            request.method,
            request.path,
            response.status_code,
            timer.elapsed_sec,
            extra=log_data,
        )
        return response

    def _capture_request_info(self, request: HttpRequest) -> dict[str, str | None]:
        """Capture request information for logging."""
        return {
            "rq_method": request.method,
            "rq_path": request.path,
            "rq_client_ip": self._get_ip_function(request),
            "rq_ua": request.META.get("HTTP_USER_AGENT", None),
            "rq_query_string": request.META.get("QUERY_STRING", ""),
        }

    def _capture_request_info_and_log(self, request: HttpRequest) -> dict[str, str | None]:
        data = self._capture_request_info(request)
        self._logger_request.debug("Received %s %s", request.method, request.path, extra=data)
        return data

    def _capture_response_info(
        self, request: HttpRequest, response: HttpResponse, exec_time: float
    ) -> dict[str, str | None]:
        """Capture response information for logging."""
        view_name = (
            request.resolver_match.view_name if request.resolver_match and request.resolver_match.view_name else None
        )
        view_class_name: str | None = None
        if request.resolver_match and hasattr(request.resolver_match, "_func_path"):
            view_class_name = request.resolver_match._func_path
        return {
            "rs_status": str(response.status_code),
            "rs_time": str(exec_time),
            "rq_view_name": view_name,
            "rq_view_cls": view_class_name,
        }

    def _capture_response_info_and_log(
        self, request: HttpRequest, response: HttpResponse, exec_time: float
    ) -> dict[str, str | None]:
        data = self._capture_response_info(request, response, exec_time)
        self._logger_response.debug(
            "Response status %s in %.3f seconds",
            response.status_code,
            exec_time,
            extra=data,
        )
        return data

    @staticmethod
    def _simple_resolve_ip(request: HttpRequest) -> str | None:
        """Resolve IP address from request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip
