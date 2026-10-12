from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="professional_services", name="Professional Services", icon="briefcase",
    tagline="Consulting, legal, accounting and agencies.",
    keywords=("consultant", "consulting", "law firm", "advocates", "lawyer", "accountant", "audit", "agency"),
    sub_niches=(
        SubNiche("consulting", "Consulting"),
        SubNiche("legal", "Law firm", "Advocates and legal practices.",
                 terminology={"deal": Term("Matter"), "project": Term("Matter"), "quote": Term("Fee proposal")}),
        SubNiche("accounting", "Accounting and tax"),
        SubNiche("agency", "Marketing or creative agency"),
    ),
    modules_default=("crm", "sales", "projects", "finance", "documents", "calendar"),
    modules_optional=("helpdesk", "reports", "hr", "portal", "marketing"),
    terminology={
        "lead": Term("Enquiry", "Enquiries"),
        "deal": Term("Engagement"),
        "pipeline": Term("Engagements pipeline"),
        "customer": Term("Client"),
        "product": Term("Service"),
        "project": Term("Engagement"),
        "quote": Term("Proposal"),
    },
    pipelines=(pipeline("Engagements pipeline", "Enquiry", "Discovery call", "Proposal sent", "Negotiating",
                        won="Engagement letter signed", lost="Lost"),),
    custom_fields=(
        F("deal", "service_line", "Service line"),
        F("deal", "billing_model", "Billing", "choice", ("Fixed fee", "Hourly", "Monthly retainer", "Success fee")),
        F("deal", "conflict_checked", "Conflict check done", "bool"),
        F("company", "kra_pin", "KRA PIN"),
        F("company", "industry", "Client industry"),
    ),
    document_templates=docs(*BASE_DOCS, ("proposal", "Proposal"), ("contract", "Engagement letter")),
    dashboard_widgets=("proposals_open", "active_engagements", "unbilled_time", "receivables"),
    reports=("engagements_by_service", "win_rate", "utilisation", "aged_receivables"),
    automation_templates=autos(*BASE_AUTOS),
    catalogue_kind="services",
    planned="Time and billing, matter management with deadlines, retainers and a client trust ledger for law firms.",
))
