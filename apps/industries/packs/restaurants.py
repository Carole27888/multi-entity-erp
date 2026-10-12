from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="restaurants", name="Restaurants & Cafés", icon="coffee",
    tagline="Restaurants, cafés, bars and caterers.",
    keywords=("restaurant", "cafe", "café", "bar", "catering", "food", "menu", "kitchen"),
    sub_niches=(
        SubNiche("restaurant", "Restaurant"),
        SubNiche("cafe", "Café or bakery"),
        SubNiche("bar_lounge", "Bar or lounge"),
        SubNiche("catering", "Catering", "Outside catering and events.", terminology={"deal": Term("Catering job")}),
    ),
    modules_default=("crm", "sales", "catalog", "inventory", "finance", "calendar", "website"),
    modules_optional=("hr", "marketing", "reports", "documents"),
    terminology={
        "lead": Term("Enquiry", "Enquiries"),
        "deal": Term("Event booking"),
        "pipeline": Term("Events pipeline"),
        "customer": Term("Guest"),
        "product": Term("Menu item"),
        "catalogue": Term("Menu", "Menus"),
        "order": Term("Order"),
    },
    pipelines=(pipeline("Events pipeline", "Enquiry", "Menu & quote sent", "Deposit paid", won="Confirmed", lost="Lost"),),
    custom_fields=(
        F("lead", "event_date", "Event date", "date", section="Event"),
        F("lead", "guests", "Guests", "number", section="Event"),
        F("lead", "occasion", "Occasion", "choice", ("Birthday", "Corporate", "Wedding", "Graduation", "Other"), section="Event"),
        F("product", "dietary", "Dietary tags", "multi", ("Vegetarian", "Vegan", "Halal", "Gluten-free", "Contains nuts")),
        F("product", "station", "Kitchen station", "choice", ("Grill", "Hot kitchen", "Cold kitchen", "Pastry", "Bar")),
    ),
    document_templates=docs(*BASE_DOCS, ("quote", "Event menu proposal")),
    dashboard_widgets=("orders_today", "events_this_week", "top_menu_items", "low_stock"),
    reports=("sales_by_item", "events_by_month", "stock_usage"),
    automation_templates=autos(*BASE_AUTOS),
    catalogue_kind="menu",
    planned="Point of sale with table plan and kitchen display, recipes with food-cost tracking and delivery orders.",
))
