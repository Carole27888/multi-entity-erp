from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="hospitality", name="Hospitality", icon="bed",
    tagline="Hotels, lodges, guest houses and serviced apartments.",
    keywords=("hotel", "lodge", "guest house", "airbnb", "rooms", "accommodation", "conference"),
    sub_niches=(
        SubNiche("hotel", "Hotel"),
        SubNiche("lodge_camp", "Lodge or camp"),
        SubNiche("guest_house", "Guest house or B&B"),
        SubNiche("serviced_apartments", "Serviced apartments"),
    ),
    modules_default=("crm", "sales", "catalog", "calendar", "finance", "documents", "website"),
    modules_optional=("inventory", "hr", "marketing", "reports", "portal", "helpdesk"),
    terminology={
        "lead": Term("Enquiry", "Enquiries"),
        "deal": Term("Reservation"),
        "pipeline": Term("Reservations pipeline"),
        "customer": Term("Guest"),
        "product": Term("Room or service", "Rooms and services"),
        "catalogue": Term("Rooms", "Rooms"),
        "order": Term("Reservation"),
        "resource": Term("Room"),
    },
    pipelines=(pipeline("Reservations pipeline", "Enquiry", "Quote sent", "Provisional", won="Confirmed", lost="Lost"),),
    custom_fields=(
        F("lead", "check_in", "Check-in", "date", section="Stay"),
        F("lead", "check_out", "Check-out", "date", section="Stay"),
        F("lead", "guests", "Guests", "number", section="Stay"),
        F("lead", "purpose", "Purpose", "choice", ("Leisure", "Business", "Conference", "Wedding", "Group"), section="Stay"),
        F("contact", "nationality", "Nationality", section="Profile"),
        F("contact", "loyalty_no", "Loyalty number", section="Profile"),
    ),
    document_templates=docs(*BASE_DOCS, ("confirmation", "Reservation confirmation"), ("contract", "Group booking contract")),
    dashboard_widgets=("arrivals_today", "departures_today", "new_enquiries", "occupancy_forecast"),
    reports=("reservations_by_month", "reservations_by_source", "conversion_funnel", "revenue_by_room_type"),
    automation_templates=autos(*BASE_AUTOS, ("Pre-arrival message", "reservation.arrival_soon",
                                            "Sends directions and check-in details two days before arrival.")),
    catalogue_kind="rooms",
    planned="Front desk and property management: room inventory and rate plans, check-in and check-out, "
            "housekeeping, folios and a channel manager.",
))
