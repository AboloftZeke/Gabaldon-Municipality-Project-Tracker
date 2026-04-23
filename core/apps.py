from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        """Register signal handlers when the app is ready."""
        import core.signals  # noqa: F401
