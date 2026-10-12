from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="events", name="Events & Venues", icon="ticket",
    tagline="Venues, event planners, wedding planners and conference organisers.",
    keywords=("events", "venue", "wedding", "conference", "party", "planner", "hall", "tents"),
    sub_niches=(
        SubNiche("venue", "Venue", terminology={"resource": Term("Space")}),
        SubNiche("event_planner", "Event planner"),
        SubNiche("wedding_planner", "Wedding planner"),
        SubNiche("conference_organiser", "Conference organiser"),
    ),
    modules_default=("crm", "sales", "calendar", "catalog", "finance", "documents"),
    modules_optional=("website", "portal", "projects", "inventory", "hr", "reports", "marketing"),
    terminology={
        "lead": Term("Enquiry", "Enquiries"),
        "deal": Term("Event"),
        "pipeline": Term("Events pipeline"),
        "customer": Term("Client"),
        "product": Term("Package"),
        "order": Term("Event booking"),
        "resource": Term("Venue space"),
    },
    pipelines=(pipeline("Events pipeline", "Enquiry", "Site visit", "Proposal sent", "Deposit paid",
                        won="Confirmed", lost="Lost"),),
    custom_fields=(
        F("deal", "event_date", "Event date", "date"),
        F("deal", "guest_count", "Guests", "number"),
        F("deal", "event_type", "Event type", "choice", ("Wedding", "Corporate", "Birthday", "Conference", "Launch", "Other")),
        F("deal", "venue_space", "Venue or space"),
    ),
    document_templates=docs(*BASE_DOCS, ("proposal", "Event proposal"), ("contract", "Event contract")),
    dashboard_widgets=("events_this_week", "enquiries_open", "deposits_due", "space_utilisation"),
    reports=("events_by_month", "events_by_type", "conversion_funnel", "revenue_by_package"),
    automation_templates=autos(*BASE_AUTOS, ("Final details check", "event.in_14_days",
                                            "Asks the client to confirm numbers two weeks before.")),
    catalogue_kind="packages and spaces",
    planned="Ticketing, run sheets, vendor management and seating plans.",
))
