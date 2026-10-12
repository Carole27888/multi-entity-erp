"""Built-in roles. Their permissions are computed from these rules against every registered module, so a module
added later is covered without data changes. To vary a built-in role, duplicate it as a custom role.

A rule maps a module key (or "*" for every module) to the actions allowed: "*" means every action including the
module's extra (confidential) permissions; a set lists actions explicitly. A module-specific rule overrides "*".
"""

from dataclasses import dataclass, field

OWNER = "owner"
ADMIN = "admin"
MANAGER = "manager"
FINANCE = "finance"
SALES = "sales"
OPERATIONS = "operations"
STAFF = "staff"
READ_ONLY = "read_only"

STANDARD = {"view", "create", "edit", "delete", "approve", "export"}
WORK = {"view", "create", "edit"}
VIEW = {"view"}
NONE: set = set()


@dataclass(frozen=True)
class RoleTemplate:
    key: str
    name: str
    description: str
    rules: dict = field(default_factory=dict)
    two_factor_required: bool = False
    idle_timeout_minutes: int = 0
    session_max_hours: int = 0
    default_scope: str = "all"
    sort_order: int = 100


BUILTIN_ROLES: list[RoleTemplate] = [
    RoleTemplate(OWNER, "Owner", "Full access to everything, including billing and closing the account.",
                 {"*": "*"}, two_factor_required=True, idle_timeout_minutes=60, session_max_hours=10, sort_order=1),
    RoleTemplate(ADMIN, "Admin", "Full access to every module and setting.",
                 {"*": "*"}, two_factor_required=True, idle_timeout_minutes=60, session_max_hours=10, sort_order=2),
    RoleTemplate(MANAGER, "Manager", "Runs a team: sees their department's records, approves, exports. No settings.",
                 {"*": {"view", "create", "edit", "approve", "export"}, "settings": VIEW, "finance": {"view", "export"},
                  "hr": VIEW, "api": NONE}, default_scope="department", sort_order=3),
    RoleTemplate(FINANCE, "Finance", "Invoices, payments, bills, payroll and financial reports.",
                 {"*": NONE, "dashboard": VIEW, "finance": "*", "documents": STANDARD, "reports": {"view", "export"},
                  "crm": VIEW, "sales": {"view", "export"}, "catalog": VIEW, "hr": {"view", "view_salary"},
                  "tourism": {"view", "view_margin"}, "realestate": VIEW, "inventory": VIEW, "settings": VIEW},
                 two_factor_required=True, idle_timeout_minutes=60, session_max_hours=10, sort_order=4),
    RoleTemplate(SALES, "Sales", "Works their own contacts, pipeline and quotes.",
                 {"*": NONE, "dashboard": VIEW, "crm": WORK, "sales": WORK, "catalog": VIEW, "calendar": WORK,
                  "documents": {"view", "create"}, "tourism": WORK, "realestate": WORK, "reports": VIEW},
                 default_scope="own", sort_order=5),
    RoleTemplate(OPERATIONS, "Operations", "Delivers the work: operations, jobs, stock and the calendar.",
                 {"*": NONE, "dashboard": VIEW, "crm": VIEW, "sales": VIEW, "calendar": STANDARD, "tourism": STANDARD,
                  "realestate": WORK, "projects": STANDARD, "inventory": STANDARD, "helpdesk": STANDARD,
                  "documents": WORK, "catalog": VIEW, "reports": VIEW},
                 sort_order=6),
    RoleTemplate(STAFF, "Staff", "Day-to-day work on their own tasks, calendar and tickets.",
                 {"*": NONE, "dashboard": VIEW, "crm": {"view", "create"}, "calendar": WORK, "projects": WORK,
                  "helpdesk": WORK, "catalog": VIEW},
                 default_scope="own", sort_order=7),
    RoleTemplate(READ_ONLY, "Read-only", "Can open every module but change nothing (e.g. a director or auditor).",
                 {"*": VIEW, "api": NONE}, sort_order=8),
]
BUILTIN_BY_KEY = {r.key: r for r in BUILTIN_ROLES}
TWO_FACTOR_BUILTIN = {r.key for r in BUILTIN_ROLES if r.two_factor_required}


def builtin_permissions(key: str) -> dict[str, str]:
    """{permission: scope} for a built-in role, computed from the registered modules."""
    from apps.core.modules import all_modules

    template = BUILTIN_BY_KEY.get(key)
    if template is None:
        return {}
    out = {}
    for module in all_modules():
        rule = template.rules.get(module.key, template.rules.get("*", NONE))
        if rule == "*":
            allowed = set(module.actions) | set(module.extra_permissions)
        else:
            allowed = {a for a in rule if a in module.actions or a in module.extra_permissions}
        for action in allowed:
            out[f"{module.key}.{action}"] = template.default_scope
    return out
