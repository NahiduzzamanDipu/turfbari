"""Consistent JSON error envelope: {"error": {"code", "message", "fields"}}."""

from rest_framework import exceptions
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None  # unhandled -> Django 500 (logged, no stack trace to client when DEBUG=False)

    code = getattr(exc, "default_code", "error")
    fields = None
    if isinstance(exc, exceptions.ValidationError):
        code = "validation_error"
        message = "Please correct the highlighted fields."
        fields = response.data if isinstance(response.data, dict) else {"non_field_errors": response.data}
    else:
        detail = response.data.get("detail") if isinstance(response.data, dict) else response.data
        message = str(detail) if detail else "Request failed."
        code = getattr(getattr(exc, "detail", None), "code", code) or code

    response.data = {"error": {"code": code, "message": message, "fields": fields}}
    return response
