"""Host and path routing: staff app under /<slug>/, public site under /s/<slug>/, subdomains, custom domains."""

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.tenancy import routing
from apps.tenancy.models import Domain
from tests.factories import login


@pytest.mark.django_db
def test_staff_app_is_under_the_org_slug_and_reverse_includes_it(client, org1, owner1):
    login(client, owner1)
    response = client.get(f"/{org1.slug}/settings/")
    assert response.status_code == 200
    # Links on the page carry the prefix without any slug argument in the templates.
    assert f'href="/{org1.slug}/settings/team/"'.encode() in response.content
    # Platform links stay global.
    assert b'action="/accounts/logout/"' in response.content


@pytest.mark.django_db
def test_slug_without_trailing_slash_redirects(client, org1, owner1):
    login(client, owner1)
    response = client.get(f"/{org1.slug}")
    assert response.status_code == 302 and response["Location"] == f"/{org1.slug}/"


@pytest.mark.django_db
def test_anonymous_staff_page_redirects_to_login(client, org1):
    response = client.get(f"/{org1.slug}/settings/")
    assert response.status_code == 302
    assert response["Location"].startswith("/accounts/login/?next=")


def test_reserved_slugs_route_to_the_platform():
    route = routing.resolve("testserver", "/accounts/login/")
    assert route.kind == routing.PLATFORM


@pytest.mark.django_db
def test_public_site_fallback_path(client, org1):
    response = client.get(f"/s/{org1.slug}/")
    assert response.status_code == 200
    assert org1.name.encode() in response.content
    assert client.get(f"/s/{org1.slug}").status_code == 302
    assert client.get("/s/no-such-org/").status_code == 404


@pytest.mark.django_db
def test_unknown_host_is_rejected(client, org1):
    assert client.get("/", HTTP_HOST="evil.example.com").status_code == 400


@pytest.mark.django_db
def test_wildcard_subdomains_only_when_enabled(client, org1, settings):
    host = f"{org1.slug}.{settings.PUBLIC_DOMAIN}"
    settings.WILDCARD_SUBDOMAINS = False
    assert client.get("/", HTTP_HOST=host).status_code == 400
    settings.WILDCARD_SUBDOMAINS = True
    response = client.get("/", HTTP_HOST=host)  # trial = Growth features, which include the subdomain
    assert response.status_code == 200 and org1.name.encode() in response.content


@pytest.mark.django_db
def test_custom_domain_needs_verification(client, org1):
    domain = Domain.objects.create(organization=org1, hostname="www.savannahtest.co.ke")
    assert client.get("/", HTTP_HOST="www.savannahtest.co.ke").status_code == 400
    domain.verified_at = timezone.now()
    domain.save()
    response = client.get("/", HTTP_HOST="www.savannahtest.co.ke")
    assert response.status_code == 200 and org1.name.encode() in response.content
    # The public URL now prefers the verified domain.
    assert org1.public_url.startswith("http://www.savannahtest.co.ke/")


@pytest.mark.django_db
def test_public_url_falls_back_to_path(org1, settings):
    settings.WILDCARD_SUBDOMAINS = False
    assert org1.public_url == f"{settings.SITE_URL}/s/{org1.slug}/"


@pytest.mark.django_db
def test_subdomain_staff_routing(client, org1, owner1, settings):
    settings.TENANT_ROUTING = "subdomain"
    login(client, owner1)
    host = f"{org1.slug}.{settings.APP_HOST}"
    response = client.get("/settings/", HTTP_HOST=host)
    assert response.status_code == 200
    assert b'href="/settings/team/"' in response.content


@pytest.mark.django_db
def test_reverse_global_ignores_tenant_prefix(org1):
    from django.urls import set_script_prefix

    set_script_prefix(f"/{org1.slug}/")
    try:
        assert routing.reverse_global("accounts:login") == "/accounts/login/"
    finally:
        set_script_prefix("/")
    assert reverse("accounts:login") == "/accounts/login/"


@pytest.mark.django_db
def test_org_timezone_is_active_inside_requests(client, org1, owner1):
    from unittest import mock

    from django.http import HttpResponse
    from django.utils import timezone as tz

    org1.timezone = "Africa/Kampala"
    org1.save()
    login(client, owner1)
    seen = {}

    def fake_render(*args, **kwargs):
        seen["tz"] = tz.get_current_timezone_name()
        return HttpResponse("ok")

    with mock.patch("apps.core.views.render", fake_render):
        client.get(f"/{org1.slug}/")
    assert seen["tz"] == "Africa/Kampala"
