from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, BASE_DOCS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="education", name="Education & Training", icon="book",
    tagline="Schools, colleges, training providers and tuition centres.",
    keywords=("school", "college", "tvet", "university", "training", "academy", "courses", "tuition"),
    sub_niches=(
        SubNiche("school", "School"),
        SubNiche("college", "College or TVET"),
        SubNiche("training_provider", "Training provider"),
        SubNiche("tuition", "Tuition centre"),
    ),
    modules_default=("crm", "sales", "catalog", "calendar", "finance", "website"),
    modules_optional=("portal", "documents", "hr", "reports", "marketing", "helpdesk"),
    terminology={
        "lead": Term("Enquiry", "Enquiries"),
        "deal": Term("Admission"),
        "pipeline": Term("Admissions pipeline"),
        "customer": Term("Student"),
        "product": Term("Course"),
        "catalogue": Term("Courses", "Courses"),
        "order": Term("Enrolment"),
        "appointment": Term("Class"),
    },
    pipelines=(pipeline("Admissions pipeline", "Enquiry", "Application received", "Assessment", "Offer made",
                        won="Enrolled", lost="Lost"),),
    custom_fields=(
        F("lead", "programme", "Programme of interest"),
        F("lead", "intake", "Intake", "choice", ("January", "May", "September")),
        F("lead", "level", "Level", "choice", ("Certificate", "Diploma", "Degree", "Short course", "Primary", "Secondary")),
        F("contact", "guardian_name", "Parent or guardian", section="Guardian"),
        F("contact", "guardian_phone", "Guardian phone", "phone", section="Guardian"),
    ),
    document_templates=docs(*BASE_DOCS, ("contract", "Admission letter"), ("statement", "Fee statement")),
    dashboard_widgets=("applications_this_intake", "enrolled", "fees_outstanding", "classes_today"),
    reports=("applications_by_programme", "admissions_funnel", "fees_collected", "fee_balances"),
    automation_templates=autos(*BASE_AUTOS, ("Fee reminder", "invoice.due_soon", "Reminds the guardian before fees are due.")),
    catalogue_kind="courses",
    planned="Student records, timetables, fee structures with statements, attendance and report cards.",
))
