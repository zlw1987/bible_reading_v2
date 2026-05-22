from django.urls import path

from . import views

urlpatterns = [
    path("events/", views.service_event_list, name="service_event_list"),
    path("events/new/", views.create_service_event, name="create_service_event"),
    path("events/<int:event_id>/", views.service_event_detail, name="service_event_detail"),
    path("events/<int:event_id>/edit/", views.edit_service_event, name="edit_service_event"),
    path("events/<int:event_id>/cancel/", views.cancel_service_event, name="cancel_service_event"),
]
