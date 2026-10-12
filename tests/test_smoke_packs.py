"""Seeded end-to-end smoke test per pack: seed_demo, then every page the organization can open answers."""

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils.html import escape

from apps.core import modules
from apps.industries import registry
from apps.tenancy.models import Membership, Organization
from tests.factories import login


@pytest.mark.django_db
@pytest.mark.parametrize("pack", [p.key for p in registry.all_packs()])
def test_seeded_pack_works_end_to_end(client, pack):
    call_command("seed_demo", pack=pack, verbosity=0)
    org = Organization.objects.get(industry=pack)
    assert org.onboarding_completed_at and org.enabled_modules
    owner = Membership.objects.get(organization=org, role__key="owner").user
    login(client, owner)
    dashboard = client.get(f"/{org.slug}/")
    assert dashboard.status_code == 200 and escape(org.name).encode() in dashboard.content
    for module in modules.modules_for(owner, org):
        for item in module.nav:
            if item.url_name:
                url = f"/{org.slug}" + reverse(item.url_name, urlconf="config.urls_tenant")
                assert client.get(url).status_code == 200, url
    assert client.get(f"/s/{org.slug}/").status_code == 200
    # Re-running the seed changes nothing (idempotent).
    call_command("seed_demo", pack=pack, verbosity=0)
    assert Organization.objects.filter(industry=pack).count() == 1


@pytest.mark.django_db
def test_seed_reset_removes_demo_data():
    call_command("seed_demo", pack="tourism", verbosity=0)
    assert Organization.objects.filter(slug="savannah-trails").exists()
    call_command("seed_demo", pack="tourism", reset=True, verbosity=0)
    assert Organization.objects.filter(slug="savannah-trails").count() == 1
