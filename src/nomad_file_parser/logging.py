"""Logging helpers shared by file and mapping parsers."""

import logging
from typing import Any, Protocol


class StructuredLogger(Protocol):
    """Logging interface shared by structlog and the stdlib adapter."""

    def debug(self, event: object, /, *args: Any, **kwargs: Any) -> Any: ...

    def info(self, event: object, /, *args: Any, **kwargs: Any) -> Any: ...

    def warning(self, event: object, /, *args: Any, **kwargs: Any) -> Any: ...

    def error(self, event: object, /, *args: Any, **kwargs: Any) -> Any: ...

    def exception(self, event: object, /, *args: Any, **kwargs: Any) -> Any: ...


class StructuredLoggerAdapter(logging.LoggerAdapter):
    """Adapt stdlib loggers to accept structlog-style keyword fields."""

    _stdlib_kwargs = {'exc_info', 'extra', 'stack_info', 'stacklevel'}

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        extra = dict(self.extra)
        extra.update(kwargs.get('extra') or {})
        kwargs['extra'] = extra
        for key in list(kwargs):
            if key not in self._stdlib_kwargs:
                extra[key] = kwargs.pop(key)
        return msg, kwargs


LOGGER = StructuredLoggerAdapter(logging.getLogger(__name__), {})


def normalize_logger(logger: StructuredLogger | None) -> StructuredLogger:
    """Return a logger that accepts structured keyword fields.

    Existing structlog loggers and ``StructuredLoggerAdapter`` instances are kept as
    is. Plain stdlib loggers and adapters are wrapped while preserving bound context.
    """
    logger = LOGGER if logger is None else logger
    if isinstance(logger, StructuredLoggerAdapter):
        return logger
    if isinstance(logger, logging.LoggerAdapter):
        return StructuredLoggerAdapter(logger.logger, dict(logger.extra))
    if isinstance(logger, logging.Logger):
        return StructuredLoggerAdapter(logger, {})
    return logger
