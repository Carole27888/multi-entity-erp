# PLAN

Build plan for **Pamoja** (working name until you choose one): a multi-industry, multi-tenant ERP + CRM + public website + customer portal, sold as a subscription.

Reference implementation: `/home/carole/Downloads/RealityBorisEPR` (read-only). Its patterns are reused: the module registry, the database job runner, the settings split, TOTP login, the double-entry finance module, WeasyPrint documents, backups and monitoring, the importers, data protection and the design tokens. What changes is that **every one of those is now per organization**, and a **pack registry** sits above the module registry.

Status: **approved 12 Oct 2026. Phase 1 is done (13 Oct 2026); Phase 2 is next.** The owner's answers are in [§9](#9-business-decisions-answered); the progress log is in [§10](#10-progress).

---

## 1. Architecture

### 1.1 Stack (fixed by the brief)
Python 3.12, Django 5.2, django-environ, django-htmx, django-filter, DRF, django-simple-history, whitenoise, Pillow, qrcode, openpyxl, WeasyPrint, pypdf, cryptography, optional sentry-sdk, pytest + pytest-django. Server-rendered templates + HTMX + Alpine.js + Chart.js + SortableJS, all vendored in `static/vendor/` and listed in `VERSIONS.md`. No Node, no build step. SQLite for development, MySQL or PostgreSQL in production; the test suite must pass on all three. Passenger WSGI on cPanel, with cron running `manage.py run_jobs` every 5 minutes.

Differences from the reference:
- The Django project package is **`config/`** (`config/settings/{base,dev,prod,test}.py`), so the product name is not baked into imports. The product name, domain and support email come from settings (`PRODUCT_NAME`, `PLATFORM_DOMAIN`, …).
- The reference's optional Celery adapter is **dropped**. The brief rules out workers, so the only job backends are `sync` (dev/tests) and `cron` (prod).

### 1.2 Tenancy

**Model.** `apps.tenancy.Organization` has name, slug, industry, sub_niche, country, currency (KES), timezone (Africa/Nairobi), logo, brand_colour, plan, status (trial / active / past_due / read_only / suspended / cancelled), trial_ends_at, `settings` (JSON) and `enabled_modules` (JSON list of module keys). `Domain` holds org, hostname, kind (subdomain or custom), verification token, verified_at and is_primary.

