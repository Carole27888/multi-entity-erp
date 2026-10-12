"""Demo organizations with realistic Kenyan details, one per industry pack.

    python manage.py seed_demo                    # every pack
    python manage.py seed_demo --pack tourism     # one pack
    python manage.py seed_demo --reset            # delete the demo organizations and users first

Every demo account uses the password printed at the end (default Demo@2026!). Owners, admins and finance
users must set up two-factor login on first sign-in unless TWO_FACTOR_ENFORCED=False.
Business records (contacts, enquiries, bookings…) are added by each module's sample loader as modules ship.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Department, User
from apps.industries import registry, sample
from apps.industries.services import apply_pack
from apps.tenancy.context import tenant
from apps.tenancy.models import Membership, Organization
from apps.tenancy.services import builtin_role, create_organization

PASSWORD = "Demo@2026!"
PLATFORM_EMAIL = "platform@demo.co.ke"
MULTI_EMAIL = "wanjiku@demo.co.ke"

# pack: (name, slug, sub-niche, brand colour, phone, address, owner name)
# Demo organizations use the platform colour (settings.BRAND_COLOUR) so the default look is what you see;
# each organization can pick its own under Settings › Profile & branding.
DEMO_ORGS = {
    "tourism": ("Savannah Trails Safaris", "savannah-trails", "tour_operator", "#9A3412", "+254722410300",
                "Lavington Green, James Gichuru Road, Nairobi", "Daniel Ole Sankale"),
    "real_estate": ("Kilimani Homes", "kilimani-homes", "agency", "#1E3A8A", "+254733120450",
                    "Argwings Kodhek Road, Kilimani, Nairobi", "Grace Wambui Njoroge"),
    "hospitality": ("Lake Naivasha Lodge", "naivasha-lodge", "lodge_camp", "#065F46", "+254720550870",
                    "Moi South Lake Road, Naivasha", "Peter Kamau Gitau"),
    "restaurants": ("Jikoni Grill", "jikoni-grill", "restaurant", "#B45309", "+254711302040",
                    "Ngong Road, Adams Arcade, Nairobi", "Akinyi Odhiambo"),
    "retail": ("Duka Bora Supermarket", "duka-bora", "minimart", "#BE123C", "+254702661190",
               "Kenyatta Avenue, Nakuru", "Hassan Abdi Mohamed"),
    "wholesale": ("Pwani Distributors", "pwani-distributors", "fmcg", "#0369A1", "+254741228830",
                  "Moi Avenue, Mombasa", "Fatma Said Bakari"),
    "manufacturing": ("Kiambu Furniture Works", "kiambu-furniture", "furniture", "#78350F", "+254722874410",
                      "Thika Road, Ruiru", "Joseph Mwangi Kariuki"),
    "construction": ("Imara Builders", "imara-builders", "general_contractor", "#C2410C", "+254733902215",
                     "Mombasa Road, Syokimau", "Collins Otieno Ouma"),
    "professional_services": ("Achieng & Mutua Advocates", "achieng-mutua", "legal", "#312E81", "+254720118833",
                              "Upper Hill, Nairobi", "Lilian Achieng Mutua"),
    "healthcare": ("Afya Bora Clinic", "afya-bora", "general_clinic", "#0F766E", "+254711445566",
                   "Thika Road Mall, Roysambu, Nairobi", "Dr. Esther Chebet"),
    "education": ("Elimu Skills Institute", "elimu-skills", "training_provider", "#4338CA", "+254700334455",
                  "Kimathi Street, Nairobi", "Samuel Kiprono Rotich"),
    "salons_spas": ("Nywele Hair Studio", "nywele-studio", "hair_salon", "#A21CAF", "+254799221133",
                    "Westlands, Sarit Centre, Nairobi", "Mercy Nyambura"),
    "fitness": ("Westlands Fitness Hub", "westlands-fitness", "gym", "#B91C1C", "+254710998877",
                "Woodvale Grove, Westlands, Nairobi", "Brian Omondi"),
    "events": ("Karen Gardens Events", "karen-gardens", "venue", "#3F6212", "+254722667788",
               "Karen Road, Nairobi", "Naomi Wanjiru Kiarie"),
    "logistics": ("Mombasa Freight Movers", "mombasa-freight", "freight_forwarding", "#1E40AF", "+254733556677",
                  "Port Reitz Road, Changamwe, Mombasa", "Ali Hassan Juma"),
    "automotive": ("Industrial Area Auto Care", "auto-care", "garage", "#334155", "+254721334466",
                   "Enterprise Road, Industrial Area, Nairobi", "Kevin Mutiso Musyoka"),
    "agriculture": ("Meru Avocado Growers", "meru-avocado", "aggregator", "#166534", "+254724778899",
                    "Makutano, Meru", "Purity Kendi Mwiti"),
    "nonprofit": ("Tumaini Children's Foundation", "tumaini-foundation", "foundation", "#9D174D", "+254712009988",
                  "Kileleshwa, Nairobi", "Ruth Njeri Kamau"),
    "generic": ("Upande Ventures", "upande-ventures", "general", "#134E4A", "+254700112233",
                "Kilimani Business Centre, Nairobi", "Victor Kipchumba"),
}

# Extra staff for the deep packs: (role key, full name, email local part, department)
TEAMS = {
    "tourism": [
        ("admin", "Mary Wairimu Gachanja", "mary", "Management"),
        ("manager", "John Lekishon", "john", "Sales"),
        ("finance", "Beatrice Atieno Okoth", "beatrice", "Finance"),
        ("sales", "Kelvin Mwenda", "kelvin", "Sales"),
        ("sales", "Halima Yusuf", "halima", "Sales"),
        ("operations", "Moses Kiplagat", "moses", "Operations"),
        ("staff", "Joseph Lemayian", "joseph", "Operations"),
        ("read_only", "Margaret Ole Sankale", "director", "Management"),
    ],
    "real_estate": [
        ("admin", "Stephen Kimani Ndungu", "stephen", "Management"),
        ("manager", "Caroline Njeri Mwangi", "caroline", "Sales"),
        ("finance", "Dennis Ochieng", "dennis", "Finance"),
        ("sales", "Sarah Wanjiku", "sarah", "Sales"),
        ("sales", "James Kariuki", "james", "Sales"),
        ("operations", "Lucy Akinyi", "lucy", "Lettings"),
        ("read_only", "Patrick Njoroge", "director", "Management"),
    ],
}


def _domain(slug: str) -> str:
    return f"{slug}.co.ke"


class Command(BaseCommand):
    help = "Create demo organizations (one per industry pack) with realistic Kenyan details."

    def add_arguments(self, parser):
        parser.add_argument("--pack", default="all", help="Pack key (e.g. tourism, real_estate) or 'all'.")
        parser.add_argument("--reset", action="store_true", help="Delete the demo organizations and users first.")
        parser.add_argument("--password", default=PASSWORD)

    def handle(self, *args, **opts):
        keys = list(DEMO_ORGS) if opts["pack"] == "all" else [opts["pack"]]
        for key in keys:
            if key not in DEMO_ORGS or registry.get(key) is None:
                raise CommandError(f"Unknown pack '{key}'. Choose from: {', '.join(DEMO_ORGS)}")
        if opts["reset"]:
            self._reset(keys)
        password = opts["password"]
        platform = self._user(PLATFORM_EMAIL, "Platform Support", password, "+254700000001", is_platform_staff=True,
                              is_staff=True, is_superuser=True)
        multi = self._user(MULTI_EMAIL, "Wanjiku Kamau", password, "+254711000222")
        for key in keys:
            org = self._org(key, password)
            if key == "tourism":
                self._join(org, multi, "sales")
            if key == "real_estate":
                self._join(org, multi, "manager")
        self.stdout.write(self.style.SUCCESS(f"Demo data ready. Password for every account: {password}"))
        self.stdout.write(f"  Platform admin: {platform.email}")
        self.stdout.write(f"  In two organizations (tourism + real estate, no 2FA needed): {multi.email}")
        for key in keys:
            name, slug = DEMO_ORGS[key][0], DEMO_ORGS[key][1]
            self.stdout.write(f"  {name:32} /{slug}/  owner@{_domain(slug)}")

    # --- helpers ---------------------------------------------------------------------------------------

    def _reset(self, keys):
        slugs = [DEMO_ORGS[k][1] for k in keys]
        deleted, _ = Organization.objects.filter(slug__in=slugs).delete()
        domains = tuple(f"@{_domain(s)}" for s in slugs)
        users = User.objects.filter(email__in=[PLATFORM_EMAIL, MULTI_EMAIL]) if len(keys) == len(DEMO_ORGS) else User.objects.none()
        for d in domains:
            users = users | User.objects.filter(email__endswith=d)
        count = users.count()
        users.delete()
        self.stdout.write(f"Reset: removed {len(slugs)} demo organization(s) and {count} user(s).")

    def _user(self, email, name, password, phone, **extra):
        user, created = User.objects.get_or_create(email=email, defaults={
            "full_name": name, "phone": phone, "email_verified_at": timezone.now(), **extra})
        if created:
            user.set_password(password)
            user.save()
        return user

    def _join(self, org, user, role_key):
        Membership.objects.get_or_create(user=user, organization=org, defaults={"role": builtin_role(org, role_key)})

    @transaction.atomic
    def _org(self, key, password) -> Organization:
        name, slug, sub, colour, phone, address, owner_name = DEMO_ORGS[key]
        domain = _domain(slug)
        owner = self._user(f"owner@{domain}", owner_name, password, phone)
        org = Organization.objects.filter(slug=slug).first()
        if org is None:
            org = create_organization(owner, name, slug=slug, phone=phone, address=address,
                                      email=f"info@{domain}", legal_name=f"{name} Ltd")
        apply_pack(org, key, sub, primary=True)
        org.refresh_from_db()
        if not org.onboarding_completed_at:
            org.onboarding_completed_at = timezone.now()
            org.team_size = "6-20" if key in TEAMS else "2-5"
            org.settings = {**org.settings, "sample_data_requested": True}
            org.save()
        for role_key, full_name, local, dept_name in TEAMS.get(key, []):
            user = self._user(f"{local}@{domain}", full_name, password, "")
            with tenant(org, activate_timezone=False):
                dept, _ = Department.objects.get_or_create(name=dept_name)
                membership, _ = Membership.objects.get_or_create(user=user, organization=org,
                                                                 defaults={"role": builtin_role(org, role_key)})
                membership.departments.add(dept)
        sample.load(org)
        self.stdout.write(f"  {name}: pack {key} ({sub}), modules: {', '.join(org.enabled_modules)}")
        return org
