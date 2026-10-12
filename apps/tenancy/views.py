"""Platform pages about organizations: choosing one, and accepting an invitation."""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache

from apps.accounts.models import User
from apps.accounts.two_factor import VERIFIED

from . import services
from .forms import AcceptInviteForm


@login_required
@never_cache
def choose_organization(request):
    memberships = list(request.user.active_memberships())
    ready = [m for m in memberships if m.organization.onboarding_completed_at]
    if request.GET.get("all") != "1":
        if len(memberships) == 1 and ready:
            return redirect(ready[0].organization.app_path)
        last = next((m for m in ready if m.organization_id == request.user.last_organization_id), None)
        if last and len(ready) > 1 and request.GET.get("switch") != "1":
            return redirect(last.organization.app_path)
        if not memberships:
            if request.user.is_platform_staff:
                return redirect("platformadmin:dashboard")
            return redirect("onboarding:start")
    return render(request, "tenancy/choose.html", {"page_title": "Your organizations", "memberships": memberships})


@never_cache
def accept_invite(request, token):
    inv = services.find_invitation(token)
    if inv is None:
        return render(request, "tenancy/invite_invalid.html", status=404)
    from .models import Organization

    org = Organization.objects.get(pk=inv.organization_id)
    existing = User.objects.filter(email__iexact=inv.email).first()

    if request.user.is_authenticated:
        if request.user.email.lower() != inv.email.lower():
            return render(request, "tenancy/invite_wrong_user.html", {"inv": inv, "org": org}, status=403)
        if request.method == "POST":
            services.accept_invitation(inv, request.user, request)
            messages.success(request, f"Welcome to {org.name}.")
            return redirect(org.app_path)
        return render(request, "tenancy/invite_accept.html", {"inv": inv, "org": org, "form": None})

    if existing is not None:
        messages.info(request, "Sign in to accept the invitation.")
        return redirect(f"/accounts/login/?next=/invite/{token}/")

    form = AcceptInviteForm(request.POST or None, email=inv.email)
    if request.method == "POST" and form.is_valid():
        user = User.objects.create_user(email=inv.email, password=form.cleaned_data["password"],
                                        full_name=form.cleaned_data["full_name"], phone=form.cleaned_data["phone"])
        services.accept_invitation(inv, user, request)
        login(request, user, backend="apps.accounts.backends.EmailBackend")
        request.session[VERIFIED] = False
        messages.success(request, f"Welcome to {org.name}.")
        if user.uses_two_factor:
            return redirect(f"/accounts/two-factor/setup/?next={org.app_path}")
        return redirect(org.app_path)
    return render(request, "tenancy/invite_accept.html", {"inv": inv, "org": org, "form": form})


def org_missing(request, *args, **kwargs):
    raise Http404
