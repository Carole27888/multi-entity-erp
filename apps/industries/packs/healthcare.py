from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

INSURERS = ("Cash", "SHA", "AAR", "Jubilee", "Britam", "CIC", "Madison", "APA", "Old Mutual", "Other")

PACK = register(IndustryPack(
    key="healthcare", name="Healthcare Clinics", icon="plus-square",
    tagline="Clinics, dental, physiotherapy and eye care.",
    keywords=("clinic", "hospital", "medical", "dental", "dentist", "physio", "optician", "doctor"),
    sub_niches=(
        SubNiche("general_clinic", "General clinic"),
        SubNiche("dental", "Dental clinic"),
        SubNiche("physiotherapy", "Physiotherapy"),
        SubNiche("eye_clinic", "Eye clinic or optician"),
    ),
    modules_default=("crm", "calendar", "sales", "catalog", "finance", "documents"),
    modules_optional=("portal", "inventory", "hr", "reports", "marketing", "website"),
    terminology={
        "contact": Term("Patient"),
        "customer": Term("Patient"),
        "lead": Term("Enquiry", "Enquiries"),
        "deal": Term("Treatment plan"),
        "pipeline": Term("Treatment plans"),
        "product": Term("Treatment"),
        "order": Term("Visit"),
        "catalogue": Term("Services", "Services"),
    },
    pipelines=(pipeline("Treatment plans", "Enquiry", "Consultation booked", "Plan proposed",
                        won="Accepted", lost="Declined"),),
    custom_fields=(
        F("contact", "date_of_birth", "Date of birth", "date", section="Patient"),
        F("contact", "gender", "Gender", "choice", ("Female", "Male", "Other", "Prefer not to say"), section="Patient"),
        F("contact", "insurer", "Insurer", "choice", INSURERS, section="Insurance"),
        F("contact", "member_no", "Member number", section="Insurance"),
    ),
    document_templates=docs(*BASE_DOCS, ("quote", "Treatment estimate"), ("contract", "Consent form")),
    dashboard_widgets=("appointments_today", "new_patients", "plans_open", "receivables"),
    reports=("appointments_by_day", "patients_by_insurer", "revenue_by_service"),
    automation_templates=autos(*BASE_AUTOS, ("Appointment reminder", "appointment.tomorrow",
                                            "Reminds the patient by SMS the day before.")),
    catalogue_kind="services",
    planned="Clinical records with confidential notes, SHA and insurer claims, dispensary stock and lab orders. "
            "Clinical data is not collected until that module (with sensitive-data protections) exists.",
))
