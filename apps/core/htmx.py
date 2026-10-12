"""Small helpers for HTMX responses."""

import json

from django.http import HttpResponse
from django.shortcuts import redirect


def trigger(response: HttpResponse, message: str, level: str = "success", **events) -> HttpResponse:
    """Attach a toast (and optional extra client events) via the HX-Trigger header."""
    payload = {"toast": {"message": message, "level": level}, **events}
    response["HX-Trigger"] = json.dumps(payload)
    return response


def redirect_or_refresh(request, url: str) -> HttpResponse:
    """Full redirect for normal posts; HX-Redirect for HTMX posts (e.g. from a modal)."""
    if request.htmx:
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response
    return redirect(url)
