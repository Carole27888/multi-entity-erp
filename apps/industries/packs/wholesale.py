from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="wholesale", name="Wholesale & Distribution", icon="truck",
    tagline="Distributors, importers and FMCG wholesalers.",
    keywords=("distributor", "wholesaler", "importer", "fmcg", "stockist", "dealer"),
    sub_niches=(
        SubNiche("distributor", "Distributor"),
        SubNiche("importer", "Importer"),
        SubNiche("fmcg", "FMCG wholesaler"),
    ),
    modules_default=("crm", "sales", "catalog", "inventory", "finance", "reports"),
    modules_optional=("documents", "marketing", "hr", "portal", "partners", "website"),
    terminology={
        "company": Term("Account"),
        "deal": Term("Opportunity", "Opportunities"),
        "order": Term("Sales order"),
        "partner": Term("Sales rep"),
    },
    pipelines=(pipeline("New accounts", "Prospect", "Samples or quote sent", "Negotiating", "Trial order",
                        won="Won", lost="Lost"),),
    custom_fields=(
        F("company", "credit_limit", "Credit limit", "money", section="Credit"),
        F("company", "payment_terms", "Payment terms", "choice", ("Cash", "7 days", "14 days", "30 days", "60 days"),
          section="Credit"),
        F("company", "route", "Delivery route", section="Delivery"),
        F("company", "kra_pin", "KRA PIN", section="Tax"),
        F("product", "pack_size", "Pack size", help="e.g. 24 × 500 ml"),
        F("product", "moq", "Minimum order quantity", "number"),
    ),
    document_templates=docs(*BASE_DOCS, ("delivery_note", "Delivery note"), ("statement", "Customer statement")),
    dashboard_widgets=("orders_today", "overdue_accounts", "top_accounts", "low_stock"),
    reports=("sales_by_account", "sales_by_route", "aged_receivables", "stock_valuation"),
    automation_templates=autos(*BASE_AUTOS, ("Over credit limit", "invoice.created",
                                            "Alerts the credit controller when an account goes over its limit.")),
    catalogue_kind="products",
    planned="Route sales with van stock, credit control holds, price tiers per customer group and supplier EDI.",
))
