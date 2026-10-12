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

## Business decisions from the owner (12 Oct 2026)

- **Name and domain.** The product is "Pamoja" at "[domain.co.ke]" for now. Both are settings (`PRODUCT_NAME`, `PLATFORM_DOMAIN`, `APP_HOST`, `PUBLIC_DOMAIN`), so they can change later without code edits.
- **Payment providers, in build order:**
  1. M-PESA (Daraja) first overall.
  2. Paystack is the first card provider (it serves Kenyan businesses, cards and M-PESA).
  3. Flutterwave second.
  4. Stripe stays mocked, because it doesn't onboard Kenyan-registered businesses directly.
- **Platform company details** come from `.env` placeholders (`PLATFORM_LEGAL_NAME`, `PLATFORM_KRA_PIN`, `PLATFORM_VAT_REGISTERED`, `PLATFORM_PAYBILL`). The real values are due before Phase 8.
- **Plans** are stored in `billing.Plan` and editable in `/django-admin/`. They are seeded once and never overwritten:

  | Plan | KES / month | Users | Industry packs | Storage | Public site | Custom domain | Customer portal | Partner portal | API & webhooks |
  |---|---|---|---|---|---|---|---|---|---|
  | Starter | 2,500 | 3 | 1 | 2 GB | `/s/<slug>/` only | – | – | – | – |
  | Growth | 7,500 | 10 | 2 (my choice) | 10 GB | + subdomain | ✓ | ✓ | – | – |
  | Business | 20,000 | 30 | 5 (my choice) | 50 GB | + subdomain | ✓ | ✓ | ✓ | ✓ |

  Plan details:
  - The trial lasts 14 days with Growth features (`TRIAL_PLAN=growth`).
  - Annual price defaults to 10 × monthly (2 months free) unless set.
  - **My assumptions:** public bookings per month are Starter 50, Growth 500 and Business unlimited. The Growth and Business pack counts in the table are also mine.
  - "Users" counts active members plus open invitations.
- **Wildcard subdomains** are off by default (`WILDCARD_SUBDOMAINS=False`); `/s/<slug>/` is the default public address. The README lists what to ask the host for. Custom domains work either way.

## Phase 1: foundation (12–13 Oct 2026)

### Tenancy
- **The organization is resolved at SQL compile time.** `TenantModel.objects` adds a `CurrentOrganizationId()` expression that reads the current organization when the query runs. It does not read it when the queryset is built.
  - This matters because ModelForm choice fields build their querysets at import time, outside any organization. They are still scoped correctly when the form is used.
  - A query with no current organization raises `NoTenantError`.
- **Saving across organizations is refused.** Saving a row whose organization differs from the current one raises `CrossTenantError`.
- **Uploads always land in the right folder.** A file saved before its row has an organization goes into the current organization's folder; if no organization is set, the save fails. The isolation test caught the earlier `media/None/` bug.
- **Membership is a global table filtered by organization**, not a `TenantModel`. The organization switcher has to list a user's memberships across organizations. Every tenant view filters it by `request.organization`.
- **Deleting an organization works as a whole.** `Membership.role` uses `RESTRICT`, so a role that people hold can't be deleted, but deleting a whole organization (or cancelling an unfinished set-up) works.
- **Non-members get a 404.** Someone who isn't a member gets a 404 for every page of an organization, never a 403, so the organization's pages don't reveal that it exists.
- **Host checking is done by the tenant middleware.** `ALLOWED_HOSTS = ["*"]`, because tenants add custom domains at run time. `TenantMiddleware` answers 400 for any host that is not the app host, a platform subdomain or a verified custom domain. Emails build links from `SITE_URL`, never from the Host header.
- **Uploads are never served at `/media/`.** `MEDIA_URL` is a path that nothing serves. Organization logos are public by nature and are served at `/media-public/logo/<slug>/`. Every other file goes through `core:attachment`, which looks the row up with the scoped manager and checks its permission.
- **The app is assumed to be mounted at the domain root.** Passenger normally does this. Path routing keeps any outer `SCRIPT_NAME` intact.

