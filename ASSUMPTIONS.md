# Assumptions

These are decisions I made where the brief was silent or ambiguous. Any of them can be changed.

## Planning (12 Oct 2026)

**Project layout**
- The Django project package is `config/`, not the product name. That way the name (still to be decided) can change without renaming imports. The product name, platform domain and support email come from settings.
- The reference project's optional Celery adapter is not carried over. The brief rules out workers, so the job backends are `sync` (dev and tests) and `cron` (production).

**Tenancy and routing**
- **The staff app uses path-based routing** (`app.<domain>/<org-slug>/…`), with subdomain routing available through `TENANT_ROUTING`. Path routing needs no wildcard TLS certificate, which cPanel AutoSSL only issues when the DNS zone is on the same cPanel. It also gives one session cookie and CSRF origin, and one PWA scope. The organization slug moves into `SCRIPT_NAME`, so `reverse()` adds it automatically.
- **The public site and customer portal are host-based** (`<slug>.<public-domain>` or a verified custom domain). Where wildcard DNS isn't available, they fall back to `app.<domain>/s/<slug>/`.
- **Tenant managers fail closed.** A query on a tenant model with no current organization raises an error instead of returning every row.
- **Primary keys are global integers**, and staff URLs use them. Lookups through scoped managers return 404 for other organizations' rows. Public and customer-facing links use random tokens, never primary keys.

**Users and roles**
- **Customer portal accounts are separate from staff `User` accounts** (`portal.PortalAccount`, signed in by OTP, with their own session key). A customer session can never act as staff.
- **Role permissions are stored as rows** (`RolePermission(role, module, action)`), not JSON, so they can be queried on SQLite, MySQL and PostgreSQL alike.

**Reference data and rates**
- **Statutory payroll tables are global per country and effective-dated**, maintained by platform staff, because they are law. VAT rates, the chart of accounts, leave types and numbering are copied into each organization on provisioning, and each organization edits its own copy.

**Tourism accounting**
- Customer money received before travel is held as a liability (Customer deposits). Supplier prepayments are held as an asset. Revenue and cost of sales are recognised on the trip start date by a daily job. Cancellation charges are recognised on the cancellation date.

**Scope**
- **Inventory and Projects** are built in phase 6, since no pack built in phases 1–5 depends on them. Tourism uses its own allotment-based supplier inventory.
