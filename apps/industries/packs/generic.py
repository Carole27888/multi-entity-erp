from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, autos, docs, pipeline

PACK = register(IndustryPack(
    key="generic", name="Generic / Other", icon="grid",
    tagline="Any other business: start with the core and switch on what you need.",
    keywords=("other", "general", "business", "company", "services"),
    sub_niches=(SubNiche("general", "General business"),),
    modules_default=("crm", "sales", "catalog", "calendar", "finance", "documents"),
    modules_optional=("inventory", "projects", "helpdesk", "hr", "marketing", "reports", "website", "portal"),
    pipelines=(pipeline("Sales pipeline", "New", "Qualified", "Proposal", "Negotiation", won="Won", lost="Lost"),),
    document_templates=docs(*BASE_DOCS),
    dashboard_widgets=("new_leads", "deals_open", "receivables", "tasks_due"),
    reports=("pipeline_by_stage", "sales_by_month", "aged_receivables"),
    automation_templates=autos(*BASE_AUTOS),
    catalogue_kind="products and services",
))
