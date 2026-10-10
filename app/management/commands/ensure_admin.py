"""
Management command: ensure_admin

Guarantees that the single hardcoded administrator account always exists
in the database.  Safe to run multiple times (idempotent).

Usage:
    python manage.py ensure_admin

Also called automatically via the post_migrate signal in AppConfig.ready().
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings

ADMIN_EMAIL    = getattr(settings, 'ADMIN_EMAIL', 'cheersthepure@gmail.com')
ADMIN_PASSWORD = getattr(settings, 'ADMIN_PASSWORD', 'change-this-admin-password')
ADMIN_USERNAME = 'cheersadmin'


def ensure_admin_exists():
    """
    Create or repair the hardcoded administrator account.
    Returns (user, created) tuple.
    """
    user, created = User.objects.get_or_create(
        email=ADMIN_EMAIL,
        defaults={
            'username':     ADMIN_USERNAME,
            'is_staff':     True,
            'is_superuser': True,
            'first_name':   'Cheers',
            'last_name':    'Admin',
        },
    )

    # Always ensure the account has full admin privileges
    changed = False
    if not user.is_staff:
        user.is_staff = True
        changed = True
    if not user.is_superuser:
        user.is_superuser = True
        changed = True

    # On first creation, set the password
    if created:
        user.set_password(ADMIN_PASSWORD)
        user.save()
    elif changed:
        user.save(update_fields=['is_staff', 'is_superuser'])

    # Ensure a UserProfile exists for the admin
    from app.models import UserProfile
    UserProfile.objects.get_or_create(
        user=user,
        defaults={
            'role':         'staff',
            'account_type': 'b2b',
            'company_name': 'Cheers the Pure Water',
        },
    )

    return user, created


class Command(BaseCommand):
    help = 'Ensure the hardcoded administrator account (cheersthepure@gmail.com) exists.'

    def handle(self, *args, **options):
        user, created = ensure_admin_exists()
        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f'[OK] Admin account created: {ADMIN_EMAIL}'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'[INFO] Admin account already exists: {ADMIN_EMAIL}'
                )
            )
