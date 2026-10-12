from django import forms
from django.contrib.auth import authenticate


class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    remember_me = forms.BooleanField(required=False, initial=True, label="Keep me signed in")

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        email, password = cleaned.get("email"), cleaned.get("password")
        if email and password:
            self.user = authenticate(self.request, email=email, password=password)
            if self.user is None:
                raise forms.ValidationError("Email or password is incorrect.")
        return cleaned


class CodeForm(forms.Form):
    """A 6-digit authenticator code or a backup code (e.g. k7m2-9xq4)."""

    code = forms.CharField(max_length=20, label="Code", widget=forms.TextInput(attrs={
        "autocomplete": "one-time-code", "inputmode": "text", "autofocus": True, "placeholder": "123 456", "class": "code-input"}))

    def clean_code(self):
        return self.cleaned_data["code"].strip()
