from django.urls import path

from . import views

urlpatterns = [
    path(
        "activities/",
        views.community_activity_list,
        name="community_activity_list",
    ),
    path(
        "activities/new/",
        views.community_activity_create,
        name="community_activity_create",
    ),
    path(
        "activities/<int:activity_id>/",
        views.community_activity_detail,
        name="community_activity_detail",
    ),
    path(
        "activities/<int:activity_id>/signup/",
        views.community_activity_signup,
        name="community_activity_signup",
    ),
    path(
        "activities/<int:activity_id>/cancel-signup/",
        views.community_activity_cancel_signup,
        name="community_activity_cancel_signup",
    ),
]
