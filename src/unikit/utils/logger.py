#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
from contextlib import contextmanager
import logging
from typing import Any, ContextManager, Generator


class StaticFieldFilter(logging.Filter):
    """Filter to add static fields to log records."""

    def __init__(self, fields: dict, prefix: str = ""):
        super().__init__()
        self.static_fields: dict = fields
        self._prefix = prefix

    def filter(self, record: logging.LogRecord) -> bool:
        """Add static fields to log record."""
        for k, v in self.static_fields.items():
            setattr(record, self._prefix + k, v)
        return True


class LogMixin:
    """Convenience super-class to have a logger configured with the class name."""

    _log: logging.Logger | None = None

    @property
    def log(self) -> logging.Logger:
        """Return a logger."""
        if self._log is None:
            self._log = logging.getLogger(self.__class__.__module__ + "." + self.__class__.__name__)
        return self._log

    def with_logging_context(self, **extras: Any) -> ContextManager[None]:
        """
        Context manager that adds extra fields to log records.

        :param extras: any extra fields to be added to log every record
        """
        return with_logging_context(self.log, **extras)


@contextmanager
def with_logging_context(logger: logging.Logger, prefix: str = "", **extras: Any) -> Generator[Any, None, None]:
    """
    Context manager that adds extra fields to log records.

    :param logger: logger instance to be modified
    :param prefix: prefix to be added to every key in extras
    :param extras: any extra fields to be added to log every record
    """
    logger_filter = StaticFieldFilter(extras, prefix)
    try:
        logger.addFilter(logger_filter)
        yield
    finally:
        logger.removeFilter(logger_filter)
