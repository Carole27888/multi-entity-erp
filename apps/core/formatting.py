"""Money, Kenyan phone numbers and date/duration display helpers."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.utils import timezone

PHONE_DIGITS = re.compile(r"\D+")


def normalise_phone(raw: str | None) -> str:
    """Return E.164 form. Kenyan numbers become +2547XXXXXXXX / +2541XXXXXXXX.

    Accepts 0712 345 678, 712345678, 254712345678, +254 712-345-678, 00254...
    Foreign numbers written with + or 00 keep their country code.
    Returns "" for empty input; raises ValueError for obviously invalid numbers.
    """
    if not raw:
        return ""
    raw = raw.strip()
    has_plus = raw.startswith("+")
    digits = PHONE_DIGITS.sub("", raw)
    if digits.startswith("00"):
        digits, has_plus = digits[2:], True
    if not digits:
        return ""
    if digits.startswith("254") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 10 and digits[1] in "17":
        return "+254" + digits[1:]
    if len(digits) == 9 and digits[0] in "17" and not has_plus:
        return "+254" + digits
    if has_plus and 8 <= len(digits) <= 15:
        return "+" + digits
    raise ValueError(f"'{raw}' is not a valid phone number")


def is_kenyan_phone(phone: str) -> bool:
    return bool(phone) and phone.startswith("+254")


def to_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def kes(value, with_currency: bool = True, decimals: int = 0) -> str:
    """4850000 -> 'KES 4,850,000'. Negative numbers get a leading minus."""
    amount = to_decimal(value).quantize(Decimal(1) / (Decimal(10) ** decimals), rounding=ROUND_HALF_UP)
    text = f"{abs(amount):,.{decimals}f}"
    sign = "-" if amount < 0 else ""
    return f"{sign}KES {text}" if with_currency else f"{sign}{text}"


def money(value, currency: str = "KES", decimals: int | None = None) -> str:
    """4850000, "KES" -> 'KES 4,850,000'; 1250.5, "USD" -> 'USD 1,250.50'. Shillings show no cents by default."""
    if decimals is None:
        decimals = 0 if currency in ("KES", "UGX", "TZS", "RWF") else 2
    amount = to_decimal(value).quantize(Decimal(1) / (Decimal(10) ** decimals), rounding=ROUND_HALF_UP)
    text = f"{abs(amount):,.{decimals}f}"
    sign = "-" if amount < 0 else ""
    return f"{sign}{currency} {text}"


def compact(value) -> str:
    """2120000 -> '2.12M', 48200 -> '48.2K'."""
    amount = float(to_decimal(value))
    for size, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if abs(amount) >= size:
            return f"{amount / size:.2f}".rstrip("0").rstrip(".") + suffix
    return f"{amount:.0f}"


def display_date(value) -> str:
    """28 Apr 2025"""
    if not value:
        return ""
    if hasattr(value, "tzinfo") and value.tzinfo is not None:
        value = timezone.localtime(value)
    return f"{value.day} {value:%b %Y}"


def display_time(value) -> str:
    """2:45 PM"""
    if not value:
        return ""
    if hasattr(value, "tzinfo") and value.tzinfo is not None:
        value = timezone.localtime(value)
    return value.strftime("%I:%M %p").lstrip("0")


def duration(seconds) -> str:
    """248 -> '4m 08s'; 5400 -> '1h 30m'."""
    seconds = int(seconds or 0)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"


def initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
         "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _words_below_1000(n: int) -> str:
    parts = []
    if n >= 100:
        parts.append(f"{_ONES[n // 100]} Hundred")
        n %= 100
        if n:
            parts.append("and")
    if n >= 20:
        parts.append(_TENS[n // 10] + (f"-{_ONES[n % 10]}" if n % 10 else ""))
    elif n:
        parts.append(_ONES[n])
    return " ".join(parts)


def amount_in_words(value) -> str:
    """4850000.50 → 'Kenya Shillings Four Million Eight Hundred and Fifty Thousand and Fifty Cents Only'."""
    amount = to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    shillings, cents = int(amount), int((amount - int(amount)) * 100)
    if shillings == 0:
        words = "Zero"
    else:
        chunks = []
        for size, name in ((10**9, "Billion"), (10**6, "Million"), (1000, "Thousand"), (1, "")):
            if shillings >= size:
                chunk, shillings = divmod(shillings, size)
                chunks.append(f"{_words_below_1000(chunk)} {name}".strip())
        words = " ".join(chunks)
    out = f"Kenya Shillings {words}"
    if cents:
        out += f" and {_words_below_1000(cents)} Cents"
    return out + " Only"
