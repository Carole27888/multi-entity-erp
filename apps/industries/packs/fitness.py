from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="fitness", name="Fitness & Gyms", icon="dumbbell",
    tagline="Gyms, studios, personal trainers and sports clubs.",
    keywords=("gym", "fitness", "yoga", "pilates", "crossfit", "trainer", "sports club", "studio"),
    sub_niches=(
        SubNiche("gym", "Gym"),
        SubNiche("studio", "Yoga, pilates or dance studio"),
        SubNiche("personal_training", "Personal training"),
        SubNiche("sports_club", "Sports club"),
    ),
    modules_default=("crm", "sales", "calendar", "catalog", "finance", "marketing"),
    modules_optional=("website", "portal", "hr", "reports", "inventory"),
    terminology={
        "lead": Term("Prospect"),
        "deal": Term("Membership sale"),
        "customer": Term("Member"),
        "product": Term("Membership plan"),
        "catalogue": Term("Plans and classes", "Plans and classes"),
        "appointment": Term("Class session"),
        "staff": Term("Trainer"),
    },
    pipelines=(pipeline("Membership sales", "Enquiry", "Trial booked", "Trial done", "Offer made",
                        won="Joined", lost="Lost"),),
    custom_fields=(
        F("lead", "trial_date", "Trial date", "date"),
        F("contact", "goal", "Fitness goal", "choice", ("Weight loss", "Strength", "Endurance", "Flexibility", "Rehab")),
        F("contact", "emergency_contact", "Emergency contact"),
        F("contact", "member_no", "Membership number"),
    ),
    document_templates=docs(*BASE_DOCS, ("contract", "Membership agreement")),
    dashboard_widgets=("active_members", "trials_this_week", "renewals_due", "classes_today"),
    reports=("members_by_plan", "trial_conversion", "renewals_and_churn"),
    automation_templates=autos(*BASE_AUTOS, ("Renewal reminder", "membership.expiring", "Reminds members a week before expiry.")),
    catalogue_kind="plans and classes",
    planned="Memberships with renewals and freezes, class booking with capacity, check-in and access control.",
))
