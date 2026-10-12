"""Sign-up, email (and phone) verification and the resumable set-up wizard.

Wizard steps: business → industry → sub-niche → team size → modules → sample data → invite teammates.
The organization is created on the first step (so the logo is stored under its folder) and finished on the
last, when the industry pack is applied and the 14-day trial is already running.
"""

from contextlib import nullcontext

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts import ratelimit
from apps.accounts.models import Role, User
from apps.accounts.two_factor import VERIFIED
from apps.core.audit import audit
from apps.core.modules import CATALOGUE
from apps.industries import registry, sample
from apps.industries.services import apply_pack
from apps.tenancy import services as tenancy
from apps.tenancy.context import tenant
from apps.tenancy.models import Membership

from . import services
from .forms import (BusinessForm, IndustryForm, InviteFormSet, ModulesForm, NicheForm, PhoneCodeForm, SampleForm,
                    SignupForm, TeamForm)
from .models import OnboardingSession

STEP_TITLES = {
    "business": "Your business", "industry": "Your industry", "niche": "What you do", "team": "Your team",
    "modules": "Modules", "sample": "Sample data", "invite": "Invite your team",
}


# --- Sign-up and verification ---------------------------------------------------------------------------

@never_cache
def signup(request):
    if request.user.is_authenticated:
        return redirect("onboarding:start")
    form = SignupForm(request.POST or None)
    if request.method == "POST":
        if ratelimit.too_many(request, "signup", limit=_signup_limit()):
            form.add_error(None, "Too many sign-ups from this connection. Please try again in an hour.")
        elif form.is_valid():
            data = form.cleaned_data
            user = User.objects.create_user(email=data["email"], password=data["password"], full_name=data["full_name"],
                                            phone=data["phone"])
            login(request, user, backend="apps.accounts.backends.EmailBackend")
            request.session[VERIFIED] = False
            services.send_verification_email(user)
            audit("signup", request, user=user, organization=None)
            return redirect("onboarding:verify_pending")
    return render(request, "onboarding/signup.html", {"form": form, "page_title": "Create your account"})


def _signup_limit():
    from django.conf import settings

    return settings.SIGNUP_RATE_LIMIT


@login_required
@never_cache
def verify_pending(request):
    if request.user.email_verified:
        return redirect("onboarding:start")
    if request.method == "POST":
        if ratelimit.too_many(request, f"verify-resend:{request.user.pk}", limit=3, window=900):
            messages.error(request, "Please wait a few minutes before asking for another email.")
        else:
            services.send_verification_email(request.user)
            messages.success(request, f"We sent a new link to {request.user.email}.")
        return redirect("onboarding:verify_pending")
    return render(request, "onboarding/verify_pending.html", {"page_title": "Confirm your email"})


@never_cache
def verify_email(request, token):
    user = services.check_email_token(token)
    if user is None:
        return render(request, "onboarding/verify_invalid.html", {"page_title": "Link expired"}, status=400)
    services.mark_email_verified(user)
    if request.user.is_authenticated and request.user.pk == user.pk:
        messages.success(request, "Thanks, your email is confirmed.")
        if services.phone_verification_available() and user.phone and not user.phone_verified_at:
            return redirect("onboarding:verify_phone")
        return redirect("onboarding:start")
    messages.success(request, "Your email is confirmed. Sign in to continue.")
    return redirect("accounts:login")


@login_required
@never_cache
def verify_phone(request):
    """Only offered when a real SMS provider is configured (the mock never asks)."""
    user = request.user
    if not services.phone_verification_available() or not user.phone or user.phone_verified_at:
        return redirect("onboarding:start")
    form = PhoneCodeForm(request.POST or None)
    if request.method == "POST":
        if request.POST.get("action") == "resend":
            if not ratelimit.too_many(request, f"phone-otp:{user.pk}", limit=3, window=900):
                services.send_phone_code(user)
            return redirect("onboarding:verify_phone")
        if form.is_valid() and services.check_phone_code(user, form.cleaned_data["code"]):
            messages.success(request, "Your phone number is confirmed.")
            return redirect("onboarding:start")
        form.add_error("code", "That code is not right or has expired.")
    elif not request.GET.get("sent"):
        services.send_phone_code(user)
    return render(request, "onboarding/verify_phone.html", {"form": form, "page_title": "Confirm your phone"})


# --- Wizard ------------------------------------------------------------------------------------------------

def _require_verified(request):
    if not request.user.email_verified:
        return redirect("onboarding:verify_pending")
    return None


