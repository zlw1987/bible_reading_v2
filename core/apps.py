from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Structure-core support app (MODULAR-CORE.1A).

    Holds cross-module foundation code that is not itself a CMS module:
    the module registry / feature gates and their template context support.
    It defines no models and requires no migrations.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
