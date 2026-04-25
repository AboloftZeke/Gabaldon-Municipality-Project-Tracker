from django.apps import AppConfig


class SystemConfig(AppConfig):
    name = 'apps.system'
    label = 'system'

    def ready(self):
        """Register signal handlers when the app is ready."""
        import apps.system.signals  # noqa: F401
