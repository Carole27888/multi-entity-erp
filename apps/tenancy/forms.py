from django import forms

from apps.accounts.models import User


class AcceptInviteForm(forms.Form):
    """For someone who has no account yet: their name and a password."""

    full_name = forms.CharField(max_length=150, label="Your name")
    phone = forms.CharField(max_length=20, required=False, label="Mobile number")
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), label="Choose a password")

    def __init__(self, *args, email="", **kwargs):
        self.email = email
        super().__init__(*args, **kwargs)

    def clean_phone(self):
        from apps.core.formatting import normalise_phone

        try:
            return normalise_phone(self.cleaned_data.get("phone"))
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean_password(self):
        from django.contrib.auth.password_validation import validate_password

        password = self.cleaned_data["password"]
        validate_password(password, User(email=self.email, full_name=self.data.get("full_name", "")))
        return password
