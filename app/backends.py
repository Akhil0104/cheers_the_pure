"""
Custom authentication backend for Cheers the Pure Water.

Allows users to log in using EITHER:
  - Their email address
  - Their registered mobile / phone number

No username is ever required by end users.
"""

import re
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q
from django.conf import settings


# Simple heuristic: 7-15 digit strings (with optional leading +) = mobile number
_MOBILE_RE = re.compile(r'^\+?[\d\s\-]{7,15}$')

ADMIN_EMAIL    = getattr(settings, 'ADMIN_EMAIL', 'cheersthepure@gmail.com')
ADMIN_PASSWORD = getattr(settings, 'ADMIN_PASSWORD', 'change-this-admin-password')


def _looks_like_mobile(value: str) -> bool:
    return bool(_MOBILE_RE.match(value.strip()))


class EmailOrMobileBackend(ModelBackend):
    """
    Authenticate against email address OR mobile phone number.

    The 'username' parameter received from the login form is treated
    as either an email or a mobile — we resolve it to a User automatically.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        credential = username.strip()
        user = None

        try:
            if _looks_like_mobile(credential):
                # Mobile number path — look up via UserProfile.phone
                from app.models import UserProfile
                digits_only = re.sub(r'[\s\-]', '', credential)
                profile = UserProfile.objects.select_related('user').get(
                    phone=digits_only
                )
                user = profile.user
            else:
                # Email path — case-insensitive match
                user = User.objects.get(email__iexact=credential)
        except (User.DoesNotExist, Exception):
            # Run a dummy password check to prevent timing attacks
            User().set_password(password)
            return None

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
