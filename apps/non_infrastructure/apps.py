from django.apps import AppConfig


class NonInfrastructureConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.non_infrastructure'
