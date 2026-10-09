"""Allowlisted structured logs that omit request bodies, query strings and exception text."""

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from functools import wraps


class SafeJSONFormatter(logging.Formatter):
    fields = (
        "event",
        "request_id",
        "route",
        "method",
        "status",
        "duration_ms",
        "job",
        "provider",
        "operation",
        "count",
        "error_type",
    )

    def format(self, record):
        payload = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }
        for field in self.fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("lotneeti.request")

    def __call__(self, request):
        request_id = str(uuid.uuid4())
        started = time.monotonic()
        try:
            response = self.get_response(request)
        except Exception as exc:
            self.logger.error(
                "request.failed",
                extra={
                    "event": "request.failed",
                    "request_id": request_id,
                    "route": self._route(request),
                    "method": request.method,
                    "status": 500,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "error_type": type(exc).__name__,
                },
            )
            raise
        response["X-Request-ID"] = request_id
        self.logger.log(
            logging.ERROR if response.status_code >= 500 else logging.INFO,
            "request.completed",
            extra={
                "event": "request.completed",
                "request_id": request_id,
                "route": self._route(request),
                "method": request.method,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return response

    @staticmethod
    def _route(request):
        match = getattr(request, "resolver_match", None)
        return match.route if match else "unmatched"


def log_provider_error(*, provider: str, operation: str, error: Exception) -> None:
    logging.getLogger("lotneeti.provider").error(
        "provider.failed",
        extra={
            "event": "provider.failed",
            "provider": provider,
            "operation": operation,
            "error_type": type(error).__name__,
        },
    )


def logged_provider_operation(provider: str, operation: str):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except Exception as exc:
                log_provider_error(provider=provider, operation=operation, error=exc)
                raise

        return wrapped

    return decorate
