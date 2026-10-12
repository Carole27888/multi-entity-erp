from ..registry import IndustryPack, SubNiche, register
from ._common import BASE_AUTOS, CustomFieldDef as F, Term, autos, docs, pipeline

PACK = register(IndustryPack(
    key="nonprofit", name="NGOs & Non-profits", icon="heart",
    tagline="NGOs, foundations, faith organisations and community groups.",
    keywords=("ngo", "non-profit", "charity", "foundation", "church", "community", "cbo", "donors", "grants"),
    sub_niches=(
        SubNiche("ngo", "NGO"),
        SubNiche("foundation", "Foundation or trust"),
        SubNiche("faith", "Church or faith organisation", terminology={"customer": Term("Member")}),
        SubNiche("community", "Community-based organisation"),
    ),
    modules_default=("crm", "sales", "projects", "finance", "documents", "marketing"),
    modules_optional=("website", "hr", "reports", "calendar"),
    terminology={
        "lead": Term("Prospect"),
        "customer": Term("Donor"),
        "deal": Term("Pledge"),
        "pipeline": Term("Fundraising pipeline"),
        "product": Term("Programme"),
        "project": Term("Programme"),
        "order": Term("Donation"),
        "quote": Term("Funding proposal"),
    },
    pipelines=(pipeline("Fundraising pipeline", "Prospect", "Cultivation", "Proposal submitted",
                        won="Pledged", lost="Declined"),),
    custom_fields=(
        F("contact", "donor_type", "Donor type", "choice", ("Individual", "Corporate", "Foundation", "Government",
                                                            "Multilateral")),
        F("contact", "giving_interest", "Giving interest"),
        F("deal", "grant_ref", "Grant reference"),
        F("deal", "reporting_due", "Next report due", "date"),
        F("deal", "restricted", "Restricted funds", "bool"),
    ),
    document_templates=docs(("quote", "Funding proposal"), ("receipt", "Donation receipt"), ("invoice", "Invoice"),
                            ("contract", "Grant agreement")),
    dashboard_widgets=("pledges_open", "donations_this_month", "reports_due", "programme_spend"),
    reports=("donations_by_donor", "pledges_by_stage", "grant_reporting_calendar"),
    automation_templates=autos(*BASE_AUTOS, ("Thank donors", "payment.received", "Sends a thank-you and receipt."),
                               ("Grant report due", "deal.reporting_due", "Reminds the programme lead two weeks before.")),
    catalogue_kind="programmes",
    planned="Donor management with tax receipts, grants with budget-versus-actual, beneficiaries and M&E indicators.",
))
