from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "notifications"
    verbose_name = "Notifications / 通知"

    def ready(self):
        from core.notification_delivery import register_notification_sink

        from .services import persist_notification

        register_notification_sink(persist_notification)
