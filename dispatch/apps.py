import sys
from django.apps import AppConfig


class DispatchConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dispatch'
    verbose_name = 'DispatchAI'

    def ready(self):
        """Run startup environment validation for DispatchAI."""
        # Avoid running duplicate validation during management commands like makemigrations
        is_management = any(cmd in sys.argv for cmd in ('makemigrations', 'migrate', 'collectstatic', 'check'))
        if not is_management:
            try:
                from .config import validate_dispatch_environment
                validate_dispatch_environment()
            except Exception:
                pass
