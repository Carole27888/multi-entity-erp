"""Row-level multi-tenancy: the abstract TenantModel and its fail-closed manager.

Every business model inherits TenantModel. `Model.objects` only ever returns the current organization's rows.
The organization is read when the SQL is compiled (not when the queryset is built), so querysets created early
— e.g. a ModelForm's choice fields at import time — are still scoped to whoever runs them later. Running a
scoped query with no current organization raises NoTenantError; it never falls back to "all rows".

`Model.unscoped` sees every organization and is reserved for platform code (platform admin, billing, the job
runner, provisioning); a test fails if it is used anywhere else.
"""

from django.db import models
from django.db.models.expressions import Expression

from .context import CrossTenantError, NoTenantError, get_current_organization


class CurrentOrganizationId(Expression):
    """SQL parameter holding the current organization's id, resolved at query compile time."""

    output_field = models.BigIntegerField()

    def as_sql(self, compiler, connection):
        org = get_current_organization()
        if org is None:
            model = compiler.query.model.__name__ if compiler.query.model else "a tenant model"
            raise NoTenantError(
                f"{model} was queried without a current organization. Wrap the code in `with tenant(org):`, "
                "or use .unscoped in platform code."
            )
        return "%s", [org.pk]

    def get_group_by_cols(self):
        return []

    def __repr__(self):
        return "CurrentOrganizationId()"


class TenantQuerySet(models.QuerySet):
    pass


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(organization_id=CurrentOrganizationId())


class TenantModel(models.Model):
    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.CASCADE, editable=False, related_name="+", db_index=True,
    )

    objects = TenantManager()
    unscoped = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        current = get_current_organization()
        if self.organization_id is None:
            if current is None:
                raise NoTenantError(f"Cannot save {type(self).__name__} without a current organization.")
            self.organization = current
        elif current is not None and self.organization_id != current.pk:
            raise CrossTenantError(
                f"{type(self).__name__} belongs to organization {self.organization_id}, "
                f"but the current organization is {current.pk}."
            )
        super().save(*args, **kwargs)


def is_tenant_model(model) -> bool:
    return isinstance(model, type) and issubclass(model, TenantModel)
