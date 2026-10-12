"""Public site of an organization. Phase 1 serves a branded holding page; the page builder, catalogue and
online booking arrive in phase 5."""

from django.http import HttpResponse
from django.shortcuts import render


def home(request):
    org = request.organization
    return render(request, "website/home.html", {"org": org, "page_title": org.name})


def robots(request):
    return HttpResponse("User-agent: *\nAllow: /\n", content_type="text/plain")
