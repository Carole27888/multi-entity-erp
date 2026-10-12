"""Custom fields on core records: definitions are CustomField rows, values sit in the record's `custom` JSON.

    class ContactForm(CustomFieldsFormMixin, TenantModelForm):
        custom_entity = "contact"

The mixin adds one form field per active definition (named cf_<key>), fills it from instance.custom and writes
cleaned values back into instance.custom (JSON-safe: dates as ISO strings, amounts as strings).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from apps.core.formatting import normalise_phone

from .models import CustomField

PREFIX = "cf_"


def definitions(entity: str):
    return CustomField.objects.filter(entity=entity, is_active=True).order_by("order", "label")


def form_field(defn: CustomField) -> forms.Field:
    common = {"label": defn.label, "required": defn.required, "help_text": defn.help_text}
    t = defn.type
    if t == CustomField.Type.TEXTAREA:
        return forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), **common)
    if t == CustomField.Type.NUMBER:
        return forms.DecimalField(max_digits=18, decimal_places=4, **common)
    if t == CustomField.Type.MONEY:
        return forms.DecimalField(max_digits=14, decimal_places=2, **common)
    if t == CustomField.Type.DATE:
        return forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), **common)
    if t == CustomField.Type.CHOICE:
        return forms.ChoiceField(choices=[("", "—")] + [(o, o) for o in defn.options], **common)
    if t == CustomField.Type.MULTI:
        return forms.MultipleChoiceField(choices=[(o, o) for o in defn.options], widget=forms.CheckboxSelectMultiple, **common)
    if t == CustomField.Type.BOOL:
        common["required"] = False
        return forms.BooleanField(**common)
    if t == CustomField.Type.EMAIL:
        return forms.EmailField(**common)
    if t == CustomField.Type.URL:
        return forms.URLField(assume_scheme="https", **common)
    if t == CustomField.Type.PHONE:
        return forms.CharField(max_length=20, **common)
    return forms.CharField(max_length=255, **common)


def to_json(defn: CustomField, value):
    if value in (None, "", []):
        return None
    if isinstance(value, Decimal):
        return str(value.normalize()) if defn.type == CustomField.Type.NUMBER else f"{value:.2f}"
    if isinstance(value, date):
        return value.isoformat()
    if defn.type == CustomField.Type.PHONE:
        try:
            return normalise_phone(value)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
    return value


def from_json(defn: CustomField, value):
    if value is None:
        return None
    if defn.type == CustomField.Type.DATE and isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    if defn.type in (CustomField.Type.NUMBER, CustomField.Type.MONEY):
        return Decimal(str(value))
    return value


class CustomFieldsFormMixin:
    custom_entity: str = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._custom_defs = list(definitions(self.custom_entity)) if self.custom_entity else []
        instance = getattr(self, "instance", None)
        current = getattr(instance, "custom", None) or {}
        for defn in self._custom_defs:
            name = PREFIX + defn.key
            self.fields[name] = form_field(defn)
            if not self.is_bound:
                self.initial[name] = from_json(defn, current.get(defn.key))

    @property
    def custom_field_names(self) -> list[str]:
        return [PREFIX + d.key for d in self._custom_defs]

    def clean(self):
        cleaned = super().clean()
        values = {}
        for defn in self._custom_defs:
            name = PREFIX + defn.key
            if name in self.errors:
                continue
            try:
                values[defn.key] = to_json(defn, cleaned.get(name))
            except ValidationError as exc:
                self.add_error(name, exc)
        self.custom_values = {k: v for k, v in values.items() if v is not None}
        return cleaned

    def apply_custom_values(self, obj) -> None:
        """Merge cleaned values into obj.custom, keeping keys of fields that were switched off."""
        data = dict(getattr(obj, "custom", None) or {})
        for defn in self._custom_defs:
            data.pop(defn.key, None)
        data.update(getattr(self, "custom_values", {}))
        obj.custom = data

    def save(self, commit=True):
        obj = super().save(commit=False)
        self.apply_custom_values(obj)
        if commit:
            obj.save()
            if hasattr(self, "save_m2m"):
                self.save_m2m()
        return obj
