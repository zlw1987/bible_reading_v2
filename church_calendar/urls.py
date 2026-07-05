from django.urls import path

from . import views


urlpatterns = [
    path(
        "calendar/",
        views.church_calendar_month,
        name="church_calendar_month",
    ),
    path(
        "calendar/<int:year>/<int:month>/<int:day>/",
        views.church_calendar_day,
        name="church_calendar_day",
    ),
]
