"""Sign-in, rate limiting, two-factor login, session limits and password reset."""

import time

import pytest
from django.core import mail

from apps.accounts import totp
from apps.accounts.two_factor import LAST_ACTIVITY
from tests.factories import add_member, login, make_user


def _sign_in(client, email, password="pass12345!", **extra):
    return client.post("/accounts/login/", {"email": email, "password": password, "remember_me": "on", **extra})


@pytest.mark.django_db
def test_login_page_has_password_eye_toggle(client):
    html = client.get("/accounts/login/").content.decode()
    assert "password-field__toggle" in html and "Show password" in html


@pytest.mark.django_db
def test_password_login_without_two_factor(client, org1, staff1):
    response = _sign_in(client, staff1.email)
    assert response.status_code == 302 and response["Location"] == "/orgs/"
    assert client.get("/orgs/")["Location"] == f"/{org1.slug}/"


@pytest.mark.django_db
def test_wrong_password_and_rate_limit(client, staff1, settings):
    settings.LOGIN_RATE_LIMIT = 3
    for _ in range(3):
        assert b"incorrect" in _sign_in(client, staff1.email, "wrong").content
    response = _sign_in(client, staff1.email)  # right password, but blocked
    assert b"Too many failed attempts" in response.content
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_owner_must_set_up_two_factor(client, org1, owner1, settings):
    settings.TWO_FACTOR_ENFORCED = True
    response = _sign_in(client, owner1.email)
    assert response["Location"] == "/accounts/two-factor/setup/"
    page = client.get("/accounts/two-factor/setup/")
    assert b"<svg" in page.content  # the QR code
    secret = client.session["2fa_setup_secret"]
    response = client.post("/accounts/two-factor/setup/", {"code": totp.code_at(secret, totp.current_step())})
    assert response.status_code == 200 and b"backup" in response.content.lower()
    owner1.refresh_from_db()
    assert owner1.totp_enabled and len(owner1.totp_backup_codes) == 10
    assert client.get(f"/{org1.slug}/").status_code == 200


@pytest.mark.django_db
def test_two_factor_code_and_backup_code(client, org1, owner1, settings):
    settings.TWO_FACTOR_ENFORCED = True
    secret = totp.generate_secret()
    codes = totp.new_backup_codes()
    owner1.totp_secret, owner1.totp_enabled = secret, True
    owner1.totp_backup_codes = [totp.hash_backup_code(c) for c in codes]
    owner1.save()
    assert _sign_in(client, owner1.email)["Location"] == "/accounts/two-factor/"
    assert b"not right" in client.post("/accounts/two-factor/", {"code": "000000"}).content
    response = client.post("/accounts/two-factor/", {"code": totp.code_at(secret, totp.current_step())})
    assert response.status_code == 302
    client.post("/accounts/logout/")
    _sign_in(client, owner1.email)
    assert client.post("/accounts/two-factor/", {"code": codes[0]}).status_code == 302
    owner1.refresh_from_db()
    assert len(owner1.totp_backup_codes) == 9  # used once


@pytest.mark.django_db
def test_totp_code_cannot_be_reused(owner1):
    secret = totp.generate_secret()
    step = totp.current_step()
    code = totp.code_at(secret, step)
    assert totp.verify(secret, code, last_step=step) is None
    assert totp.verify(secret, code) == step


@pytest.mark.django_db
def test_session_without_two_factor_is_sent_to_setup_when_role_requires_it(client, org1, settings):
    settings.TWO_FACTOR_ENFORCED = True
    user = add_member(org1, make_user(), role="staff")
    client.force_login(user)  # session never verified a code
    assert client.get(f"/{org1.slug}/").status_code == 200  # staff: optional
    from apps.tenancy.models import Membership
    from apps.tenancy.services import builtin_role

    Membership.objects.filter(user=user).update(role=builtin_role(org1, "finance"))
    response = client.get(f"/{org1.slug}/")
    assert response.status_code == 302 and response["Location"].startswith("/accounts/two-factor/setup/")


@pytest.mark.django_db
def test_money_roles_have_shorter_sessions(client, org1, owner1, staff1):
    assert owner1.session_max_seconds == 10 * 3600
    assert staff1.session_max_seconds is None


@pytest.mark.django_db
def test_idle_timeout_signs_out(client, org1, owner1):
    login(client, owner1)
    session = client.session
    session[LAST_ACTIVITY] = int(time.time()) - 61 * 60  # owner idle timeout is 60 minutes
    session.save()
    response = client.get(f"/{org1.slug}/")
    assert response.status_code == 302 and response["Location"].startswith("/accounts/login/")
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_password_reset_email_uses_site_url_not_host_header(client, staff1, settings):
    response = client.post("/accounts/password/reset/", {"email": staff1.email})
    assert response.status_code == 302
    assert len(mail.outbox) == 1
    assert f"{settings.SITE_URL}/accounts/password/reset/" in mail.outbox[0].body


@pytest.mark.django_db
def test_password_reset_for_unknown_email_reveals_nothing(client):
    response = client.post("/accounts/password/reset/", {"email": "nobody@test.co.ke"})
    assert response.status_code == 302 and len(mail.outbox) == 0


@pytest.mark.django_db
def test_login_is_audited(client, staff1):
    from apps.core.models import AuditLog

    _sign_in(client, staff1.email)
    client.post("/accounts/logout/")
    _sign_in(client, staff1.email, "wrong")
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"login", "login_failed"} <= actions