**Row-level isolation.**
```python
class TenantModel(models.Model):          # apps/tenancy/models.py, abstract
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.CASCADE, editable=False)
    objects = TenantManager()             # filtered by the current org
    unscoped = models.Manager()           # platform-admin code only; banned elsewhere by a test
```
- The current organization lives in a `contextvars.ContextVar` (`apps.tenancy.context`). It is set by middleware for requests, and by `with tenant(org):` in jobs, management commands, seeders and tests.
- **Fail closed.** `TenantManager.get_queryset()` raises `NoTenantError` when no organization is set. It never falls back to returning every row.
- `TenantModel.save()` fills `organization` from the context and refuses to save a row whose organization differs from the active one.
- Related managers, `ModelChoiceField` querysets and DRF querysets all go through `objects`, so they are scoped. Forms get a `TenantModelForm` base that re-scopes every FK/M2M field queryset, so a hidden or edited `<select>` value cannot point at another organization's row.
- Uniqueness is per organization: `UniqueConstraint(fields=["organization", "number"])`. Document numbering uses a per-org `Sequence` (the reference's sequence pattern with an `organization` column).
- Historical models (simple-history) keep `organization_id`. `AuditLog` has a nullable organization: null means a platform event.
- A test walks every model in the project and fails if a business model does not inherit `TenantModel`. The allow-list of global models (User, Organization, Plan, country templates, Job, …) is explicit and reviewed.
- A second test greps the `apps/` source and fails if `.unscoped` is used outside `apps/platformadmin`, `apps/billing`, `apps/core/jobs` and `apps/tenancy`.

**Routing decision: staff app is path-based.** It runs at `app.<domain>/<org-slug>/…`. Set with `TENANT_ROUTING = "path"`, with `"subdomain"` also supported.

Why path-based is the default:
- **One TLS certificate.** cPanel AutoSSL issues wildcard certificates only when the DNS zone is hosted on the same cPanel. Many customers' hosts can't do that, and path routing needs no wildcard.
- **Simple sessions.** One host means one session cookie and one CSRF origin. The organization switcher is just a link, and a user who belongs to several organizations stays signed in once.
- **One PWA.** The installed app has a single scope and start URL.

How path routing works. The middleware reads the first path segment, looks up the organization, moves `/<slug>` from `PATH_INFO` into `SCRIPT_NAME` and calls `set_script_prefix()`. Every `reverse()` and `{% url %}` then includes the slug automatically. URL patterns carry no `org_slug` kwarg, and the reference's registry pattern (`reverse(url_name)`) works unchanged. Slugs are checked against a reserved list (`accounts`, `platform`, `static`, `media`, `api`, `health`, `sw.js`, …).

**Public site is host-based.** It runs at `<org-slug>.<PUBLIC_DOMAIN>` or on a verified custom domain. The middleware sees a host that isn't the app host, finds the `Domain` row and sets `request.urlconf = "config.urls_public"`. Customer-portal URLs live under the public site (`/portal/…`), so customers stay on the organization's own brand and domain.
- Fallback for hosts without wildcard DNS: `app.<domain>/s/<org-slug>/…` serves the same public URLconf.
- Each custom domain must be added in cPanel as an alias with SSL. It is a manual step in the platform-admin runbook, automatable later with cPanel UAPI. Verification is a DNS TXT record or an HTTP token file.

**Request flow.**
```
Host + path → TenantMiddleware → (org, urlconf, script prefix, timezone.activate(org.tz))
            → SuspensionMiddleware (suspended/read-only → 402/blocked writes)
            → MembershipMiddleware (staff URLs need an active Membership in that org)
            → TwoFactorMiddleware → view
```

**Users.**
- `accounts.User` is global and signs in by email. The reference fields carry over (TOTP secret encrypted, hashed backup codes). New fields: phone and `is_platform_staff`.
- `tenancy.Membership` holds user, org, role, departments (M2M), status (invited / active / disabled) and invited_by.
- `Invitation` is a signed token sent by email.
- The top bar has an organization switcher that lists the user's active memberships.

**Files.**
- Uploads use `upload_to=org_path("contacts/docs")`, which gives `media/<org-id>/contacts/docs/<uuid>.<ext>`. File names are random UUIDs.
- `MEDIA_ROOT` must be outside `public_html` (checked by `check --deploy` and documented). Files are only served by `/files/<signed-id>/`, which loads the owning object through the scoped manager and checks permissions.
- Public images use `/media-public/<token>/`, which checks that the parent item is published. Responses use `X-Sendfile` when Apache supports it and fall back to `FileResponse`.

**Platform admin.** `apps.platformadmin` lives at `app.<domain>/platform/` and is reachable only by `is_platform_staff` users with 2FA.
- It shows organizations, plans, usage (users, storage, bookings this month), health and the job queue.
- Platform staff can suspend or restore an organization.
- **Impersonation** creates an `AuditLog` entry, stores the original user in the session, shows a red banner on every page and blocks money actions and password or 2FA changes while it lasts.

### 1.3 Module registry (from `apps/core/modules.py`)
The reference dataclasses are kept, with these additions:
- `Module.key`, `permissions` (actions supported, a subset of view/create/edit/delete/approve/export), `requires` (other module keys), `plan_feature` (billing gate) and `core: bool`.
- Nav labels can be **terminology keys**: `NavItem(term="lead", plural=True, url_name="crm:lead_list")`.
- `modules_for(user, org)` returns the modules enabled for the organization that the user's role can view and that the plan allows. That list drives the sidebar, the main-menu tiles and the phone bottom bar.
- Every app registers its own `Module` in `apps.py` `ready()` (`registry.register(...)`), rather than editing one central list. Apps also register their reports, dashboard widgets, permissions, search providers, import types, report-builder models, automation triggers/actions and public catalogue providers the same way.

### 1.4 Industry Pack registry
`apps/industries/registry.py` and `apps/industries/packs/<key>.py`, one file per industry:
```python
@dataclass(frozen=True)
class IndustryPack:
    key: str; name: str; icon: str; sub_niches: list[SubNiche]
    modules_default: list[str]; modules_optional: list[str]
    terminology: dict[str, Term]                  # "lead" -> Term("Enquiry", "Enquiries")
    pipelines: list[PipelineDef]                  # stages with colour, probability, is_won, is_lost
    custom_fields: list[CustomFieldDef]           # per entity: contact, lead, deal, product, …
    document_templates: list[DocTemplateDef]
    dashboard_widgets: list[str]; reports: list[str]
    automation_templates: list[AutomationDef]
    checklist: list[ChecklistItem]
    sample_data: Callable[[Organization], None] | None
    catalogue_kind: str                           # what the public site publishes
    version: int
```
- **Applying a pack** (`industries.services.apply_pack(org, key, sub_niche)`) is idempotent. It uses `get_or_create` on natural keys (`pack_key + item_key`) and records `AppliedPack(org, key, version)`.
- Rows an admin has edited carry `customised=True` and are never overwritten.
- Re-applying adds whatever is missing. Applying a second pack only adds its modules, fields and stages. Switching packs changes the primary industry and terminology but deletes nothing.
- **Terminology** is resolved in this order: organization override, then sub-niche, then pack, then core default. It is used as `{% term "lead" %}`, `{% term "lead" plural=True %}`, `{% term "deal" cap=False %}` in templates and `term("lead", org)` in Python, and cached per organization. A test renders every core template and fails on hard-coded industry words ("Property", "Tour", "Patient", …) outside packs.
- **Custom fields:** `CustomField(org, entity, key, label, type[text, number, money, date, choice, multi, bool, email, phone, url, file], options, required, help, order, section, pack_key, customised)`. Values are stored in a `custom = JSONField(default=dict)` column on the record and validated by a form mixin that builds the form fields dynamically. Filtering uses JSON key lookups, which work on SQLite 3.38+, MySQL 8 and PostgreSQL. Fields are exportable and importable.
- **Packs in this build:** Tourism & Travel and Real Estate are **deep**. The other 17 are **configuration packs**: terminology, stages, custom fields, suggested modules, document templates, checklist and sample data. `ASSUMPTIONS.md` gets a table of what each one has and what is planned.

### 1.5 Global and per-org reference data (no data migrations)
- **Global, through `post_migrate` (`<app>/setup.py`).**
  - Country templates: Kenya first. Each has its chart of accounts, VAT rates, statutory payroll tables (PAYE bands, personal relief, NSSF tiers, SHIF, AHL) with effective dates, statutory leave types and public holidays.
  - Also global: currencies, the industry list, default plans and permission definitions.
  - All of it is created idempotently with `get_or_create` and never overwrites edits. Platform staff can edit it in the platform admin.
- **Per org, through `tenancy.services.provision_organization(org)`.** It runs during onboarding, is re-runnable, and is also called by a `post_migrate` sweep so new reference rows reach existing orgs. It copies from the country template:
  - built-in roles, chart of accounts, tax rates, numbering formats and leave types
  - pipelines and fields, by applying the pack
  - Each organization can then edit its own copy.
- **Statutory payroll tables stay global** and effective-dated, because they are law, not a business preference. An organization may override them only when a platform setting allows it. (Assumption.)

### 1.6 Roles and permissions
- `accounts.Role(org, name, is_builtin, two_factor_required, session_seconds)` and `RolePermission(role, module_key, action)`. Rows instead of JSON, so they can be queried on every database.
- Built-in roles are Owner, Admin, Manager, Finance, Sales, Operations, Staff and Read-only. Custom roles are edited in a module × action matrix (an HTMX grid).
- **Record scoping**: `own` / `department` / `all`, per role and module. Sales sees its own leads, managers see their department.
- **Confidential fields** (salaries, passport numbers, medical notes, margin and cost prices, property legal documents) are declared in a registry and need an explicit permission (`hr.view_salary`, `tourism.view_margin`, …). Templates use `{% if perms_ctx.tourism.view_margin %}`, and serializers drop those fields.
- One `has_perm(user, org, "crm.lead.edit")` service is used by views (a mixin or decorator), templates, DRF permissions and the isolation test's coverage map.

### 1.7 Integrations (mock first)
Every external service has an interface, a mock and a real adapter, picked automatically when the credentials exist (from `.env` for platform-wide keys, or from the organization's encrypted `IntegrationCredential` for its own keys):

| Interface | Mock | Real adapters |
|---|---|---|
| SMS | MockSMS (stores `OutboundMessage`) | Africa's Talking |
| WhatsApp | MockWhatsApp | WhatsApp Cloud API |
| Email | console/locmem | SMTP via `EMAIL_URL` |
| Payments (card/bank) | MockCardProvider | Paystack, Flutterwave, Stripe |
| M-PESA | MockDaraja (simulated callbacks) | Daraja: C2B, STK Push, B2C |
| eTIMS | MockEtims (fake CU number + QR) | KRA eTIMS OSCU/VSCU |
| Social | MockMeta | Meta Graph (lead ads, CTWA, Messenger, IG DMs) |
| Maps | static map placeholder | OpenStreetMap static tiles / Google Static Maps |
| Portal feeds | XML to file | BuyRentKenya, Property24 |

Credentials are encrypted with Fernet (`FIELD_ENCRYPTION_KEY`), using the reference `EncryptedTextField`. Webhooks are signed (HMAC) or checked against an IP allow-list with a token, logged in `ProviderCallback` and processed idempotently, keyed on the provider transaction ID.

### 1.8 Background jobs
Copied from the reference `apps/core/jobs`: `@task`, `@interval`, `@daily`, `@monthly`, `enqueue()`, the `Job`/`JobLock`/`ScheduleState`/`JobRunnerHeartbeat` models and `run_jobs`. The tenant-aware changes:
- `enqueue()` records `organization_id` on the `Job`, and the runner wraps execution in `with tenant(org)`.
- Scheduled tasks are either platform-wide or marked `@daily(per_org=True)`. Per-org tasks run once for each active organization, each in its own tenant context and its own try/except, so one organization's failure doesn't stop the rest.
- The time zone for `at="06:00"` is the organization's time zone for per-org schedules and `TIME_ZONE` for platform ones.

### 1.9 Public layer
- **Website:** `website.Site(org, theme, seo defaults)`, `Page(slug, title, meta, og image, published)` and `Section(page, kind, order, content JSON)`, built from section templates (hero, text, gallery, catalogue grid, testimonials, contact form, map, FAQ). The builder is HTMX with SortableJS for ordering, and every page is themed by the organization's CSS variables. Each site gets a sitemap, robots, JSON-LD and Open Graph tags.
- **Catalogue providers:** each module registers what it publishes (tour packages, properties, services, products, classes, menu). The public site renders whatever the organization's modules provide, with search, filters and detail pages.
- **Forms** create CRM leads or bookings with `source=website`. Spam is stopped by a honeypot and a per-IP rate limit (the reference pattern). A consent checkbox creates a `ConsentRecord`. A deposit can be taken by STK Push or card through `PaymentIntent`.
- **Customer portal:** `portal.PortalAccount(org, contact, email, phone)`, signed in by an email or SMS OTP. It uses its own session key, **not** `django.contrib.auth`, so a customer session can never act as a staff user. Every portal query starts from `request.portal_contact` (a selector layer). Customers can view bookings, documents, invoices and receipts, pay, sign documents, open tickets and edit their profile.
- **Partner portal:** `partners.Partner(org, company contact, commission rules, net-rate access)` plus `PartnerUser`. Partners see net rates and create leads or bookings for their own clients, and their commission ledger.

---

## 2. App list

| App | Purpose | Phase |
|---|---|---|
| `core` | Base models (timestamps, soft delete), sequences, jobs, PDF, crypto, formatting (+254 phones), HTMX helpers, search, audit log, files, PWA, backup, monitoring, module registry | 1 |
| `tenancy` | Organization, Domain, Membership, Invitation, context, managers, middleware, provisioning | 1 |
| `accounts` | User, login, password reset, TOTP + backup codes, rate limit, session timeouts, roles and permissions | 1 |
| `onboarding` | Sign-up, email/phone verification, resumable wizard, getting-started checklist | 1 |
| `industries` | Pack registry, 19 packs, terminology, custom fields, pipelines, applied packs | 1 |
| `platformadmin` | Platform staff console, suspend/restore, impersonation | 1 (shell), 8 (full) |
| `orgsettings` | Organization profile, branding, modules, terminology, fields, pipelines, numbering, taxes, payment methods, integrations, users/roles | 2 |
| `crm` | Contacts, companies, leads, deals/pipeline, activities, tasks, mentions, tags, segments, duplicates/merge, assignment rules + SLA, scoring, consent | 2 |
| `catalog` | Products/services, variants, price lists | 2 |
| `sales` | Quotes (versioned, public accept link), orders/bookings, discount approvals, commissions, targets, leaderboards | 2 |
| `calendar` | Calendars, events, resources, resource bookings, public appointment slots | 2 |
| `notifications` | In-app, email, SMS, WhatsApp; per-user preferences | 2 |
| `integrations` | Messaging services, encrypted credentials, provider registry, mocks | 2 |
| `imports` | Excel/CSV import with templates, preview, row validation, de-duplication, undo | 2 |
| `finance` | Ledger, chart of accounts, invoices, receipts, credit notes, recurring, schedules, dunning, suppliers/bills/POs, expenses/petty cash, bank rec, trust, FX, budgets, statements, eTIMS | 3 |
| `payments` | PaymentIntent, provider adapters, M-PESA Daraja, callbacks, idempotency | 3 |
| `documents` | Template engine with merge fields, generated documents with versions, e-signature by OTP with an audit certificate | 3 |
| `tourism` | §5 | 4 |
| `website`, `portal`, `partners` | Public layer | 5 |
| `hr` | Employees, departments, contracts, documents/expiry, leave, holidays, attendance, expense claims, payroll, self-service | 6 |
| `marketing` | Campaigns, tracked links/UTM/QR, social inbox, broadcasts, content calendar, ad spend | 6 |
| `automation` | Workflows (trigger → conditions → actions → waits), visual builder | 6 |
| `helpdesk` | Tickets from portal, email and WhatsApp, with SLAs | 6 |
| `inventory` | Items, warehouses, stock moves, reorder levels, serials/batches | 6 |
| `projects` | Projects, milestones, tasks, time tracking, Kanban | 6 |
| `reports` | Report registry, exports, scheduled delivery, executive dashboard, report builder | 6 |
| `realestate` | §6 | 7 |
| `billing` | Plans, limits, subscriptions, platform invoices, dunning, read-only mode | 8 |
| `dataprotection` | Consent, privacy notice, data subject requests, retention, breach register | 8 (consent fields arrive in phase 2) |
| `api` | DRF, per-org tokens, outgoing webhooks | 2 (skeleton), grows each phase |

Inventory and projects move from "core" to phase 6, because no phase 1–5 pack depends on them. The Tourism pack uses its own supplier inventory (allotments).

---

## 3. Data model overview: core

Every model below inherits `TenantModel` unless marked **(global)**. Every model with money fields stores `Decimal(14,2)` plus a `currency` code.

**tenancy / accounts**
- Organization, Domain, Plan **(global)**
- User **(global)**: email, phone, TOTP fields
- Membership(user, org, role, departments, status), Invitation
- Role, RolePermission, Department
- AuditLog(org nullable, actor, impersonator, action, object ref, ip, data)

**industries**
- AppliedPack(pack_key, version)
- TerminologyOverride(key, singular, plural)
- CustomField
- Pipeline(entity, name, is_default)
- PipelineStage(pipeline, name, colour, order, probability, is_won, is_lost)
- ChecklistProgress(item_key, done_at)

**crm**
- Contact(kind person/company, company FK, names, email, phone E.164, alt phones, address, owner, source, tags, consent_marketing / consent_at / consent_channel, custom, is_repeat)
- Lead(contact, source, source_detail, campaign, tracked_link, status, score, assigned_to, assigned_at, sla_due_at, first_response_at, custom). Displayed as "Enquiry" or "Prospect" depending on the pack.
- Deal(contact, lead, pipeline, stage, value, currency, owner, expected_close, won_at, lost_reason, custom)
- Activity(kind call/whatsapp/email/meeting/note/sms, direction, contact, lead, deal, body, due/at, user)
- Task(title, assignee, due_at, reminder_at, related contact/lead/deal, done_at)
- Mention(activity, user)
- Tag, Segment(filter JSON)
- AssignmentRule(kind round_robin/rule/capacity, conditions JSON, members, SLA minutes, reassign_after)
- ScoreRule(field, op, value, points)
- MergeLog(survivor, merged data snapshot)

**catalog / sales**
- Product(kind product/service, sku, name, unit, price, tax_rate, cost, track_stock, custom), Variant, PriceList, PriceListItem
- Quote(number, version, root, contact, deal, status draft/sent/viewed/accepted/declined/expired/superseded, valid_until, currency, fx_locked JSON, public_token, accepted_at/by/ip, totals), QuoteLine
- Order(number, quote, contact, status, totals). Displayed as "Booking", "Sale" and so on.
- DiscountApproval(object ref, requested %, limit, approver, status)
- CommissionPlan, CommissionEntry, SalesTarget

**calendar**
- Calendar(owner user/resource/shared)
- Event(calendar, start, end, all_day, attendees, related)
- Resource(kind room/vehicle/staff/equipment)
- ResourceBooking (with clash check)
- AppointmentType(duration, buffer, public, staff), AvailabilityRule

**finance / payments** (reference models made tenant-aware, plus new ones)
- Ledger: Account, JournalEntry, JournalLine, TaxRate
- Sales documents: Invoice, InvoiceLine, CreditNote, Receipt, Allocation(receipt to invoice)
- Payment schedules: PaymentSchedule, Instalment, CollectionActivity
- Spending: Supplier, Bill, BillPayment, PurchaseOrder, Expense, PettyCashFloat
- Banking and trust: BankAccount, BankStatementLine, BankReconciliation, TrustMovement, TrustReconciliation
- Multi-currency and budgets: Currency **(global)**, ExchangeRate, Budget, BudgetLine
- eTIMS: EtimsSubmission
- payments: PaymentIntent(provider, purpose, object ref, amount, currency, status, idempotency_key, provider_ref), MpesaTransaction, ProviderCallback

**documents**
- DocumentTemplate(kind, name, body HTML with `{{ merge }}` fields, version, pack_key, customised)
- GeneratedDocument(template, object ref, version, file, sha256)
- SignatureRequest, Signer(OTP), SignatureEvent(ip, user agent, timestamp, hash). A certificate page is appended with pypdf.

**notifications / imports / api**
- Notification, NotificationPreference(event × channel), OutboundMessage
- ImportBatch, ImportRow(raw, cleaned, errors, created object ref, for undo)
- ApiToken(hashed, scopes), WebhookEndpoint(url, secret, events), WebhookDelivery(attempts, status)

---

## 4. Data model overview: Tourism (`apps/tourism`)

**Destinations and fees**
- Destination(parent, kind country/region/park/reserve/city/beach, name, slug, description, best_months, lat/lng, gallery)
- ParkFeeTable(destination, valid_from/to, currency, authority KWS/county/conservancy)
- ParkFeeRate(table, residency citizen/resident/non_resident, age_band adult/child/infant with min/max age, unit per_day/per_entry/per_vehicle, amount)

**Suppliers and contracts**
- SupplierProfile(finance.Supplier one-to-one, kind lodge/hotel/camp/activity/transport/airline/ground_handler, destination, commission %, markup %)
- SupplierContract(supplier, valid_from/to, document, default_release_days, cancellation policy)

**Accommodation and rates**
- Accommodation(supplier, destination, name, category, check-in/out), RoomType(max adults/children/occupancy)
- SeasonPeriod(contract, season low/high/peak/custom, start, end)
- RateSheet(contract, room_type, season, board RO/BB/HB/FB/AI, residency, basis per_person_sharing/per_room, rate, single_supplement, currency)
- ChildPolicy(contract, age_from, age_to, sharing, pct or amount)
- Allotment(room_type, start, end, rooms, release_days), AllotmentUsage

**Activities and transport**
- Activity(supplier, destination, name, duration, ActivityRate by residency and age_band, min_pax)
- Vehicle(kind land cruiser/van/bus, reg, seats, owned or supplier), DriverGuide(employee or contact, languages, licences with expiry)
- DistanceLink(from, to, km, drive_minutes), TransferRate

**Itinerary and pricing**
- Itinerary (one-to-one with `sales.Quote`): start_date, party, cover photo, inclusions/exclusions, terms, is_template, package
- Party(itinerary, residency, adults, child ages JSON)
- ItineraryDay(day_no, date, title, description, destination)
- ItineraryItem(day, order, kind accommodation/activity/transfer/flight/meal/text/park_fee, reference FK, nights, room allocation JSON, qty, unit_cost, cost_currency, fx_rate, markup_rule, sell, cost_snapshot JSON, optional, notes). Every cost line keeps the snapshot of the rate it was priced from, so changing a rate sheet never changes a sent quote.
- MarkupRule(scope global/category/supplier/line, pct or amount, rounding)

**Packages and departures**
- Package(slug, kind fixed_departure/tailor_made, template itinerary, published, gallery, highlights)
- Departure(package, start, seats, min/max pax, guaranteed, prices by residency, status), WaitlistEntry

**Bookings**
- TripBooking (one-to-one with `sales.Order`): travel dates, lead traveller, partner
- BookingLine(supplier, service dates, status requested/confirmed/cancelled, confirmation_no, cost, bill FK)
- Traveller: names, DOB, nationality, passport no (**encrypted**), dietary, medical (**encrypted**), insurance, visa notes
- Voucher(line, number, pdf)
- CancellationPolicy and CancellationTier(days_before ≥ n → % charge), used for both customer and supplier charges

**Operations and after the trip**
- VehicleAllocation(booking, vehicle, driver, start, end), with clash detection
- JobSheet, TripIncident(severity, description, actions, resolved), EmergencyContact
- TripFeedback(ratings, comment, review_requested_at, referral source)

**Accounting choice (to record in `ASSUMPTIONS.md`).**
- Customer receipts before travel go to *2300 Customer deposits (liability)*.
- Supplier payments before travel go to *1250 Prepaid supplier costs (asset)*.
- A daily job runs on each trip's start date and moves the booking's sell value to revenue and its cost to cost of sales.
- Cancellation charges are recognised on the cancellation date.

---

## 5. Real Estate (`apps/realestate`), phase 7, summary
The reference project's features become tenant-scoped: properties, amenities, confidential documents, galleries, price history, viewings with agent check-out/check-in, offers → KYC → deposit to trust → agreement → completion, double-allocation detection and commissions. New in this build:
- rental management: leases, rent billing, arrears, landlord statements and remittances, and maintenance work orders with contractors
- off-plan developments: project → block → unit, with time-limited holds and instalment schedules
- public listings and portal feeds through an adapter
- tenant and landlord portals, which reuse `portal` with extra roles

A detailed data model will be written at the start of phase 7.

---

## 6. Phases and definition of done

Each phase ends with:
- **pytest all green on SQLite** (MySQL and PostgreSQL are run when available locally; the CI matrix is documented)
- `check --deploy` clean with prod settings
- the tenant-isolation suite green
- headless-Chrome screenshots of every new screen at 1280px and 390px, reviewed and fixed
- `README.md`, `.env.example` and `ASSUMPTIONS.md` updated
- `seed_demo` working, and a short report to you

Then I stop and wait for "continue".

**Phase 1: Foundation and tenancy**
- *Project:* `config/` settings split, requirements, `passenger_wsgi.py`, `deploy.sh`, `.gitignore` (migrations, `.env`, db, media, logs, backups)
- *Design and PWA:* design system (tokens, base/layout/components, Manrope, icons, per-org brand colour through CSS variables with automatic contrast-safe text colour), base templates, PWA (manifest, service worker, offline page, icons)
- *Jobs:* job runner made tenant-aware
- *Tenancy and isolation tests:* the TenantModel base and tenant managers, middleware, routing, file serving, and the isolation test framework with its URL-coverage enforcement
- *Accounts:* login, password reset, eye toggle, TOTP and backup codes, rate limit, role session timeouts, audit log
- *Roles and permissions:* roles, custom roles and the permission matrix
- *Registration and onboarding:* sign-up, email verification (phone OTP once SMS is live), the onboarding wizard (all steps, resumable) and the 14-day trial
- *Packs:* module and pack registries, all 19 configuration packs (sample data for Tourism and Real Estate is minimal until phases 4 and 7), terminology tag and custom-field engine, getting-started checklist, organization switcher
- *Platform admin:* shell with an organization list, suspend/restore and impersonation with a banner
- *Done when:*
  - two orgs can be onboarded with different packs, and each sees its own terminology and stages
  - the isolation test covers 100% of tenant URLs
  - 2FA is enforced for Owner, Admin and Finance
  - `run_jobs` runs per-org jobs

**Phase 2: CRM and the sales core**
- crm, catalog and sales (quotes with PDF and a public accept link)
- calendar, tasks and notifications
- orgsettings (all settings screens that exist so far), custom fields UI, imports, audit trail views
- API skeleton (tokens, contacts and leads endpoints) with webhooks
- *Done when:* each feature is tested, Kanban works at 390px, assignment and SLA reassignment run through jobs, and import has preview and undo.

**Phase 3: Finance and documents**, built in this order:
1. ledger and chart of accounts by country template
2. invoices (VAT, recurring), receipts, credit notes
3. payment schedules and dunning
4. payments with M-PESA (C2B, STK, B2C) and the card interface
5. suppliers, bills, POs, expenses and petty cash
6. bank reconciliation, trust accounts, FX and budgets
7. statements (P&L, balance sheet, trial balance, cash flow, aged AR/AP)
8. eTIMS mock

Then: the document engine, invoice and receipt PDFs in the reference style, and e-signature.
- *Done when:* every posting balances (tested), every money action is atomic and in history, callback tests cover signature, IP, replay and idempotency, and PDFs render.

**Phase 4: Tourism in full** (§4 and section 7 of the brief)
- itinerary builder with drag-and-drop and the live costing panel
- proposal PDF and public proposal page with Accept & pay deposit
- packages and departures, booking flow, vouchers, rooming lists and manifests, cancellations
- operations dashboard, allocation calendar with clash detection, job sheets
- finance links and revenue recognition
- after-trip features, tourism reports, and sample data for a Kenyan safari operator
- *Done when:* the end-to-end smoke test passes (enquiry → quote → accept → deposit by mock STK → booking → supplier confirmations → vouchers → travel-date revenue recognition → feedback).

**Phase 5: Public layer**
- website builder, public catalogue and booking with deposit
- customer portal and partner portal
- custom domain verification, SEO (sitemap, JSON-LD, OG)
- *Done when:* the portal-scoping tests pass (customer A can never see customer B, in the same org or across orgs).

**Phase 6:** HR and Kenyan payroll; marketing and automation with the visual builder; helpdesk; inventory and projects; reports, exports, scheduled delivery, executive dashboard and report builder.

**Phase 7:** Real Estate in full (§5).

**Phase 8:** SaaS billing and plan limits; read-only mode; the complete platform admin; backups and restore drill per the reference; monitoring and the status page; data protection in full; production hardening; the cPanel/Passenger deployment guide.

**Phase 9:** deep modules for further industries, in the order you choose.

---

## 7. Testing strategy
- **Factories:** `tests/factories.py` (plain functions, as in the reference) plus `org_factory(pack=…)` and fixtures `org1`, `org2`, `user_a`, `user_b`, `client_a` and `client_b` (logged in, with their tenant prefixes).
- **`tests/test_isolation.py`:**
  1. Seed both orgs fully with every pack's sample data.
  2. Walk `get_resolver()` for every tenant URL pattern.
  3. Fill each URL's kwargs with **org 2's** object ids, using a `url_name → model` coverage map that views declare (for example `TenantDetailView.model`).
  4. As user A, request GET (and POST for actions) and expect 404 or 403, and assert that no org 2 identifiers appear in list, search, export, file or API responses.
  5. Fail if any tenant URL is neither covered nor exempted with a written reason.
- **Portal scoping:** the same approach for the portal URLconf, with two contacts in the same organization.
- **Payments:** a signed versus unsigned callback, IP allow-list, a duplicate callback (idempotent), amount mismatch, and an out-of-order STK result.
- **Per pack:** a smoke test that runs `seed_demo --pack <key>` and then GETs every enabled module's home page and the main reports, expecting 200.
- **Fail-closed managers:** querying without a tenant raises, and saving across orgs raises.
- **Database matrix:** SQLite locally; `DATABASE_URL` set to MySQL/PostgreSQL in CI.

## 8. Risks and mitigations
- **Scope.** The brief is a multi-month build. Each phase delivers working, tested features rather than broad stubs. Anything that won't fit a phase at quality goes into this file under "Deferred" with its reason.
- **Missing row filters** are the classic row-level-tenancy failure. Mitigated by fail-closed managers, form queryset re-scoping, the model-inheritance test, the `.unscoped` usage test and the URL-coverage isolation test.
- **WeasyPrint on cPanel** needs Pango. The reference README's notes apply; if Pango is missing, the PDF service degrades to a clear error page, never a crash.
- **MySQL JSON lookups and case sensitivity.** The suite must be run on MySQL before phase 3 closes, and the collation (`utf8mb4_unicode_ci`) is documented.
- **Custom domains on shared hosting** need manual cPanel steps, which the runbook covers.

## 9. Business decisions (answered)
1. **Name and domain:** Pamoja at [domain.co.ke], kept in settings.
2. **Payments:** M-PESA (Daraja) first overall, then Paystack, then Flutterwave. Stripe stays mocked.
3. **Platform company:** `.env` placeholders (`PLATFORM_LEGAL_NAME`, `PLATFORM_KRA_PIN`, `PLATFORM_VAT_REGISTERED`, `PLATFORM_PAYBILL`). Real values are due before Phase 8.
4. **Plans** are seeded in the database and editable in admin:

   | Plan | KES / month | Users | Includes |
   |---|---|---|---|
   | Starter | 2,500 | 3 | 1 pack, `/s/<slug>/` site, 2 GB |
   | Growth | 7,500 | 10 | custom domain, customer portal, 10 GB |
   | Business | 20,000 | 30 | partner portal, API and webhooks, 50 GB |

   The trial is 14 days with Growth features, and annual billing gets 2 months free.
5. **Wildcard subdomains:** off by default (`WILDCARD_SUBDOMAINS=False`), with `/s/<slug>/` as the default public address. The README lists what to ask the host for.

## 10. Progress

### Phase 1: done (13 Oct 2026)

**What was built:**
- the `config/` settings split, the tenant-aware job runner, the design system with per-organization brand colours, and the PWA
- tenancy: fail-closed managers, path / subdomain / custom-domain routing, and permission-checked files
- accounts with TOTP, backup codes, rate limits, idle and maximum session limits, and password reset
- built-in and custom roles with a permission matrix and record scopes
- sign-up with email verification (phone OTP once SMS is live) and the 7-step resumable wizard
- the pack registry with all 19 packs, terminology, the custom-field engine and the getting-started checklist
- the settings screens (profile and branding, modules, team and invitations, roles, departments)
- the platform admin shell (organizations, suspend and restore, impersonation)
- `seed_demo --pack/--reset`

**Results:**
- `pytest`: 170 passed on SQLite. This includes the URL-walking isolation suite, one smoke test per pack and `check --deploy`.
- Screenshots: 24 screens at 1280px and 390px are in `screenshots/phase1/` (gitignored). No horizontal scroll at 390px.

**Carried forward:**
- The suite has not been run on MySQL or PostgreSQL yet. Both servers are installed on the development machine, but no credentials were available. This needs a test user (see the Phase 2 report).
- Moved to Phase 2: the screens for custom fields and terminology overrides, and the sample-data loaders (organizations that asked for sample data are flagged).
- Moved to Phase 5: the public-image view and self-service custom-domain verification.
