from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'apps.core'
    label = 'core'

    def ready(self):
        """Register signal handlers when the app is ready."""
        import apps.core.signals  # noqa: F401
