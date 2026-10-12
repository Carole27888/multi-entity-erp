from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="construction", name="Construction & Contractors", icon="hard-hat",
    tagline="Builders, specialist trades, fit-out and civil works.",
    keywords=("contractor", "builder", "construction", "electrical", "plumbing", "fit-out", "civil", "renovation"),
    sub_niches=(
        SubNiche("general_contractor", "General contractor"),
        SubNiche("specialist_trade", "Specialist trade", "Electrical, plumbing, HVAC, solar."),
        SubNiche("interior_fitout", "Interior fit-out"),
        SubNiche("civil_works", "Civil works"),
    ),
    modules_default=("crm", "sales", "projects", "finance", "documents", "calendar", "inventory"),
    modules_optional=("hr", "reports", "helpdesk", "portal"),
    terminology={
        "lead": Term("Enquiry", "Enquiries"),
        "deal": Term("Job"),
        "pipeline": Term("Jobs pipeline"),
        "customer": Term("Client"),
        "quote": Term("Estimate"),
        "project": Term("Site project"),
    },
    pipelines=(pipeline("Jobs pipeline", "Enquiry", "Site visit", "Estimate sent", "Negotiating",
                        won="Contract signed", lost="Lost"),),
    custom_fields=(
        F("deal", "site_location", "Site location"),
        F("deal", "project_type", "Project type", "choice", ("Residential", "Commercial", "Industrial", "Infrastructure")),
        F("deal", "start_date", "Planned start", "date"),
        F("deal", "duration_weeks", "Duration (weeks)", "number"),
        F("company", "nca_category", "NCA category", "choice", ("NCA 1", "NCA 2", "NCA 3", "NCA 4", "NCA 5", "NCA 6",
                                                                 "NCA 7", "NCA 8"), help="For subcontractors."),
    ),
    document_templates=docs(*BASE_DOCS, ("quote", "Estimate"), ("contract", "Works contract"), ("job_card", "Site job card")),
    dashboard_widgets=("active_sites", "estimates_open", "jobs_won_this_month", "payments_due"),
    reports=("jobs_by_status", "estimate_win_rate", "project_profitability", "aged_receivables"),
    automation_templates=autos(*BASE_AUTOS),
    catalogue_kind="services",
    planned="Bills of quantities, progress valuations and payment certificates, retention, subcontractors, "
            "site diaries and equipment hire.",
))
