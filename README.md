# Pamoja

A multi-industry, multi-tenant business platform: ERP + CRM + public website + customer portal, sold as a subscription.

When a business signs up, it picks its industry. The platform then configures itself for that industry: modules, menus, terminology, pipeline stages, custom fields, documents and the getting-started checklist.

Built with Django 5.2, HTMX, Alpine.js and hand-written CSS. **No Node.js, npm or build step.** It runs on cPanel shared hosting with Passenger and cron, and on SQLite, MySQL or PostgreSQL.

> **Build status: Phase 1 of 9 is done.** It covers the foundation, multi-tenancy, accounts and 2FA, roles, onboarding and all 19 industry configuration packs. See [PLAN.md](PLAN.md) for the phases and [ASSUMPTIONS.md](ASSUMPTIONS.md) for every judgement call.

The product name, domains and platform company details are settings (`PRODUCT_NAME`, `PLATFORM_DOMAIN`, `APP_HOST`, `PLATFORM_*`), so they can change without code edits.

---

## Quick start (local)

Requires Python 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python manage.py makemigrations          # migrations are not committed (see "Repository rules")
python manage.py migrate                 # also seeds plans, countries, currencies and built-in roles
python manage.py seed_demo               # one demo organization per industry pack
python manage.py runserver
```

Open http://127.0.0.1:8000. You don't need a `.env` file: SQLite and inline jobs are the defaults. To change anything, copy `.env.example` to `.env`.

### Demo logins

The password for every demo account is **`Demo@2026!`**.

| Who | Email | Notes |
|---|---|---|
| Platform staff | `platform@demo.co.ke` | Platform admin at `/platform/` and Django admin at `/django-admin/` |
| Member of two organizations | `wanjiku@demo.co.ke` | Sales in Savannah Trails Safaris, Manager in Kilimani Homes. Shows the organization switcher. No 2FA needed. |
| Owner of each demo organization | `owner@<slug>.co.ke` | e.g. `owner@savannah-trails.co.ke`, `owner@kilimani-homes.co.ke` |
| Tourism team | `mary@`, `john@`, `beatrice@`, `kelvin@`, `halima@`, `moses@`, `joseph@`, `director@` `savannah-trails.co.ke` | One person per built-in role |
| Real estate team | `stephen@`, `caroline@`, `dennis@`, `sarah@`, `james@`, `lucy@`, `director@` `kilimani-homes.co.ke` | One person per built-in role |

Owners, admins, finance users and platform staff must set up an authenticator app on first sign-in. For a quick local demo without a phone, put `TWO_FACTOR_ENFORCED=False` in `.env`.

The `seed_demo` command takes these options:
- `--pack tourism` seeds one pack. Pack keys: `tourism`, `real_estate`, `hospitality`, `restaurants`, `retail`, `wholesale`, `manufacturing`, `construction`, `professional_services`, `healthcare`, `education`, `salons_spas`, `fitness`, `events`, `logistics`, `automotive`, `agriculture`, `nonprofit`, `generic`.
- `--reset` deletes the demo organizations and users first.

Business records (contacts, enquiries, bookings) arrive with each module's sample loader from Phase 2 on.

### Tests

```bash
pytest
```

The suite has 170 tests. It includes:
- the tenant-isolation suite (`tests/test_isolation.py`)
- a seeded smoke test for each of the 19 packs
- a `check --deploy` run with production settings

Run the suite against MySQL and PostgreSQL too: `DATABASE_URL=postgres://… pytest`.

---

## How it fits together

### Organizations and URLs

| What | Where |
|---|---|
| Sign-in, sign-up, onboarding, organization chooser | `https://APP_HOST/accounts/…`, `/signup/`, `/onboarding/`, `/orgs/` |
| An organization's staff app | `https://APP_HOST/<org-slug>/…` (`TENANT_ROUTING=path`, the default) |
| Its public website | `https://APP_HOST/s/<org-slug>/` always works |
| | `https://<org-slug>.PUBLIC_DOMAIN/` when `WILDCARD_SUBDOMAINS=True` (Growth plan and up) |
| | its own verified custom domain (Growth plan and up) |
| Platform admin | `https://APP_HOST/platform/` |
| Health check for uptime monitors | `https://APP_HOST/health/` |

**Data isolation.** Every business table has an `organization` column, through the abstract `apps.tenancy.base.TenantModel`.
- `Model.objects` only returns the current organization's rows. If no organization is set, the query raises an error instead of returning everything.
- `Model.unscoped` is for platform code only, and a test enforces that.
- `tests/test_isolation.py` walks every staff URL and proves that organization 1 can never see, change or download organization 2's data.

**Files.** Uploads are stored under `MEDIA_ROOT/<org-id>/…` and are never served by a public URL. Downloads go through a permission-checked view. Keep `MEDIA_ROOT` outside `public_html`.

### Industry packs and modules