@login_required
@never_cache
def start(request):
    if (resp := _require_verified(request)) is not None:
        return resp
    slug = request.GET.get("org")
    session = None
    if slug:
        membership = request.user.memberships.filter(organization__slug=slug, role__key="owner").first()
        if membership is None:
            raise Http404
        if membership.organization.onboarding_completed_at:
            return redirect(membership.organization.app_path)
        session, _ = OnboardingSession.objects.get_or_create(organization=membership.organization,
                                                             defaults={"user": request.user})
    elif request.GET.get("new") != "1":
        session = request.user.onboarding_sessions.filter(completed_at__isnull=True).first()
    if session is None:
        session = OnboardingSession.objects.create(user=request.user)
    return redirect(_step_url(session, session.step))


def _step_url(session, step):
    return reverse("onboarding:step", kwargs={"pk": session.pk, "step": step})


def _session(request, pk) -> OnboardingSession:
    session = OnboardingSession.objects.select_related("organization").filter(pk=pk, user=request.user).first()
    if session is None or session.completed_at:
        raise Http404
    return session


@login_required
@never_cache
def step(request, pk, step):
    if (resp := _require_verified(request)) is not None:
        return resp
    session = _session(request, pk)
    if step not in OnboardingSession.STEPS:
        raise Http404
    if not session.reached(step) and step != session.step:
        return redirect(_step_url(session, session.step))
    if step != "business" and session.organization is None:
        return redirect(_step_url(session, "business"))
    scope = tenant(session.organization) if session.organization else nullcontext()
    with scope:
        return STEP_HANDLERS[step](request, session)


def _render(request, session, step, form, **extra):
    steps = [{"key": s, "title": STEP_TITLES[s], "url": _step_url(session, s), "reached": session.reached(s),
              "current": s == step} for s in OnboardingSession.STEPS]
    ctx = {"session": session, "step": step, "steps": steps, "form": form, "title": STEP_TITLES[step],
           "number": OnboardingSession.STEPS.index(step) + 1, "total": len(OnboardingSession.STEPS),
           "page_title": f"Set up · {STEP_TITLES[step]}",
           "back_url": _step_url(session, OnboardingSession.STEPS[OnboardingSession.STEPS.index(step) - 1])
           if step != "business" else None, **extra}
    return render(request, f"onboarding/steps/{step}.html", ctx)


def _advance(session, current):
    nxt = OnboardingSession.STEPS[OnboardingSession.STEPS.index(current) + 1]
    session.go_to(nxt)
    session.save(update_fields=["step", "data"])
    return redirect(_step_url(session, nxt))


def _business(request, session):
    org = session.organization
    if org:
        initial = {"name": org.name, "country": org.country_id, "currency": org.currency, "timezone": org.timezone,
                   "brand_colour": org.brand_colour}
    else:
        initial = {"country": "KE", "currency": "KES", "timezone": "Africa/Nairobi", "brand_colour": "#134E4A"}
    form = BusinessForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            if org is None:
                org = tenancy.create_organization(request.user, d["name"], country=d["country"].code, currency=d["currency"],
                                                  timezone_name=d["timezone"], brand_colour=d["brand_colour"].upper(),
                                                  request=request)
                session.organization = org
                session.save(update_fields=["organization"])
            else:
                org.name, org.country, org.currency = d["name"], d["country"], d["currency"]
                org.timezone, org.brand_colour = d["timezone"], d["brand_colour"].upper()
                org.save()
            if d.get("logo"):
                org.logo = d["logo"]
                org.save(update_fields=["logo"])
        return _advance(session, "business")
    return _render(request, session, "business", form)


def _industry(request, session):
    form = IndustryForm(request.POST or None, initial={"industry": session.data.get("industry")})
    if request.method == "POST" and form.is_valid():
        key = form.cleaned_data["industry"]
        if key != session.data.get("industry"):
            pack = registry.get(key)
            session.data.update({"industry": key, "sub_niche": pack.sub_niches[0].key if len(pack.sub_niches) == 1 else "",
                                 "modules": pack.default_modules()})
        return _advance(session, "industry")
    return _render(request, session, "industry", form, packs=registry.all_packs())


def _niche(request, session):
    pack = registry.get(session.data.get("industry", ""))
    if pack is None:
        return redirect(_step_url(session, "industry"))
    form = NicheForm(request.POST or None, pack=pack, initial={"sub_niche": session.data.get("sub_niche")})
    if request.method == "POST" and form.is_valid():
        sub = form.cleaned_data["sub_niche"]
        if sub != session.data.get("sub_niche"):
            session.data["modules"] = pack.default_modules(sub)
        session.data["sub_niche"] = sub
        return _advance(session, "niche")
    return _render(request, session, "niche", form, pack=pack)