### Accounts, roles and sessions
- **Built-in roles can't be edited.** Their permissions are computed from rules in `apps/accounts/roles.py` against the registered modules, so new modules are covered automatically. To vary one, duplicate it as a custom role.
- **Two-factor rule.** Two-factor login is required for platform staff and for anyone whose role in **any** of their organizations requires it (Owner, Admin, Finance, or a custom role with the flag).
- **When a new role suddenly needs 2FA** in the middle of a session, the user is sent to set it up rather than signed out. Their password was already checked for that session.
- **The set-up wizard is exempt from 2FA.** A brand-new owner sets 2FA up right after finishing, before entering the app.
- **Session limits use the strictest of the user's roles:**
  - the idle timeout (Owner, Admin and Finance: 60 minutes)
  - the longest sign-in (Owner, Admin and Finance: 10 hours)
- **Custom roles can't grant every action yet.** The permission matrix lists only modules whose app exists. Phase 1 has Dashboard and Settings; each later phase adds its modules to the matrix automatically.
- **Admins cannot grant or change the Owner role.** Only owners can, and the last active owner can't be demoted or disabled.

### Impersonation
- Platform staff "view as" an active member. The impersonation session:
  - lasts at most an hour
  - shows a red banner on every page
  - blocks password and 2FA changes
  - closes the platform admin until the impersonation is stopped
- Every audit entry made during it records the impersonator. Platform staff can't be impersonated.

### Onboarding
- **Phone verification needs a real SMS provider.** It is only offered when one is configured (`SMS_PROVIDER=africastalking`). With the mock, nobody is asked for a code that would never arrive.
- **The organization is created at step 1 of the wizard**, so the logo is stored in its own folder. Abandoning set-up deletes that empty organization.
- **Sample data is a flag in Phase 1.** "Load sample data?" sets `settings.sample_data_requested`, because Phase 1 has no business records. Loaders register in `apps.industries.sample` from Phase 2 and fill the flagged organizations.
- **Industry packs per organization are limited by the plan** (`Plan.max_industry_packs`).

### Design
- **Brand colours are adjusted for contrast.** Each organization's brand colour becomes CSS variables (`apps/core/branding.py`). When the colour is too light for white text (for example yellow), darker shades are used where text sits on it, keeping WCAG AA contrast. A test checks this for light, dark and saturated colours.
- **Pipeline stage colours are fixed for readability.** They come from a fixed, contrast-checked palette, and the pill uses the stage colour on a 14% tint of itself.
- **The platform's own default mark** is three stacked layers ("one platform, many businesses"). Replace `static/brand/logo-source.png` and run `generate_pwa_assets` once there is a real logo.
- **SortableJS 1.15.6 is vendored now** for the drag-and-drop screens in later phases (Kanban, itinerary builder, page builder).

### Not done in Phase 1 (scheduled)
- **Admin screens for custom fields and terminology overrides** come in Phase 2 with the CRM, together with module sample loaders. The engine and models exist now and are tested.
- **A "file" custom-field type** comes later, once attachments have an upload widget.
- **The public-image view for published website items** comes in Phase 5. So does self-service custom-domain verification by DNS TXT token.
- **The test suite has only run on SQLite.** MySQL and PostgreSQL are installed on the development machine, but no credentials were available. See PLAN.md.

### Industry packs in this build

All 19 packs have terminology, sub-niches, pipelines, custom fields, suggested modules, document-template names, dashboard widgets, reports, automation templates and checklist items. Only Tourism and Real Estate get their own deep module in this build (Phases 4 and 7). The other packs record what their deep module will add (`IndustryPack.planned`).

