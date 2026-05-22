from functools import reduce
from operator import or_

from django.db.models import Q

from .models import ChurchRoleAssignment, SmallGroup

CAP_MANAGE_READING_PLANS = "manage_reading_plans"
CAP_PUBLISH_READING_GUIDES = "publish_reading_guides"
CAP_MANAGE_BIBLE_STUDIES = "manage_bible_studies"
CAP_PUBLISH_BIBLE_STUDY_GUIDES = "publish_bible_study_guides"
CAP_MANAGE_SERVICE_EVENTS = "manage_service_events"
CAP_MANAGE_MINISTRY_TEAMS = "manage_ministry_teams"
CAP_VIEW_GROUP_PROGRESS = "view_group_progress"
CAP_VIEW_DISTRICT_PROGRESS = "view_district_progress"
CAP_VIEW_ALL_GROUP_PROGRESS = "view_all_group_progress"
CAP_MODERATE_REFLECTIONS = "moderate_reflections"
CAP_MODERATE_PRAYERS = "moderate_prayers"
CAP_MANAGE_USERS = "manage_users"

ALL_CAPABILITIES = {
    CAP_MANAGE_READING_PLANS,
    CAP_PUBLISH_READING_GUIDES,
    CAP_MANAGE_BIBLE_STUDIES,
    CAP_PUBLISH_BIBLE_STUDY_GUIDES,
    CAP_MANAGE_SERVICE_EVENTS,
    CAP_MANAGE_MINISTRY_TEAMS,
    CAP_VIEW_GROUP_PROGRESS,
    CAP_VIEW_DISTRICT_PROGRESS,
    CAP_VIEW_ALL_GROUP_PROGRESS,
    CAP_MODERATE_REFLECTIONS,
    CAP_MODERATE_PRAYERS,
    CAP_MANAGE_USERS,
}

ROLE_CAPABILITIES = {
    ChurchRoleAssignment.ROLE_PASTOR: {
        CAP_PUBLISH_READING_GUIDES,
        CAP_MANAGE_BIBLE_STUDIES,
        CAP_PUBLISH_BIBLE_STUDY_GUIDES,
        CAP_MANAGE_SERVICE_EVENTS,
        CAP_MANAGE_MINISTRY_TEAMS,
        CAP_VIEW_ALL_GROUP_PROGRESS,
        CAP_MODERATE_REFLECTIONS,
        CAP_MODERATE_PRAYERS,
    },
    ChurchRoleAssignment.ROLE_ELDER: {
        CAP_MANAGE_BIBLE_STUDIES,
        CAP_PUBLISH_BIBLE_STUDY_GUIDES,
        CAP_MANAGE_SERVICE_EVENTS,
        CAP_MANAGE_MINISTRY_TEAMS,
        CAP_VIEW_ALL_GROUP_PROGRESS,
        CAP_MODERATE_REFLECTIONS,
        CAP_MODERATE_PRAYERS,
    },
    ChurchRoleAssignment.ROLE_DEACON: {
        CAP_VIEW_ALL_GROUP_PROGRESS,
        CAP_MANAGE_USERS,
    },
    ChurchRoleAssignment.ROLE_DISTRICT_LEADER: {
        CAP_VIEW_DISTRICT_PROGRESS,
    },
    ChurchRoleAssignment.ROLE_GROUP_LEADER: {
        CAP_VIEW_GROUP_PROGRESS,
    },
    ChurchRoleAssignment.ROLE_COWORKER: {
        CAP_MANAGE_READING_PLANS,
        CAP_MANAGE_BIBLE_STUDIES,
        CAP_PUBLISH_BIBLE_STUDY_GUIDES,
        CAP_MANAGE_SERVICE_EVENTS,
        CAP_MANAGE_MINISTRY_TEAMS,
    },
}


def get_user_active_role_assignments(user):
    if not getattr(user, "is_authenticated", False):
        return ChurchRoleAssignment.objects.none()

    return (
        ChurchRoleAssignment.objects.filter(user=user, is_active=True)
        .select_related("district", "small_group")
        .order_by("role", "scope_type")
    )


def has_capability(user, capability):
    if not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return capability in ALL_CAPABILITIES

    for assignment in get_user_active_role_assignments(user):
        if capability in ROLE_CAPABILITIES.get(assignment.role, set()):
            return True

    return False


def get_accessible_progress_groups(user):
    groups = SmallGroup.objects.filter(is_active=True).order_by("name")

    if not getattr(user, "is_authenticated", False):
        return groups.none()

    if (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or has_capability(user, CAP_VIEW_ALL_GROUP_PROGRESS)
    ):
        return groups

    filters = []
    assignments = list(get_user_active_role_assignments(user))

    district_ids = [
        assignment.district_id
        for assignment in assignments
        if assignment.role == ChurchRoleAssignment.ROLE_DISTRICT_LEADER
        and assignment.scope_type == ChurchRoleAssignment.SCOPE_DISTRICT
        and assignment.district_id
    ]
    if district_ids:
        filters.append(Q(district_id__in=district_ids, district__is_active=True))

    small_group_ids = [
        assignment.small_group_id
        for assignment in assignments
        if assignment.role == ChurchRoleAssignment.ROLE_GROUP_LEADER
        and assignment.scope_type == ChurchRoleAssignment.SCOPE_SMALL_GROUP
        and assignment.small_group_id
    ]
    if small_group_ids:
        filters.append(Q(id__in=small_group_ids))

    profile = getattr(user, "profile", None)
    own_group = getattr(profile, "small_group", None)
    if own_group and own_group.is_active:
        filters.append(Q(id=own_group.id))

    if not filters:
        return groups.none()

    return groups.filter(reduce(or_, filters)).distinct().order_by("name")


def can_view_group_progress_for(user, small_group):
    if small_group is None:
        return False

    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True

    return get_accessible_progress_groups(user).filter(id=small_group.id).exists()
