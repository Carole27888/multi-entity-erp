"""Module registry: drives the sidebar, the main menu tiles and the phone bottom bar.

Each app registers its own Module in its AppConfig.ready():

    from apps.core.modules import Module, NavItem, register

    register(Module("crm", "CRM", "users", "Contacts, leads and the pipeline.", "crm:home", ("crm",),
                    nav=[NavItem(term="lead", plural=True, url_name="crm:lead_list", icon="user-plus")]))

A module shows for an organization when (1) it is in Organization.enabled_modules (core modules always are),
(2) the user's role can view it, and (3) its home URL can be reversed (so the menu never links to a page that is
not built yet). Labels can be terminology keys, so "Leads" reads "Enquiries" for a tour operator.

CATALOGUE lists every planned module (name, icon, description) so onboarding and Settings can offer modules
that industry packs switch on before their app exists; they appear in the menu once their app ships.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.urls import NoReverseMatch, reverse

ACTIONS = ("view", "create", "edit", "delete", "approve", "export")


@dataclass
class NavItem:
    label: str = ""
    url_name: str = ""
    icon: str = ""
    term: str = ""  # terminology key; replaces label (e.g. "lead" → "Enquiries" with plural=True)
    plural: bool = False
    badge: str = ""
    section: str = ""
    permission: str = ""  # e.g. "settings.edit"; empty = anyone who can view the module
    match: tuple = ()

    def display_label(self, org=None) -> str:
        if self.term:
            from apps.industries.terms import term

            return term(self.term, org=org, plural=self.plural)
        return self.label

    @property
    def url(self) -> str | None:
        if not self.url_name:
            return None
        try:
            return reverse(self.url_name)
        except NoReverseMatch:
            return None


@dataclass
class Module:
    key: str
    name: str
    icon: str
    description: str
    home_url_name: str = ""
    namespaces: tuple[str, ...] = ()
    nav: list[NavItem] = field(default_factory=list)
    bottom_nav: list[NavItem] = field(default_factory=list)
    core: bool = False  # always enabled (dashboard, settings)
    actions: tuple[str, ...] = ACTIONS
    extra_permissions: dict[str, str] = field(default_factory=dict)  # "view_margin": "See cost and margin"
    plan_feature: str = ""  # Plan feature flag needed (e.g. "customer_portal")
    requires: tuple[str, ...] = ()
    order: int = 100
    term: str = ""  # optional terminology key for the module name

    def display_name(self, org=None) -> str:
        if self.term:
            from apps.industries.terms import term

            return term(self.term, org=org, plural=True)
        return self.name

    @property
    def home_url(self) -> str | None:
        if not self.home_url_name:
            return None
        try:
            return reverse(self.home_url_name)
        except NoReverseMatch:
            return None

    @property
    def is_available(self) -> bool:
        return self.home_url is not None

    def permission_keys(self) -> list[str]:
        return [f"{self.key}.{a}" for a in self.actions] + [f"{self.key}.{p}" for p in self.extra_permissions]


@dataclass(frozen=True)
class CatalogueEntry:
    """A planned module, known before its app ships (used by packs, onboarding and Settings)."""

    key: str
    name: str
    icon: str
    description: str
    core: bool = False
    plan_feature: str = ""


CATALOGUE: dict[str, CatalogueEntry] = {e.key: e for e in [
    CatalogueEntry("dashboard", "Dashboard", "grid", "Your day at a glance, with the getting-started checklist.", core=True),
    CatalogueEntry("settings", "Settings", "settings", "Organization profile, branding, team, roles and modules.", core=True),
    CatalogueEntry("crm", "CRM", "users", "Contacts, companies, leads, the pipeline, activities and tasks."),
    CatalogueEntry("sales", "Sales", "trending-up", "Quotes with an online accept link, orders, discounts, commissions and targets."),
    CatalogueEntry("catalog", "Products & services", "tag", "Your catalogue with variants and price lists."),
    CatalogueEntry("calendar", "Calendar", "calendar", "Shared calendars, resource booking and public appointment slots."),
    CatalogueEntry("finance", "Finance", "wallet", "Invoices, receipts, M-PESA, bills, expenses, bank reconciliation and statements."),
    CatalogueEntry("documents", "Documents & e-signature", "file-text", "Templates with merge fields, PDFs and signing by one-time code."),
    CatalogueEntry("inventory", "Inventory", "box", "Items, warehouses, stock moves, reorder levels, serials and batches."),
    CatalogueEntry("projects", "Projects", "columns", "Projects, milestones, tasks, time tracking and a Kanban board."),
    CatalogueEntry("helpdesk", "Helpdesk", "inbox", "Support tickets from the portal, email and WhatsApp, with SLAs."),
    CatalogueEntry("hr", "HR & payroll", "briefcase", "Employees, leave, attendance, expense claims and Kenyan payroll."),
    CatalogueEntry("marketing", "Marketing", "megaphone", "Campaigns, tracked links, social inbox, broadcasts and automation."),
    CatalogueEntry("reports", "Reports", "bar-chart", "Reports, exports, scheduled delivery and a report builder."),
    CatalogueEntry("website", "Website", "globe", "Your public website, catalogue and online enquiry or booking forms."),
    CatalogueEntry("portal", "Customer portal", "user-check", "Customers see bookings, documents and invoices, and pay online.",
                   plan_feature="customer_portal"),
    CatalogueEntry("partners", "Partner portal", "share", "Agents and partners see net rates, book for clients and track commission.",
                   plan_feature="partner_portal"),
    CatalogueEntry("api", "API & webhooks", "link", "Connect other systems with the REST API and outgoing webhooks.",
                   plan_feature="api"),
    CatalogueEntry("tourism", "Tours & travel", "plane", "Destinations, rate sheets, the itinerary builder, vouchers and trip operations."),
    CatalogueEntry("realestate", "Real estate", "home", "Properties, viewings, offers, deals, rentals and off-plan developments."),
]}

_REGISTRY: dict[str, Module] = {}


def register(module: Module) -> Module:
    if module.key not in CATALOGUE:
        raise KeyError(f"Module '{module.key}' is not in apps.core.modules.CATALOGUE")
    _REGISTRY[module.key] = module
    return module


def get(key: str) -> Module | None:
    return _REGISTRY.get(key)


def all_modules() -> list[Module]:
    return sorted(_REGISTRY.values(), key=lambda m: (m.order, m.name))


def all_permission_keys() -> list[tuple[str, str]]:
    """(key, label) for every registered permission — used by the custom-role matrix."""
    out = []
    for module in all_modules():
        out += [(f"{module.key}.{a}", f"{module.name}: {a}") for a in module.actions]
        out += [(f"{module.key}.{p}", f"{module.name}: {label}") for p, label in module.extra_permissions.items()]
    return out


def is_enabled_for(org, key: str) -> bool:
    entry = CATALOGUE.get(key)
    if entry is None:
        return False
    if entry.core:
        return True
    return key in (org.enabled_modules or [])


def modules_for(user, org, perms=None) -> list[Module]:
    """Modules enabled for `org`, allowed by its plan, and viewable by the user's role there."""
    if org is None:
        return []
    out = []
    for module in all_modules():
        if not is_enabled_for(org, module.key):
            continue
        if module.plan_feature and not org.has_feature(module.plan_feature):
            continue
        if perms is not None and not perms.has(f"{module.key}.view"):
            continue
        out.append(module)
    return out


def module_for_namespace(namespace: str) -> Module | None:
    for module in _REGISTRY.values():
        if namespace in module.namespaces:
            return module
    return None


def visible_nav(items, org=None, perms=None, current: str = "") -> list[dict]:
    result = []
    for item in items:
        if item.permission and perms is not None and not perms.has(item.permission):
            continue
        url = item.url
        if url:
            result.append({"label": item.display_label(org), "url": url, "icon": item.icon, "badge": item.badge,
                           "section": item.section, "url_name": item.url_name, "match": item.match,
                           "active": current == item.url_name or current in item.match})
    return result
