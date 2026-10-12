"""post_migrate: bring every organization's per-org reference data up to date (built-in roles, provisioners).
Idempotent and never overwrites an organization's own edits."""


def run(sender=None, **kwargs):
    from .models import Organization
    from .services import provision_organization

    for org in Organization.objects.all():
        provision_organization(org)
