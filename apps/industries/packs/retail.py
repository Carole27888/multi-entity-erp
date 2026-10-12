from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="retail", name="Retail & E-commerce", icon="shopping-bag",
    tagline="Shops, mini-marts, boutiques and online stores.",
    keywords=("shop", "store", "boutique", "supermarket", "minimart", "ecommerce", "online store", "electronics"),
    sub_niches=(
        SubNiche("shop", "Shop or boutique"),
        SubNiche("minimart", "Supermarket or mini-mart"),
        SubNiche("online_store", "Online store"),
        SubNiche("electronics", "Electronics and phones"),
    ),
    modules_default=("crm", "sales", "catalog", "inventory", "finance", "website"),
    modules_optional=("marketing", "reports", "hr", "helpdesk", "portal"),
    terminology={
        "deal": Term("Opportunity", "Opportunities"),
        "order": Term("Sale"),
        "catalogue": Term("Products", "Products"),
    },
    pipelines=(pipeline("Bulk and corporate orders", "New", "Quoted", "Negotiating", won="Won", lost="Lost"),),
    custom_fields=(
        F("product", "brand", "Brand"),
        F("product", "size", "Size"),
        F("product", "colour", "Colour"),
        F("contact", "loyalty_no", "Loyalty number", section="Loyalty"),
        F("contact", "birthday", "Birthday", "date", section="Loyalty"),
    ),
    document_templates=docs(*BASE_DOCS, ("delivery_note", "Delivery note")),
    dashboard_widgets=("sales_today", "top_products", "low_stock", "new_customers"),
    reports=("sales_by_product", "sales_by_day", "stock_valuation", "reorder_list"),
    automation_templates=autos(*BASE_AUTOS, ("Birthday offer", "contact.birthday", "Sends a birthday discount by SMS.")),
    catalogue_kind="products",
    planned="Point of sale with barcode scanning and M-PESA till, online store checkout, loyalty points and promotions.",
))