- The pack registry is in `apps/industries/registry.py`, with one file per industry in `apps/industries/packs/`. A pack sets the terminology (`{% term "lead" %}` gives "Enquiry" for a tour operator), pipeline stages, custom fields, suggested modules, document templates, reports, automations and the checklist.
- The module registry is in `apps/core/modules.py`. It drives the sidebar, the dashboard tiles and the phone bottom bar. A module shows when the organization has it switched on, its plan allows it, the user's role can view it, and its pages exist.
- Roles: the built-in roles are Owner, Admin, Manager, Finance, Sales, Operations, Staff and Read-only. Custom roles are built in a module × action matrix under Settings › Roles & permissions, with a record scope (own / department / all).

### Background jobs

These are database jobs run by cron, with no workers. Use `@task`, `@interval`, `@daily` and `@monthly` from `apps.core.jobs`.
- `per_org=True` runs a schedule once for each running organization, at that organization's local time.
- `enqueue()` remembers the organization and runs the job inside it.

---

## Deploying on cPanel (Phusion Passenger)

The app is WSGI only. There is no Docker, gunicorn, uvicorn or Celery.

1. **Create the Python app.** In cPanel, open *Setup Python App* › *Create Application* and enter:
   - Python version: 3.12
   - Application root: e.g. `platform`
   - Application URL: `app.domain.co.ke`
   - Startup file: `passenger_wsgi.py`
   - Entry point: `application`
2. **Upload the code** into the application root, using git or a file upload. `passenger_wsgi.py` uses `config.settings.prod`.
3. **Create the database** in cPanel's *MySQL Databases* or *PostgreSQL Databases*. For MySQL, also run `pip install -r requirements-mysql.txt`. If `mysqlclient` won't build, set `DB_MYSQL_DRIVER=pymysql`.
4. **Create `.env`** in the application root from `.env.example`. At minimum, set:
   ```dotenv
   SECRET_KEY=<long random string>
   PRODUCT_NAME=…
   PLATFORM_DOMAIN=domain.co.ke
   APP_HOST=app.domain.co.ke
   SITE_URL=https://app.domain.co.ke
   CSRF_TRUSTED_ORIGINS=https://app.domain.co.ke
   DATABASE_URL=mysql://user:pass@localhost:3306/dbname
   MEDIA_ROOT=/home/USER/platform_media        # outside public_html
   JOBS_BACKEND=cron
   EMAIL_URL=smtp+tls://…
   ADMINS=Ops:ops@domain.co.ke
   FIELD_ENCRYPTION_KEY=<long random string, keep a copy off the server>
   ```
5. **Install and build.** Open the virtualenv command shown at the top of the cPanel app page, then run:
   ```bash
   ./deploy.sh                          # installs, makes and applies migrations, collectstatic, check --deploy, restarts
   python manage.py createsuperuser     # first deploy only: your platform-staff account
   ```
6. **HTTPS.** Run AutoSSL in *SSL/TLS Status*. Production settings redirect to HTTPS and send HSTS headers.
7. **Cron.** In *Cron Jobs*, add this to run every 5 minutes:
   ```
   */5 * * * * /home/USER/virtualenv/platform/3.12/bin/python /home/USER/platform/manage.py run_jobs >> /home/USER/platform/logs/cron.log 2>&1
   ```
8. **Restart** after any change, with `touch tmp/restart.txt` or *Restart* in *Setup Python App*.

### What to ask the host for (public subdomains)

Public sites work at `https://app.domain.co.ke/s/<org-slug>/` with no extra setup. To give each organization `https://<org-slug>.domain.co.ke`, ask your host for two things:
1. **A wildcard DNS record**: `*.domain.co.ke` (A or CNAME) pointing at the same server as `app.domain.co.ke`.
2. **A wildcard TLS certificate** for `*.domain.co.ke`. cPanel AutoSSL can only issue it when the DNS zone is hosted on that cPanel; otherwise the host installs one, e.g. Let's Encrypt with DNS validation.

The domain must also be added in cPanel as an alias, or as a wildcard subdomain pointing at the app's document root. Then set `WILDCARD_SUBDOMAINS=True` and restart.

### Custom domains for tenants

A tenant on Growth or above adds its domain. A platform admin then does three things:
1. Adds the domain in cPanel as an alias of the app.
2. Runs AutoSSL for it.
3. Marks it verified once the tenant's DNS points at the server (a `Domain` row in `/django-admin/`).

Phase 5 adds self-service verification with a DNS TXT token.

---

## Repository rules

- Never commit `.env`, `db.sqlite3`, `media/`, `logs/`, `backups/` or `screenshots/`. They are all in `.gitignore`.
- **Migrations are not committed.** Each machine runs `makemigrations` and `migrate`.
- Reference data is never put in a data migration. It goes in an app's `setup.py`, connected to `post_migrate`, created with `get_or_create`, and it never overwrites edits.
- Per-organization reference data, such as built-in roles, is created by `apps.tenancy.services.provision_organization`, which is re-run for every organization after each `migrate`.
- Front-end libraries are vendored in `static/vendor/`, with versions listed in `static/vendor/VERSIONS.md`.
- Every setting is documented in `.env.example`. A test fails if one is missing.
