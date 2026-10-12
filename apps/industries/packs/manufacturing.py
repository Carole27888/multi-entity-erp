from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="manufacturing", name="Manufacturing", icon="factory",
    tagline="Food processing, furniture, textiles and fabrication.",
    keywords=("factory", "production", "processing", "fabrication", "furniture", "textiles", "bakery"),
    sub_niches=(
        SubNiche("food_processing", "Food and beverage processing"),
        SubNiche("furniture", "Furniture and joinery"),
        SubNiche("textiles", "Textiles and garments"),
        SubNiche("fabrication", "Metal fabrication"),
    ),
    modules_default=("crm", "sales", "catalog", "inventory", "projects", "finance"),
    modules_optional=("documents", "reports", "hr", "helpdesk", "portal"),
    terminology={
        "deal": Term("Opportunity", "Opportunities"),
        "order": Term("Sales order"),
        "project": Term("Production order"),
    },
    pipelines=(pipeline("Orders pipeline", "Enquiry", "Specification", "Quotation", "Sample approved",
                        won="Won", lost="Lost"),),
    custom_fields=(
        F("deal", "required_by", "Required by", "date"),
        F("deal", "quantity", "Quantity", "number"),
        F("deal", "specification", "Specification", "textarea"),
        F("product", "uom", "Unit of measure", "choice", ("Piece", "kg", "Litre", "Metre", "Set", "Carton")),
        F("product", "lead_time_days", "Lead time (days)", "number"),
    ),
    document_templates=docs(*BASE_DOCS, ("delivery_note", "Delivery note"), ("job_card", "Production job card")),
    dashboard_widgets=("orders_in_production", "due_this_week", "low_raw_materials", "new_enquiries"),
    reports=("orders_by_status", "on_time_delivery", "stock_valuation", "sales_by_product"),
    automation_templates=autos(*BASE_AUTOS),
    catalogue_kind="products",
    planned="Bills of materials, work orders with routing, material planning (MRP), quality checks and costing.",
))
