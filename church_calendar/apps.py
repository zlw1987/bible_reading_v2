from django.apps import AppConfig


class ChurchCalendarConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "church_calendar"
    verbose_name = "Church Calendar / 教会日历"

    def ready(self):
        # CHURCH-CALENDAR.1B: the single explicit registration site wires the
        # four member-safe source range providers in deterministic order. This
        # only registers them; the aggregator still skips disabled source
        # modules at request time.
        from .registration import register_calendar_source_providers

        register_calendar_source_providers()