| Pack | Sub-niches | Custom fields | Stages | Deep module |
|---|---|---|---|---|
| Agriculture & Agribusiness | Farm, Agro-dealer, Processor or aggregator, Co-operative | 5 | 5 | planned: farmer registry, collections, weighbridge, input credit, traceability, M-PESA bulk payouts |
| Automotive | Garage, Car dealer, Spare parts, Car hire | 5 | 5 | planned: job cards, vehicle history, service reminders, dealer stock by VIN |
| Construction & Contractors | General contractor, Specialist trade, Interior fit-out, Civil works | 5 | 6 | planned: BoQ, valuations and certificates, retention, subcontractors, site diaries |
| Education & Training | School, College or TVET, Training provider, Tuition centre | 5 | 6 | planned: student records, timetables, fee statements, attendance, report cards |
| Events & Venues | Venue, Event planner, Wedding planner, Conference organiser | 4 | 6 | planned: ticketing, run sheets, vendors, seating plans |
| Fitness & Gyms | Gym, Studio, Personal training, Sports club | 4 | 6 | planned: memberships and renewals, class booking with capacity, check-in |
| Healthcare Clinics | General clinic, Dental, Physiotherapy, Eye clinic | 4 | 5 | planned: clinical records (confidential), SHA and insurer claims, dispensary, lab |
| Hospitality | Hotel, Lodge or camp, Guest house, Serviced apartments | 6 | 5 | planned: front desk / PMS, rate plans, housekeeping, folios, channel manager |
| Logistics & Transport | Freight forwarding, Courier, Haulage, Clearing agent | 5 | 5 | planned: shipments and waybills, fleet and fuel, driver trips, customs entries |
| Manufacturing | Food processing, Furniture, Textiles, Fabrication | 5 | 6 | planned: BOMs, work orders, MRP, quality checks, costing |
| NGOs & Non-profits | NGO, Foundation, Faith organisation, Community group | 5 | 5 | planned: donor receipts, grants budget-vs-actual, beneficiaries, M&E |
| Professional Services | Consulting, Law firm, Accounting, Agency | 5 | 6 | planned: time and billing, matters, retainers, client trust ledger |
| Real Estate | Agency, Developer, Property manager | 7 | 9 | **`apps/realestate`, Phase 7** |
| Restaurants & Cafés | Restaurant, Café, Bar, Catering | 5 | 5 | planned: POS with table plan, kitchen display, recipes and food cost, delivery |
| Retail & E-commerce | Shop, Mini-mart, Online store, Electronics | 5 | 5 | planned: POS with barcode and M-PESA till, online checkout, loyalty |
| Salons & Spas | Hair salon, Barbershop, Spa, Nails and beauty | 4 | 4 | planned: online booking against rota, POS, stylist commissions, loyalty |
| Tourism & Travel | Tour operator, Travel agency, Safari camp, DMC | 10 | 6 | **`apps/tourism`, Phase 4** |
| Wholesale & Distribution | Distributor, Importer, FMCG | 6 | 6 | planned: route sales and van stock, credit holds, price tiers, EDI |
| Generic / Other | General business | 0 | 6 | core modules only |

Healthcare deliberately collects no clinical data (allergies, notes) until its deep module provides confidential fields. This follows the Kenya Data Protection Act, which treats health data as sensitive.

## Name and colours (13 Oct 2026)

- **Name: Pamoja** ("together" in Swahili), with the tagline "Your whole business, together." Both are settings (`PRODUCT_NAME`, `PRODUCT_TAGLINE`). The domain is still a placeholder. Check that `pamoja.co.ke` (or similar) is available and that the name is clear of trademarks in Kenya before launch.
- **Platform colours: indigo.** The default is `BRAND_COLOUR=#4F46E5`, with a deep indigo sidebar (#1D1A4C) and a cool grey page.
- **Brand colour rules for every organization.** The sidebar is now always a deep shade of the brand colour, and button hover is a darker shade. All text on these colours keeps at least 4.5:1 contrast.
- **Demo organizations use the platform colour.** Real organizations still choose their own under Settings › Profile & branding.
