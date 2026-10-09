from django.apps import AppConfig


class AppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app'

    def ready(self):
        """
        Called once when Django starts.
        Wire the post_migrate signal to auto-create the admin account
        so it is always present after any migration run (including fresh installs).
        """
        from django.db.models.signals import post_migrate
        from django.dispatch import receiver

        @receiver(post_migrate, sender=self)
        def _create_admin(sender, **kwargs):
            try:
                from app.management.commands.ensure_admin import ensure_admin_exists
                ensure_admin_exists()
            except Exception:
                # Silently skip on fresh installs before migrations run
                pass
