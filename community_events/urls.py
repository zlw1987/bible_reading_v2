from django.urls import path

from . import views

urlpatterns = [
    path(
        "activities/",
        views.community_activity_list,
        name="community_activity_list",
    ),
    path(
        "activities/<int:activity_id>/",
        views.community_activity_detail,
        name="community_activity_detail",
    ),
]
