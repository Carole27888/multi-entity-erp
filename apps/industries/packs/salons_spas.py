from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="salons_spas", name="Salons & Spas", icon="scissors",
    tagline="Hair salons, barbers, spas and beauty studios.",
    keywords=("salon", "barber", "barbershop", "spa", "beauty", "nails", "massage", "hair"),
    sub_niches=(
        SubNiche("hair_salon", "Hair salon"),
        SubNiche("barber", "Barbershop"),
        SubNiche("spa", "Spa and massage"),
        SubNiche("nails_beauty", "Nails and beauty"),
    ),
    modules_default=("crm", "calendar", "catalog", "sales", "finance", "marketing"),
    modules_optional=("inventory", "hr", "website", "reports"),
    terminology={
        "lead": Term("Enquiry", "Enquiries"),
        "deal": Term("Package sale"),
        "customer": Term("Client"),
        "product": Term("Service"),
        "catalogue": Term("Services", "Services"),
        "order": Term("Visit"),
        "staff": Term("Stylist"),
    },
    pipelines=(pipeline("Packages and bridal", "Enquiry", "Consultation", won="Booked", lost="Lost"),),
    custom_fields=(
        F("contact", "preferred_stylist", "Preferred stylist", section="Preferences"),
        F("contact", "hair_skin_type", "Hair or skin type", section="Preferences"),
        F("contact", "birthday", "Birthday", "date", section="Loyalty"),
        F("product", "duration_minutes", "Duration (minutes)", "number"),
    ),
    document_templates=docs(*BASE_DOCS),
    dashboard_widgets=("appointments_today", "top_services", "repeat_clients", "sales_today"),
    reports=("sales_by_service", "sales_by_stylist", "client_retention"),
    automation_templates=autos(*BASE_AUTOS, ("Appointment reminder", "appointment.tomorrow", "SMS the day before."),
                               ("We miss you", "contact.inactive_60d", "Offer to clients who haven't visited in 60 days.")),
    catalogue_kind="services",
    planned="Online booking against the staff rota, point of sale, stylist commissions and loyalty points.",
))
