"""Industry pack registry, applying packs, terminology and custom fields."""

import pytest
from django.template import Context, Template

from apps.core.modules import CATALOGUE
from apps.industries import registry
from apps.industries.customfields import CustomFieldsFormMixin
from apps.industries.models import AppliedPack, CustomField, Pipeline, PipelineStage, TerminologyOverride
from apps.industries.services import PackLimitError, apply_pack
from apps.industries.terms import term
from apps.tenancy.context import tenant
from tests.factories import make_org

EXPECTED = {"tourism", "real_estate", "hospitality", "restaurants", "retail", "wholesale", "manufacturing",
            "construction", "professional_services", "healthcare", "education", "salons_spas", "fitness", "events",
            "logistics", "automotive", "agriculture", "nonprofit", "generic"}


def test_all_19_industries_are_registered():
    assert {p.key for p in registry.all_packs()} == EXPECTED
    assert registry.all_packs()[-1].key == "generic"


@pytest.mark.parametrize("pack", registry.all_packs(), ids=lambda p: p.key)
def test_pack_is_complete_and_consistent(pack):
    assert pack.name and pack.icon and pack.tagline and pack.sub_niches
    for key in (*pack.modules_default, *pack.modules_optional):
        assert key in CATALOGUE, f"{pack.key}: unknown module {key}"
    for sn in pack.sub_niches:
        for key in sn.modules_default:
            assert key in CATALOGUE
    assert pack.pipelines, "every pack defines a pipeline"
    for p in pack.pipelines:
        keys = [s.key for s in p.stages]
        assert len(keys) == len(set(keys)), f"{pack.key}: duplicate stage keys"
        assert sum(s.is_won for s in p.stages) == 1 and sum(s.is_lost for s in p.stages) == 1
    field_keys = [(f.entity, f.key) for f in pack.custom_fields]
    assert len(field_keys) == len(set(field_keys))
    for f in pack.custom_fields:
        assert f.type in CustomField.Type.values
        if f.type in ("choice", "multi"):
            assert f.options
    assert pack.document_templates and pack.reports and pack.dashboard_widgets
    if not pack.deep_module and pack.key != "generic":
        assert pack.planned, f"{pack.key}: say what its deep module will add"


@pytest.mark.parametrize("pack", registry.all_packs(), ids=lambda p: p.key)
def test_stage_colours_are_readable_as_pills(pack):
    from apps.core.branding import contrast

    for p in pack.pipelines:
        for s in p.stages:
            # pill text in the stage colour on a 14% tint of it (close to white)
            assert contrast(s.colour, "#F2F2F2") >= 4.5, f"{pack.key}/{s.key} {s.colour}"


@pytest.mark.django_db
def test_apply_pack_is_idempotent(org1):
    before = _counts(org1)
    apply_pack(org1, "tourism", "tour_operator")
    apply_pack(org1, "tourism", "tour_operator")
    assert _counts(org1) == before


def _counts(org):
    with tenant(org):
        return (Pipeline.objects.count(), PipelineStage.objects.count(), CustomField.objects.count(),
                AppliedPack.objects.count(), tuple(org.enabled_modules))


@pytest.mark.django_db
def test_reapplying_never_overwrites_admin_edits(org1):
    with tenant(org1):
        field = CustomField.objects.get(entity="lead", key="residency")
        field.label, field.customised = "Guest residency", True
        field.save()
        stage = PipelineStage.objects.get(key="proposal-sent")
        stage.name = "Quote out"
        stage.save()
        CustomField.objects.create(entity="contact", key="own_field", label="Our own")
    apply_pack(org1, "tourism", "tour_operator")
    with tenant(org1):
        assert CustomField.objects.get(entity="lead", key="residency").label == "Guest residency"
        assert PipelineStage.objects.get(key="proposal-sent").name == "Quote out"
        assert CustomField.objects.filter(key="own_field").exists()


@pytest.mark.django_db
def test_missing_stages_are_added_back_on_reapply(org1):
    with tenant(org1):
        PipelineStage.objects.filter(key="negotiating").delete()
    apply_pack(org1, "tourism", "tour_operator")
    with tenant(org1):
        assert PipelineStage.objects.filter(key="negotiating").exists()


@pytest.mark.django_db
def test_adding_a_second_pack_keeps_the_first(org1):
    apply_pack(org1, "events", "venue", primary=False)
    org1.refresh_from_db()
    assert org1.industry == "tourism"
    assert "tourism" in org1.enabled_modules
    with tenant(org1):
        assert set(AppliedPack.objects.values_list("pack_key", flat=True)) == {"tourism", "events"}
        assert CustomField.objects.filter(entity="deal", key="event_type").exists()
        assert CustomField.objects.filter(entity="lead", key="residency").exists()


