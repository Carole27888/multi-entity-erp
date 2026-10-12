from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="logistics", name="Logistics & Transport", icon="truck",
    tagline="Freight forwarders, couriers, hauliers and clearing agents.",
    keywords=("logistics", "freight", "courier", "transport", "haulage", "clearing", "forwarding", "trucks"),
    sub_niches=(
        SubNiche("freight_forwarding", "Freight forwarding"),
        SubNiche("courier", "Courier and last-mile delivery"),
        SubNiche("haulage", "Transport and haulage"),
        SubNiche("clearing", "Clearing and forwarding agent"),
    ),
    modules_default=("crm", "sales", "calendar", "finance", "documents"),
    modules_optional=("projects", "helpdesk", "hr", "reports", "portal", "inventory"),
    terminology={
        "lead": Term("Enquiry", "Enquiries"),
        "deal": Term("Shipment opportunity", "Shipment opportunities"),
        "order": Term("Shipment"),
        "quote": Term("Rate quote"),
        "product": Term("Service"),
        "resource": Term("Vehicle"),
    },
    pipelines=(pipeline("Shipments pipeline", "Rate request", "Quote sent", "Negotiating", won="Booked", lost="Lost"),),
    custom_fields=(
        F("deal", "origin", "Origin"),
        F("deal", "destination", "Destination"),
        F("deal", "cargo_type", "Cargo", "choice", ("General", "Perishable", "Hazardous", "20ft container",
                                                   "40ft container", "Parcel")),
        F("deal", "weight_kg", "Weight (kg)", "number"),
        F("deal", "incoterm", "Incoterm", "choice", ("EXW", "FOB", "CIF", "DAP", "DDP")),
    ),
    document_templates=docs(*BASE_DOCS, ("quote", "Rate quote"), ("delivery_note", "Proof of delivery")),
    dashboard_widgets=("shipments_in_transit", "quotes_open", "deliveries_today", "receivables"),
    reports=("shipments_by_lane", "quote_win_rate", "revenue_by_customer"),
    automation_templates=autos(*BASE_AUTOS),
    catalogue_kind="services",
    planned="Shipments and waybills with tracking, fleet and fuel, driver trips and customs entries.",
))
