from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="automotive", name="Automotive", icon="car",
    tagline="Garages, car dealers, spare parts and car hire.",
    keywords=("garage", "mechanic", "car dealer", "yard", "spare parts", "car hire", "auto", "vehicles"),
    sub_niches=(
        SubNiche("garage", "Garage or workshop", terminology={"deal": Term("Job"), "order": Term("Job card")}),
        SubNiche("dealership", "Car dealer", terminology={"deal": Term("Vehicle sale"), "product": Term("Vehicle")}),
        SubNiche("spare_parts", "Spare parts", terminology={"product": Term("Part")}),
        SubNiche("car_hire", "Car hire", terminology={"order": Term("Rental"), "resource": Term("Vehicle")}),
    ),
    modules_default=("crm", "sales", "calendar", "catalog", "inventory", "finance", "documents"),
    modules_optional=("hr", "reports", "marketing", "website", "helpdesk"),
    terminology={
        "lead": Term("Enquiry", "Enquiries"),
        "customer": Term("Customer"),
        "quote": Term("Estimate"),
    },
    pipelines=(pipeline("Jobs and sales", "Enquiry", "Inspection", "Estimate sent", won="Approved", lost="Lost"),),
    custom_fields=(
        F("contact", "vehicle_reg", "Vehicle registration", section="Vehicle", help="e.g. KDA 123B"),
        F("contact", "vehicle_model", "Make and model", section="Vehicle"),
        F("deal", "vehicle_reg", "Vehicle registration"),
        F("deal", "mileage", "Mileage (km)", "number"),
        F("product", "part_number", "Part number"),
    ),
    document_templates=docs(*BASE_DOCS, ("quote", "Repair estimate"), ("job_card", "Job card")),
    dashboard_widgets=("jobs_in_workshop", "estimates_open", "parts_low", "sales_this_month"),
    reports=("jobs_by_status", "revenue_by_service", "parts_usage"),
    automation_templates=autos(*BASE_AUTOS, ("Service reminder", "vehicle.service_due",
                                            "Reminds the customer when the next service is due.")),
    catalogue_kind="vehicles, parts and services",
    planned="Job cards with labour and parts, vehicle history, service reminders and dealer stock by VIN and logbook.",
))