@pytest.mark.django_db
def test_switching_primary_pack_changes_words_not_data(org1):
    with tenant(org1):
        fields_before = CustomField.objects.count()
    apply_pack(org1, "real_estate", "agency", primary=True)
    org1.refresh_from_db()
    assert term("lead", org=org1) == "Prospect"
    with tenant(org1):
        assert CustomField.objects.count() > fields_before
        assert CustomField.objects.filter(key="residency").exists()


@pytest.mark.django_db
def test_plan_limits_the_number_of_packs(org1):
    from apps.billing.models import Plan

    org1.status = "active"
    org1.plan = Plan.objects.get(key="starter")
    org1.save()
    with pytest.raises(PackLimitError):
        apply_pack(org1, "events", "venue", primary=False)


@pytest.mark.django_db
def test_terminology_resolution_order(org1):
    assert term("lead", org=org1) == "Enquiry"
    assert term("lead", org=org1, plural=True) == "Enquiries"
    assert term("deal", org=org1) == "Booking"
    org1.sub_niche = "safari_camp"
    org1.save()
    org1._terms_cache = None
    del org1._terms_cache
    assert term("deal", org=org1) == "Reservation"  # sub-niche wins over the pack
    with tenant(org1):
        TerminologyOverride.objects.create(key="deal", singular="Safari", plural="Safaris")
    del org1._terms_cache
    assert term("deal", org=org1, plural=True) == "Safaris"  # the organization's override wins
    assert term("contact", org=org1) == "Contact"  # core default


@pytest.mark.django_db
def test_term_template_tag(org1, org2):
    t = Template('{% term "lead" plural=True %}|{% term "product" lower=True %}')
    assert t.render(Context({"org": org1})) == "Enquiries|package"
    assert t.render(Context({"org": org2})) == "Prospects|property"
    assert t.render(Context({})) == "Leads|product"


@pytest.mark.django_db
def test_custom_fields_form_mixin(org1):
    from django import forms

    class Record:
        custom = {"other": "kept"}

    class F(CustomFieldsFormMixin, forms.Form):
        custom_entity = "lead"

        def save(self, commit=True):  # a plain form: apply to an object
            obj = Record()
            self.apply_custom_values(obj)
            return obj

    with tenant(org1):
        form = F(data={"cf_adults": "2", "cf_residency": "Resident", "cf_travel_from": "2026-12-20",
                       "cf_interests": ["Beach", "Birding"], "cf_budget_pp": "185000"})
        assert {"cf_adults", "cf_residency", "cf_travel_from"} <= set(form.fields)
        assert form.is_valid(), form.errors
        obj = form.save()
    assert obj.custom["adults"] == "2" and obj.custom["travel_from"] == "2026-12-20"
    assert obj.custom["budget_pp"] == "185000.00" and obj.custom["interests"] == ["Beach", "Birding"]
    assert obj.custom["other"] == "kept"
    with tenant(org1):
        bad = F(data={"cf_residency": "Martian"})
        assert not bad.is_valid() and "cf_residency" in bad.errors


@pytest.mark.django_db
def test_core_templates_never_hard_code_industry_words():
    """Industry words belong in packs; core templates use {% term %}."""
    import re
    from pathlib import Path

    from django.conf import settings

    words = ["Enquiry", "Enquiries", "Prospect", "Booking", "Patient", "Propert", "Package", "Tour", "Itinerar",
             "Lead", "Leads", "Deal", "Deals", "Student", "Donor"]
    pattern = re.compile(r">[^<{]*\b(" + "|".join(words) + r")", re.MULTILINE)
    root = Path(settings.BASE_DIR) / "templates"
    skip = ("tourism/", "realestate/", "website/")
    offenders = []
    for path in root.rglob("*.html"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(skip):
            continue
        for m in pattern.finditer(path.read_text()):
            offenders.append(f"{rel}: {m.group(1)}")
    assert not offenders, offenders


@pytest.mark.django_db
def test_onboarding_checklist_hides_pages_not_built_yet(org1, rf):
    from django.conf import settings
    from django.urls import set_urlconf

    from apps.industries.checklist import items_for

    set_urlconf(settings.TENANT_URLCONF)
    try:
        with tenant(org1):
            keys = {i["key"] for i in items_for(org1)}
    finally:
        set_urlconf(None)
    assert "logo" in keys and "invite" in keys
    assert "destinations" not in keys  # tourism pages arrive in phase 4
