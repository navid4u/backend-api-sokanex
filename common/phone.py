import re

from django.core.exceptions import ValidationError


_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)
_IRAN_MOBILE_RE = re.compile(r"^09\d{9}$")


def normalize_iran_phone(value):
    if value is None:
        return None
    phone = str(value).translate(_DIGIT_TRANSLATION).strip()
    phone = re.sub(r"[\s\-()]+", "", phone)
    if phone.startswith("+98"):
        phone = "0" + phone[3:]
    elif phone.startswith("0098"):
        phone = "0" + phone[4:]
    elif phone.startswith("98"):
        phone = "0" + phone[2:]
    elif phone.startswith("9") and len(phone) == 10:
        phone = "0" + phone
    if not _IRAN_MOBILE_RE.fullmatch(phone):
        raise ValidationError("شماره همراه معتبر نیست.")
    return phone


def validate_iran_phone(value):
    normalize_iran_phone(value)

