"""Sign-up, email verification and the resumable set-up wizard."""

import re
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.models import User
from apps.industries.models import AppliedPack, CustomField, Pipeline
from apps.industries.terms import term
from apps.onboarding.models import OnboardingSession
from apps.tenancy.context import tenant
from apps.tenancy.models import Invitation, Membership, Organization

SIGNUP = {"full_name": "Amina Hassan", "email": "amina@pwanitours.co.ke", "phone": "0722 123 456",
          "password": "Tsavo-Elephants-2026", "accept_terms": "on", "company_website": ""}


def _verify_link():
    body = mail.outbox[-1].body
    return re.search(r"http://testserver(/verify-email/[^/\s]+/)", body).group(1)


@pytest.mark.django_db
def test_signup_creates_user_and_sends_verification(client):
    response = client.post("/signup/", SIGNUP)
    assert response.status_code == 302 and response["Location"] == "/verify-email/"
    user = User.objects.get(email="amina@pwanitours.co.ke")
    assert user.phone == "+254722123456" and not user.email_verified
    assert "Confirm your email" in mail.outbox[0].subject
    # Not verified yet: the wizard sends them back.
    assert client.get("/onboarding/")["Location"] == "/verify-email/"


@pytest.mark.django_db
def test_signup_honeypot_and_duplicate(client):
    client.post("/signup/", {**SIGNUP, "company_website": "spam.example"})
    assert not User.objects.filter(email=SIGNUP["email"]).exists()
    User.objects.create_user(email=SIGNUP["email"], password="x", full_name="Exists")
    response = client.post("/signup/", SIGNUP)
    assert b"already exists" in response.content


@pytest.mark.django_db
def test_signup_rate_limit(client, settings):
    settings.SIGNUP_RATE_LIMIT = 2
    for i in range(3):
        client.post("/signup/", {**SIGNUP, "email": f"spam{i}@test.co.ke"})
        client.post("/accounts/logout/")
    assert User.objects.filter(email__startswith="spam").count() == 2


@pytest.mark.django_db
def test_bad_verification_link(client):
    assert client.get("/verify-email/not-a-token/").status_code == 400


def _walk_wizard(client, invites=None, sample="yes", modules=None):
    client.post("/signup/", SIGNUP)
    client.get(_verify_link())
    start = client.get("/onboarding/")
    url = start["Location"]
    assert url.endswith("/business/")
    base = url.rsplit("/", 2)[0]
    r = client.post(f"{base}/business/", {"name": "Pwani Tours & Safaris", "country": "KE", "currency": "KES",
                                          "timezone": "Africa/Nairobi", "brand_colour": "#0e7490"})
    assert r["Location"].endswith("/industry/"), r.content[:500]
    assert client.post(f"{base}/industry/", {"industry": "tourism"})["Location"].endswith("/niche/")
    assert client.post(f"{base}/niche/", {"sub_niche": "dmc"})["Location"].endswith("/team/")
    assert client.post(f"{base}/team/", {"team_size": "6-20"})["Location"].endswith("/modules/")
    page = client.get(f"{base}/modules/")
    assert b'value="tourism" checked' in page.content and b'value="partners" checked' in page.content
    mods = modules or ["crm", "sales", "tourism", "website", "partners", "finance"]
    assert client.post(f"{base}/modules/", {"modules": mods})["Location"].endswith("/sample/")
    assert client.post(f"{base}/sample/", {"sample": sample})["Location"].endswith("/invite/")
    data = {"inv-TOTAL_FORMS": "3", "inv-INITIAL_FORMS": "0", "inv-MIN_NUM_FORMS": "0", "inv-MAX_NUM_FORMS": "10"}
    org = Organization.objects.get(name="Pwani Tours & Safaris")
    with tenant(org):
        from apps.accounts.models import Role

        roles = {r.key: r.pk for r in Role.objects.filter(is_builtin=True)}
    for i, (email, role) in enumerate(invites or []):
        data[f"inv-{i}-email"], data[f"inv-{i}-role"] = email, roles[role]
    for i in range(len(invites or []), 3):
        data[f"inv-{i}-role"] = roles["staff"]
    return client.post(f"{base}/invite/", data), org, base


@pytest.mark.django_db
def test_full_onboarding_applies_the_pack(client):
    response, org, base = _walk_wizard(client, invites=[("ops@pwanitours.co.ke", "operations"),
                                                         ("cash@pwanitours.co.ke", "finance")])
    org.refresh_from_db()
    assert response.status_code == 302 and response["Location"] == f"/{org.slug}/"
    assert org.industry == "tourism" and org.sub_niche == "dmc" and org.team_size == "6-20"
    assert org.onboarding_completed_at and org.brand_colour == "#0E7490"
    assert set(org.enabled_modules) == {"crm", "sales", "tourism", "website", "partners", "finance"}
    assert org.status == "trial" and org.plan.key == "growth"
    assert timedelta(days=13) < org.trial_ends_at - timezone.now() <= timedelta(days=14)
    assert org.settings["sample_data_requested"] is True
    assert term("lead", org=org) == "Enquiry"
    with tenant(org):
        assert AppliedPack.objects.get().pack_key == "tourism"
        assert Pipeline.objects.filter(entity="deal").exists()
        assert CustomField.objects.filter(entity="lead", key="residency").exists()
        assert Invitation.objects.count() == 2
    assert Membership.objects.get(organization=org).role.key == "owner"
    assert len([m for m in mail.outbox if "invited you" in m.subject]) == 2
    dashboard = client.get(f"/{org.slug}/")
    assert dashboard.status_code == 200 and b"Getting started" in dashboard.content
    assert OnboardingSession.objects.get(organization=org).completed_at is not None


