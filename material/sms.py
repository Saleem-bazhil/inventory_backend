"""
Fast2SMS integration for OTP verification.
Docs: https://docs.fast2sms.com/

Uses the "q" (quick transactional) route which doesn't require website verification.
"""

import random
import re
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone


FAST2SMS_API_URL = "https://www.fast2sms.com/dev/bulkV2"
OTP_EXPIRY_SECONDS = 300  # 5 minutes
OTP_LENGTH = 6


def _get_api_key():
    return getattr(settings, "FAST2SMS_API_KEY", "")


def _clean_phone(phone: str) -> str:
    """Strip non-digits and remove leading +91 or 91 to get 10-digit Indian number."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 13 and digits.startswith("091"):
        digits = digits[3:]
    return digits


def send_otp_sms(phone: str) -> str:
    """Generate OTP, store it in the database, and send via Fast2SMS OTP route."""
    from .models import OTPVerification

    api_key = _get_api_key()
    if not api_key:
        raise ValueError("FAST2SMS_API_KEY is not configured in Django settings.")

    phone = _clean_phone(phone)
    if len(phone) != 10:
        raise ValueError(f"Invalid phone number: must be 10 digits, got {len(phone)}")

    otp = str(random.randint(10 ** (OTP_LENGTH - 1), 10**OTP_LENGTH - 1))

    # Remove any existing OTPs for this phone, then store the new one
    OTPVerification.objects.filter(phone=phone).delete()
    OTPVerification.objects.create(
        phone=phone,
        otp=otp,
        expires_at=timezone.now() + timedelta(seconds=OTP_EXPIRY_SECONDS),
    )

    message = f"Your OTP for service verification is {otp}. Valid for 5 minutes. Do not share with anyone."
    params = {
        "authorization": api_key,
        "route": "q",
        "message": message,
        "language": "english",
        "flash": "0",
        "numbers": phone,
    }
    headers = {
        "authorization": api_key,
    }
    resp = requests.get(FAST2SMS_API_URL, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    return otp


def verify_otp(phone: str, otp: str) -> bool:
    """Verify OTP for a given phone number using the database."""
    from .models import OTPVerification

    phone = _clean_phone(phone)

    # Clean up expired OTPs
    OTPVerification.objects.filter(expires_at__lt=timezone.now()).delete()

    entry = OTPVerification.objects.filter(phone=phone).first()
    if not entry:
        return False
    if entry.is_expired():
        entry.delete()
        return False
    if entry.otp != otp:
        return False

    # OTP verified — remove it so it can't be reused
    entry.delete()
    return True
