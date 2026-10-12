"""Form bases for tenant data."""

from django import forms

from apps.tenancy.base import CurrentOrganizationId, is_tenant_model


class TenantModelForm(forms.ModelForm):
    """Every choice field that points at a tenant model is limited to the current organization, even when a view
    passed in a queryset built from another manager, so an edited <select> value can never reference another
    organization's row."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            qs = getattr(field, "queryset", None)
            if qs is not None and is_tenant_model(qs.model):
                field.queryset = qs.filter(organization_id=CurrentOrganizationId())