@pytest.mark.django_db
def test_wizard_is_resumable_and_cannot_skip_ahead(client):
    client.post("/signup/", SIGNUP)
    client.get(_verify_link())
    url = client.get("/onboarding/")["Location"]
    base = url.rsplit("/", 2)[0]
    client.post(f"{base}/business/", {"name": "Resume Co", "country": "KE", "currency": "KES",
                                      "timezone": "Africa/Nairobi", "brand_colour": "#134e4a"})
    # Jumping to a later step goes back to the current one.
    assert client.get(f"{base}/invite/")["Location"] == f"{base}/industry/"
    # A new sign-in resumes where they stopped.
    client.post("/accounts/logout/")
    client.post("/accounts/login/", {"email": SIGNUP["email"], "password": SIGNUP["password"]})
    assert client.get("/onboarding/")["Location"] == f"{base}/industry/"
    # The half-set-up organization sends its dashboard back to the wizard.
    org = Organization.objects.get(name="Resume Co")
    assert client.get(f"/{org.slug}/")["Location"].startswith("/onboarding/?org=")


@pytest.mark.django_db
def test_invites_respect_the_seat_limit(client):
    from apps.billing.models import Plan

    Plan.objects.filter(key="growth").update(max_users=2)
    response, org, base = _walk_wizard(client, invites=[("a@x.co.ke", "staff"), ("b@x.co.ke", "staff")])
    assert response.status_code == 200 and b"includes 2 users" in response.content
    org.refresh_from_db()
    assert org.onboarding_completed_at is None


@pytest.mark.django_db
def test_logo_upload_is_stored_under_the_org_folder(client):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from io import BytesIO

    from PIL import Image

    client.post("/signup/", SIGNUP)
    client.get(_verify_link())
    base = client.get("/onboarding/")["Location"].rsplit("/", 2)[0]
    buf = BytesIO()
    Image.new("RGB", (64, 64), "#0e7490").save(buf, "PNG")
    logo = SimpleUploadedFile("logo.png", buf.getvalue(), content_type="image/png")
    client.post(f"{base}/business/", {"name": "Logo Co", "country": "KE", "currency": "KES",
                                      "timezone": "Africa/Nairobi", "brand_colour": "#134e4a", "logo": logo})
    org = Organization.objects.get(name="Logo Co")
    assert org.logo.name.startswith(f"{org.pk}/branding/")
    assert client.get(f"/media-public/logo/{org.slug}/").status_code == 200


@pytest.mark.django_db
def test_accepting_an_invitation_as_a_new_person(client, org1, owner1):
    from apps.tenancy.services import builtin_role, invite

    inv = invite(org1, "newbie@test.co.ke", builtin_role(org1, "sales"), owner1)
    link = f"/invite/{inv.token}/"
    assert client.get(link).status_code == 200
    response = client.post(link, {"full_name": "New Person", "phone": "0711000111", "password": "Mara-Migration-77"})
    assert response.status_code == 302 and response["Location"] == f"/{org1.slug}/"
    m = Membership.objects.get(organization=org1, user__email="newbie@test.co.ke")
    assert m.role.key == "sales" and m.user.email_verified
    assert client.get(link).status_code == 404  # used


@pytest.mark.django_db
def test_invitation_for_someone_else(client, org1, owner1, staff1):
    from apps.tenancy.services import builtin_role, invite
    from tests.factories import login

    inv = invite(org1, "someone@test.co.ke", builtin_role(org1, "sales"), owner1)
    login(client, staff1)
    assert client.get(f"/invite/{inv.token}/").status_code == 403


@pytest.mark.django_db
def test_cancelling_an_unfinished_setup_deletes_the_empty_organization(client):
    client.post("/signup/", SIGNUP)
    client.get(_verify_link())
    base = client.get("/onboarding/")["Location"].rsplit("/", 2)[0]
    client.post(f"{base}/business/", {"name": "Abandoned Co", "country": "KE", "currency": "KES",
                                      "timezone": "Africa/Nairobi", "brand_colour": "#134e4a"})
    assert Organization.objects.filter(name="Abandoned Co").exists()
    response = client.post(f"{base}/cancel/")
    assert response.status_code == 302
    assert not Organization.objects.filter(name="Abandoned Co").exists()
    from apps.accounts.models import Role

    assert not Role.unscoped.filter(organization__name="Abandoned Co").exists()
