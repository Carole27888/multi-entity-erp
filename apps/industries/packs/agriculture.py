from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="agriculture", name="Agriculture & Agribusiness", icon="leaf",
    tagline="Farms, agro-dealers, processors, aggregators and co-operatives.",
    keywords=("farm", "agribusiness", "agro-dealer", "dairy", "tea", "coffee", "avocado", "horticulture", "cooperative"),
    sub_niches=(
        SubNiche("farm", "Farm"),
        SubNiche("agro_dealer", "Agro-dealer"),
        SubNiche("aggregator", "Processor or aggregator", terminology={"supplier": Term("Farmer")}),
        SubNiche("cooperative", "Co-operative", terminology={"contact": Term("Member"), "supplier": Term("Member")}),
    ),
    modules_default=("crm", "sales", "catalog", "inventory", "finance"),
    modules_optional=("documents", "reports", "hr", "projects", "marketing"),
    terminology={
        "customer": Term("Buyer"),
        "deal": Term("Supply contract"),
        "product": Term("Produce", "Produce"),
        "catalogue": Term("Produce", "Produce"),
    },
    pipelines=(pipeline("Buyers pipeline", "Lead", "Sample or quote", "Negotiating", won="Contracted", lost="Lost"),),
    custom_fields=(
        F("contact", "county", "County", section="Farm"),
        F("contact", "farm_size_acres", "Farm size (acres)", "number", section="Farm"),
        F("contact", "crops", "Produce", "multi", ("Maize", "Tea", "Coffee", "Avocado", "Dairy", "Horticulture",
                                                  "Poultry", "Macadamia"), section="Farm"),
        F("product", "grade", "Grade"),
        F("product", "unit", "Unit", "choice", ("kg", "90 kg bag", "Tonne", "Litre", "Crate")),
    ),
    document_templates=docs(*BASE_DOCS, ("delivery_note", "Delivery note"), ("contract", "Supply contract")),
    dashboard_widgets=("deliveries_this_week", "stock_on_hand", "buyers_open", "receivables"),
    reports=("sales_by_produce", "sales_by_buyer", "stock_movement"),
    automation_templates=autos(*BASE_AUTOS),
    catalogue_kind="produce",
    planned="Farmer registry and produce collections, weighbridge capture, input credit, traceability and "
            "M-PESA bulk payouts to farmers.",
))