def _team(request, session):
    form = TeamForm(request.POST or None, initial={"team_size": session.data.get("team_size")})
    if request.method == "POST" and form.is_valid():
        session.data["team_size"] = form.cleaned_data["team_size"]
        return _advance(session, "team")
    return _render(request, session, "team", form)


def _modules(request, session):
    pack = registry.get(session.data.get("industry", ""))
    suggested = set(pack.default_modules(session.data.get("sub_niche", "")) if pack else [])
    optional = set(pack.modules_optional if pack else [])
    form = ModulesForm(request.POST or None, initial={"modules": session.data.get("modules", sorted(suggested))})
    if request.method == "POST" and form.is_valid():
        session.data["modules"] = form.cleaned_data["modules"]
        return _advance(session, "modules")
    org = session.organization
    rows = []
    for entry in CATALOGUE.values():
        if entry.core:
            continue
        group = "suggested" if entry.key in suggested else "optional" if entry.key in optional else "other"
        rows.append({"entry": entry, "group": group,
                     "locked": bool(entry.plan_feature) and not org.has_feature(entry.plan_feature)})
    order = {"suggested": 0, "optional": 1, "other": 2}
    rows.sort(key=lambda r: order[r["group"]])
    return _render(request, session, "modules", form, rows=rows, pack=pack)


def _sample(request, session):
    form = SampleForm(request.POST or None, initial={"sample": "yes" if session.data.get("sample", True) else "no"})
    if request.method == "POST" and form.is_valid():
        session.data["sample"] = form.cleaned_data["sample"]
        return _advance(session, "sample")
    return _render(request, session, "sample", form, pack=registry.get(session.data.get("industry", "")),
                   loaders_ready=sample.available())


def _invite(request, session):
    org = session.organization
    roles = Role.objects.exclude(key="owner").order_by("sort_order", "name")
    default_role = roles.filter(key="staff").first()
    formset = InviteFormSet(request.POST or None, form_kwargs={"roles": roles}, prefix="inv",
                            initial=[{"role": default_role}] * 3)
    if request.method == "POST" and formset.is_valid():
        invites = [(f.cleaned_data["email"].lower(), f.cleaned_data["role"].pk) for f in formset
                   if f.cleaned_data.get("email")]
        limit = tenancy.seat_limit(org)
        if limit is not None and len(invites) + tenancy.seats_used(org) > limit:
            formset._non_form_errors = formset.error_class(
                [f"Your trial includes {limit} users (you plus {limit - 1}). Remove some invitations or add them later."])
        else:
            session.data["invites"] = invites
            session.save(update_fields=["data"])
            return finish(request, session)
    return _render(request, session, "invite", formset, formset=formset)


STEP_HANDLERS = {"business": _business, "industry": _industry, "niche": _niche, "team": _team, "modules": _modules,
                 "sample": _sample, "invite": _invite}


def finish(request, session):
    """Apply the industry pack and finish set-up. Runs inside the organization's tenant context."""
    org = session.organization
    d = session.data
    with transaction.atomic():
        apply_pack(org, d["industry"], d.get("sub_niche", ""), primary=True, modules=d.get("modules", []))
        org.refresh_from_db()
        org.team_size = d.get("team_size", "")
        org.onboarding_completed_at = timezone.now()
        org.settings = {**org.settings, "sample_data_requested": bool(d.get("sample"))}
        org.save(update_fields=["team_size", "onboarding_completed_at", "settings", "updated_at"])
        session.completed_at = timezone.now()
        session.save(update_fields=["completed_at"])
    if d.get("sample"):
        sample.load(org)
    sent = 0
    for email, role_id in d.get("invites", []):
        try:
            tenancy.invite(org, email, Role.objects.get(pk=role_id), request.user, request)
            sent += 1
        except (tenancy.SeatLimitError, tenancy.InvitationError) as exc:
            messages.warning(request, str(exc))
    audit("onboarding_completed", request, organization=org, industry=d["industry"], invites=sent)
    messages.success(request, f"{org.name} is ready. Your {org.trial_days_left}-day trial has started.")
    if request.user.uses_two_factor and not request.user.totp_enabled:
        return redirect(f"/accounts/two-factor/setup/?next={org.app_path}")
    return redirect(org.app_path)


@login_required
@require_POST
def cancel(request, pk):
    """Abandon a set-up that never finished (deletes the half-created organization, which has no data yet)."""
    session = _session(request, pk)
    org = session.organization
    if org and not org.onboarding_completed_at:
        if Membership.objects.filter(organization=org).exclude(user=request.user).exists():
            raise Http404
        org.delete()
    session.delete()
    return redirect("tenancy:choose")
