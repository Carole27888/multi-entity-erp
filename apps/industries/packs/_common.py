"""Shared building blocks for pack definitions."""

from django.utils.text import slugify

from ..registry import AutomationDef, ChecklistItem, CustomFieldDef, DocTemplateDef, PipelineDef, Stage, Term

# Open-stage colours in order, then won and lost (all readable as pills on white, checked for contrast).
OPEN_COLOURS = ["#475569", "#1D4ED8", "#7C3AED", "#92400E", "#0F766E", "#BE185D", "#4338CA"]
WON = "#166534"
LOST = "#B91C1C"


def stages(*open_names: str, won: str = "Won", lost: str = "Lost") -> tuple:
    out = []
    count = len(open_names)
    for i, name in enumerate(open_names):
        prob = round(10 + (i * 80 / max(count - 1, 1))) if count > 1 else 50
        out.append(Stage(slugify(name)[:40], name, OPEN_COLOURS[i % len(OPEN_COLOURS)], probability=prob))
    out.append(Stage(slugify(won)[:40], won, WON, probability=100, is_won=True))
    out.append(Stage(slugify(lost)[:40], lost, LOST, probability=0, is_lost=True))
    return tuple(out)


def pipeline(name: str, *open_names: str, won: str = "Won", lost: str = "Lost", key: str = "main", entity: str = "deal"):
    return PipelineDef(key, name, entity, stages(*open_names, won=won, lost=lost))


def docs(*pairs) -> tuple:
    """docs(("quote", "Quotation"), ("invoice", "Tax invoice"))"""
    return tuple(DocTemplateDef(kind, slugify(name), name) for kind, name in pairs)


def autos(*triples) -> tuple:
    return tuple(AutomationDef(slugify(name), name, trigger, desc) for name, trigger, desc in triples)


# Common document set most packs start with (they add their own).
BASE_DOCS = (("quote", "Quotation"), ("invoice", "Tax invoice"), ("receipt", "Receipt"))

# Automations useful in every industry.
BASE_AUTOS = (
    ("Reply to new website enquiries", "lead.created", "Sends a thank-you message and assigns the enquiry."),
    ("Chase quotes with no reply", "quote.sent", "Reminds the owner three days after a quote is sent without a response."),
    ("Invoice due reminder", "invoice.due_soon", "Reminds the customer three days before an invoice falls due."),
)

__all__ = ["AutomationDef", "ChecklistItem", "CustomFieldDef", "DocTemplateDef", "PipelineDef", "Stage", "Term",
           "stages", "pipeline", "docs", "autos", "BASE_DOCS", "BASE_AUTOS"]
