from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler


class RouteAPIError(Exception):
    """Base class for the documented error codes in plan.md's Endpoints
    section. Raised anywhere in the view/service layer, turned into the
    {"error": {"code", "message"}} shape by custom_exception_handler."""

    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class InvalidInputError(RouteAPIError):
    code = "INVALID_INPUT"
    status_code = 400


class GeocodeFailedError(RouteAPIError):
    code = "GEOCODE_FAILED"
    status_code = 422


class RouteNotFoundAPIError(RouteAPIError):
    code = "ROUTE_NOT_FOUND"
    status_code = 422


class NoStationsInRangeAPIError(RouteAPIError):
    code = "NO_STATIONS_IN_RANGE"
    status_code = 422


def _flatten_validation_errors(detail) -> str:
    """DRF's exc.detail is a dict of field -> [ErrorDetail, ...] (or a bare
    list for non_field_errors). Turn that into one human-readable string
    instead of leaking the raw Python repr to API clients."""
    if isinstance(detail, dict):
        parts = []
        for field, errors in detail.items():
            text = " ".join(str(e) for e in errors)
            parts.append(text if field == "non_field_errors" else f"{field}: {text}")
        return " ".join(parts)
    if isinstance(detail, list):
        return " ".join(str(e) for e in detail)
    return str(detail)


def custom_exception_handler(exc, context):
    if isinstance(exc, RouteAPIError):
        return Response(
            {"error": {"code": exc.code, "message": exc.message}},
            status=exc.status_code,
        )

    if isinstance(exc, drf_exceptions.ValidationError):
        return Response(
            {"error": {"code": "INVALID_INPUT", "message": _flatten_validation_errors(exc.detail)}},
            status=400,
        )

    return drf_default_handler(exc, context)
