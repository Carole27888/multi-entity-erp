import zoneinfo

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.validators import RegexValidator

from apps.accounts.models import Role, User
from apps.core.formatting import normalise_phone
from apps.core.models import Country, Currency
from apps.core.modules import CATALOGUE
from apps.industries import registry
from apps.tenancy.models import Organization

LOGO_MAX_MB = 2
LOGO_TYPES = ("image/png", "image/jpeg", "image/webp")


class SignupForm(forms.Form):
    full_name = forms.CharField(max_length=150, label="Your name", widget=forms.TextInput(attrs={"autocomplete": "name"}))
    email = forms.EmailField(label="Work email", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    phone = forms.CharField(max_length=20, label="Mobile number", help_text="e.g. 0712 345 678",
                            widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                               help_text="At least 10 characters. Avoid common words.")
    accept_terms = forms.BooleanField(label="I agree to the terms of service and the privacy notice")
    # Honeypot: hidden from people, filled in by bots.
    company_website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Sign in instead.")
        return email

    def clean_phone(self):
        try:
            return normalise_phone(self.cleaned_data["phone"])
        except ValueError as exc:
            raise forms.ValidationError("Enter a valid mobile number, e.g. 0712 345 678.") from exc

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("company_website"):
            raise forms.ValidationError("Something went wrong. Please try again.")
        password = cleaned.get("password")
        if password:
            try:
                validate_password(password, User(email=cleaned.get("email", ""), full_name=cleaned.get("full_name", "")))
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return cleaned


class PhoneCodeForm(forms.Form):
    code = forms.CharField(max_length=6, label="Code", widget=forms.TextInput(attrs={"inputmode": "numeric",
                                                                                   "autocomplete": "one-time-code"}))


def timezone_choices():
    zones = sorted(z for z in zoneinfo.available_timezones() if z.startswith(("Africa/", "Europe/", "Asia/Dubai", "UTC")))
    return [(z, z.replace("_", " ")) for z in zones]


class BusinessForm(forms.Form):
    name = forms.CharField(max_length=150, label="Business name")
    country = forms.ModelChoiceField(queryset=Country.objects.all(), empty_label=None)
    currency = forms.ChoiceField()
    timezone = forms.ChoiceField(label="Time zone")
    logo = forms.ImageField(required=False, help_text=f"PNG, JPG or WebP, up to {LOGO_MAX_MB} MB. You can add it later.")
    brand_colour = forms.CharField(max_length=7, label="Brand colour",
                                   validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Pick a colour.")],
                                   widget=forms.TextInput(attrs={"type": "color"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["currency"].choices = [(c.code, f"{c.code} · {c.name}") for c in Currency.objects.all()]
        self.fields["timezone"].choices = timezone_choices()

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo:
            if logo.size > LOGO_MAX_MB * 1024 * 1024:
                raise forms.ValidationError(f"The logo must be {LOGO_MAX_MB} MB or smaller.")
            if getattr(logo, "content_type", None) and logo.content_type not in LOGO_TYPES:
                raise forms.ValidationError("Use a PNG, JPG or WebP image.")
        return logo


class IndustryForm(forms.Form):
    industry = forms.ChoiceField(widget=forms.RadioSelect)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["industry"].choices = registry.choices()


class NicheForm(forms.Form):
    sub_niche = forms.ChoiceField(widget=forms.RadioSelect, label="Which best describes you?")

    def __init__(self, *args, pack=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sub_niche"].choices = [(s.key, s.name) for s in (pack.sub_niches if pack else ())]


class TeamForm(forms.Form):
    team_size = forms.ChoiceField(choices=Organization.TeamSize.choices, widget=forms.RadioSelect, label="How many people work in the business?")


class ModulesForm(forms.Form):
    modules = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["modules"].choices = [(e.key, e.name) for e in CATALOGUE.values() if not e.core]


class SampleForm(forms.Form):
    sample = forms.TypedChoiceField(choices=[("yes", "Yes, add sample data"), ("no", "No, start empty")],
                                    widget=forms.RadioSelect, coerce=lambda v: v == "yes", label="Load sample data?")


class InviteRowForm(forms.Form):
    email = forms.EmailField(required=False)
    role = forms.ModelChoiceField(queryset=Role.objects.none(), required=False, empty_label=None)

    def __init__(self, *args, roles=None, **kwargs):
        super().__init__(*args, **kwargs)
        if roles is not None:
            self.fields["role"].queryset = roles


InviteFormSet = forms.formset_factory(InviteRowForm, extra=3, max_num=10)
