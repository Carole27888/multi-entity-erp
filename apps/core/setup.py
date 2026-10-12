"""Global reference data (post_migrate): currencies and country templates, plus the database cache table.
Created with get_or_create, so edits made later in the platform admin are never overwritten."""

from decimal import Decimal

CURRENCIES = [
    ("KES", "Kenyan shilling", "KSh", 2), ("UGX", "Ugandan shilling", "USh", 0), ("TZS", "Tanzanian shilling", "TSh", 2),
    ("RWF", "Rwandan franc", "FRw", 0), ("ETB", "Ethiopian birr", "Br", 2), ("ZAR", "South African rand", "R", 2),
    ("NGN", "Nigerian naira", "₦", 2), ("GHS", "Ghanaian cedi", "GH₵", 2), ("USD", "US dollar", "$", 2),
    ("EUR", "Euro", "€", 2), ("GBP", "Pound sterling", "£", 2), ("AED", "UAE dirham", "AED", 2),
]

# code, name, currency, time zone, dial code, standard VAT %, has full templates (tax, payroll, chart of accounts)
COUNTRIES = [
    ("KE", "Kenya", "KES", "Africa/Nairobi", "+254", Decimal("16"), True),
    ("UG", "Uganda", "UGX", "Africa/Kampala", "+256", Decimal("18"), False),
    ("TZ", "Tanzania", "TZS", "Africa/Dar_es_Salaam", "+255", Decimal("18"), False),
    ("RW", "Rwanda", "RWF", "Africa/Kigali", "+250", Decimal("18"), False),
    ("ET", "Ethiopia", "ETB", "Africa/Addis_Ababa", "+251", Decimal("15"), False),
    ("ZA", "South Africa", "ZAR", "Africa/Johannesburg", "+27", Decimal("15"), False),
    ("NG", "Nigeria", "NGN", "Africa/Lagos", "+234", Decimal("7.5"), False),
    ("GH", "Ghana", "GHS", "Africa/Accra", "+233", Decimal("15"), False),
]


def run(sender=None, **kwargs):
    from django.conf import settings
    from django.core.management import call_command

    from .models import Country, Currency

    for code, name, symbol, decimals in CURRENCIES:
        Currency.objects.get_or_create(code=code, defaults={"name": name, "symbol": symbol, "decimals": decimals})
    for code, name, cur, tz, dial, vat, templates in COUNTRIES:
        Country.objects.get_or_create(code=code, defaults={
            "name": name, "currency_id": cur, "timezone": tz, "dial_code": dial, "default_vat_rate": vat,
            "has_templates": templates})
    if "DatabaseCache" in settings.CACHES["default"]["BACKEND"]:
        call_command("createcachetable", verbosity=0)
