from django import forms
from django.db import models

from apps.accounts.models import Department, Role
from apps.core.forms import TenantModelForm
from apps.core.models import Country, Currency
from apps.onboarding.forms import LOGO_MAX_MB, LOGO_TYPES, timezone_choices
from apps.tenancy.models import Membership, Organization


class ProfileForm(forms.ModelForm):
    remove_logo = forms.BooleanField(required=False, label="Remove the current logo")

    class Meta:
        model = Organization
        fields = ["name", "legal_name", "email", "phone", "address", "kra_pin", "website_url", "country", "currency",
                  "timezone", "logo", "brand_colour"]
        widgets = {"brand_colour": forms.TextInput(attrs={"type": "color"}), "logo": forms.FileInput}

        @staticmethod
        def formfield_callback(field, **kwargs):
            if isinstance(field, models.URLField):
                kwargs["assume_scheme"] = "https"
            return field.formfield(**kwargs)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["country"].queryset = Country.objects.all()
        self.fields["country"].empty_label = None
        self.fields["currency"] = forms.ChoiceField(choices=[(c.code, f"{c.code} · {c.name}") for c in Currency.objects.all()])
        self.fields["timezone"] = forms.ChoiceField(choices=timezone_choices(), label="Time zone")
        self.fields["logo"].help_text = f"PNG, JPG or WebP, up to {LOGO_MAX_MB} MB."

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and hasattr(logo, "content_type"):
            if logo.size > LOGO_MAX_MB * 1024 * 1024:
                raise forms.ValidationError(f"The logo must be {LOGO_MAX_MB} MB or smaller.")
            if logo.content_type not in LOGO_TYPES:
                raise forms.ValidationError("Use a PNG, JPG or WebP image.")
        return logo

    def clean_brand_colour(self):
        return self.cleaned_data["brand_colour"].upper()

    def save(self, commit=True):
        org = super().save(commit=False)
        if self.cleaned_data.get("remove_logo") and not self.files.get("logo"):
            org.logo = ""
        if commit:
            org.save()
        return org


class InviteForm(forms.Form):
    email = forms.EmailField(label="Email address")
    role = forms.ModelChoiceField(queryset=Role.objects.none(), empty_label=None)

    def __init__(self, *args, can_grant_owner=False, **kwargs):
        super().__init__(*args, **kwargs)
        roles = Role.objects.all()
        if not can_grant_owner:
            roles = roles.exclude(key="owner", is_builtin=True)
        self.fields["role"].queryset = roles
        self.fields["role"].initial = roles.filter(key="staff").first()


class MembershipForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = ["role", "title", "departments", "status"]
        widgets = {"departments": forms.CheckboxSelectMultiple}

    def __init__(self, *args, can_grant_owner=False, **kwargs):
        super().__init__(*args, **kwargs)
        roles = Role.objects.all()
        if not can_grant_owner:
            roles = roles.exclude(key="owner", is_builtin=True)
        self.fields["role"].queryset = roles
        self.fields["role"].empty_label = None
        self.fields["departments"].queryset = Department.objects.all()
        self.fields["departments"].required = False


class RoleForm(TenantModelForm):
    class Meta:
        model = Role
        fields = ["name", "description", "default_scope", "two_factor_required", "idle_timeout_minutes", "session_max_hours"]
        labels = {"default_scope": "Records they can see", "two_factor_required": "Must use two-factor login"}

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = Role.objects.filter(name__iexact=name)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("A role with this name already exists.")
        return name


class DepartmentForm(TenantModelForm):
    class Meta:
        model = Department
        fields = ["name"]
