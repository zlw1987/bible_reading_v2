from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import PasswordChangeView
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST


from .forms import (
    LocalizedPasswordChangeForm,
    ProfileForm,
    SignUpForm,
    StaffPasswordResetForm,
    StructureMembershipAddForm,
)
from .language import get_user_language, set_user_language
from .ui_text import UI_TEXT
from .models import (
    ChurchStructureMembership,
    ChurchStructureUnit,
    Profile,
)
from .permissions import CAP_MANAGE_CHURCH_MEMBERSHIPS, has_capability


@staff_member_required
def staff_overview(request):
    from comments.models import ReflectionComment, ReflectionReport
    from events.models import ServiceEvent
    from ministry.models import MinistryTeam, TeamAssignment, TeamMembership
    from ministry.services.assignment_coverage import (
        assignment_coverage_queryset,
        count_upcoming_required_team_gaps,
        events_with_coverage_queryset,
    )
    from prayers.models import PrayerReport, PrayerRequest
    from studies.models import BibleStudyLesson, BibleStudyMeeting, BibleStudySeries

    now = timezone.now()
    today = timezone.localdate()

    pending_membership_requests = ChurchStructureMembership.objects.filter(
        status=ChurchStructureMembership.STATUS_REQUESTED,
    ).count()

    draft_schedules = BibleStudySeries.objects.filter(
        status=BibleStudySeries.STATUS_DRAFT,
    ).count()
    upcoming_schedules = BibleStudySeries.objects.filter(
        start_date__gte=today,
    ).exclude(
        status=BibleStudySeries.STATUS_CANCELLED,
    ).count()
    draft_guides = BibleStudyLesson.objects.filter(
        status=BibleStudyLesson.STATUS_DRAFT,
    ).count()
    upcoming_guides = BibleStudyLesson.objects.filter(
        lesson_date__gte=today,
    ).exclude(
        status=BibleStudyLesson.STATUS_CANCELLED,
    ).count()
    draft_meetings = BibleStudyMeeting.objects.filter(
        status=BibleStudyMeeting.STATUS_DRAFT,
    ).count()
    upcoming_meetings = BibleStudyMeeting.objects.filter(
        meeting_datetime__gte=now,
    ).exclude(
        status=BibleStudyMeeting.STATUS_CANCELLED,
    ).count()

    open_prayer_reports = PrayerReport.objects.filter(
        status=PrayerReport.STATUS_OPEN,
    ).count()
    hidden_prayers = PrayerRequest.objects.filter(is_hidden=True).count()
    open_reflection_reports = ReflectionReport.objects.filter(
        status=ReflectionReport.STATUS_OPEN,
    ).count()
    hidden_reflections = ReflectionComment.objects.filter(is_hidden=True).count()

    upcoming_service_events = ServiceEvent.objects.filter(
        start_datetime__gte=now,
    ).exclude(
        status__in=[
            ServiceEvent.STATUS_DRAFT,
            ServiceEvent.STATUS_CANCELLED,
        ],
    ).count()

    upcoming_assignments = TeamAssignment.objects.filter(
        service_event__start_datetime__gte=now,
    ).exclude(
        status__in=[
            TeamAssignment.STATUS_CANCELLED,
            TeamAssignment.STATUS_COMPLETED,
        ],
    ).count()
    upcoming_assignment_queryset = TeamAssignment.objects.filter(
        service_event__start_datetime__gte=now,
    ).exclude(
        status__in=[
            TeamAssignment.STATUS_CANCELLED,
            TeamAssignment.STATUS_COMPLETED,
        ],
    )
    unconfirmed_assignments = TeamAssignment.objects.filter(
        service_event__start_datetime__gte=now,
        assignment_members__membership__is_active=True,
        assignment_members__confirmed_at__isnull=True,
    ).exclude(
        status__in=[
            TeamAssignment.STATUS_CANCELLED,
            TeamAssignment.STATUS_COMPLETED,
        ],
    ).distinct().count()
    active_ministry_teams = MinistryTeam.objects.filter(is_active=True)
    inactive_ministry_teams = MinistryTeam.objects.filter(is_active=False).count()
    teams_missing_playbook = active_ministry_teams.filter(playbook_link="").count()
    display_name_only_members = TeamMembership.objects.filter(
        is_active=True,
        user__isnull=True,
    ).count()
    teams_without_active_members = (
        active_ministry_teams
        .annotate(
            active_member_count=Count(
                "memberships",
                filter=Q(memberships__is_active=True),
                distinct=True,
            )
        )
        .filter(active_member_count=0)
        .count()
    )
    upcoming_assignments_without_active_members = (
        upcoming_assignment_queryset
        .annotate(
            active_member_count=Count(
                "assignment_members",
                filter=Q(assignment_members__membership__is_active=True),
                distinct=True,
            )
        )
        .filter(active_member_count=0)
        .count()
    )
    upcoming_assignments_with_inactive_team = upcoming_assignment_queryset.filter(
        ministry_team__is_active=False,
    ).count()
    upcoming_events_with_required_teams = list(
        events_with_coverage_queryset()
        .filter(start_datetime__gte=now, required_team_links__isnull=False)
        .exclude(
            status__in=[
                ServiceEvent.STATUS_DRAFT,
                ServiceEvent.STATUS_CANCELLED,
            ],
        )
        .distinct()
    )
    upcoming_required_team_gaps = count_upcoming_required_team_gaps(
        upcoming_events_with_required_teams,
        list(
            assignment_coverage_queryset().filter(
                id__in=upcoming_assignment_queryset.values("id"),
            )
        ),
    )
    ministry_ops_warning_indicator_count = sum(
        [
            inactive_ministry_teams,
            teams_missing_playbook,
            display_name_only_members,
            teams_without_active_members,
            upcoming_assignments_without_active_members,
            upcoming_assignments_with_inactive_team,
            upcoming_required_team_gaps,
        ]
    )

    return render(
        request,
        "accounts/staff/overview.html",
        {
            "active_nav": "staff",
            "pending_membership_requests": pending_membership_requests,
            "draft_schedules": draft_schedules,
            "upcoming_schedules": upcoming_schedules,
            "draft_guides": draft_guides,
            "upcoming_guides": upcoming_guides,
            "draft_meetings": draft_meetings,
            "upcoming_meetings": upcoming_meetings,
            "open_prayer_reports": open_prayer_reports,
            "hidden_prayers": hidden_prayers,
            "open_reflection_reports": open_reflection_reports,
            "hidden_reflections": hidden_reflections,
            "upcoming_service_events": upcoming_service_events,
            "upcoming_assignments": upcoming_assignments,
            "unconfirmed_assignments": unconfirmed_assignments,
            "inactive_ministry_teams": inactive_ministry_teams,
            "teams_missing_playbook": teams_missing_playbook,
            "display_name_only_members": display_name_only_members,
            "teams_without_active_members": teams_without_active_members,
            "upcoming_assignments_without_active_members": (
                upcoming_assignments_without_active_members
            ),
            "upcoming_assignments_with_inactive_team": (
                upcoming_assignments_with_inactive_team
            ),
            "upcoming_required_team_gaps": upcoming_required_team_gaps,
            "ministry_ops_warning_indicator_count": ministry_ops_warning_indicator_count,
        },
    )


@staff_member_required
@require_GET
def staff_structure_map(request):
    """Church Structure Map with setup-readiness indicators (CS-MAP.2).

    The default map view is review-first: counts only, no member rosters. On
    top of that, CS-SETUP.1B adds an opt-in display-name-only edit mode for
    admin-capable staff (per-row rename + Details link); no other structure
    edits happen here. Ordinary-user matching remains consumer-specific during
    the transition: ServiceEvent audience rows now match through active primary
    ChurchStructureMembership, and zero-row ServiceEvents fail closed for
    ordinary users (the zero-row legacy fallback was retired in SE-RETIRE.1B),
    while Bible Study member visibility/generation, reading/privacy/progress,
    permissions, and My Serving remain consumer-specific as documented.
    The structure map is counts/setup context only and does not itself grant
    visibility.
    """
    language = get_user_language(request)
    today = timezone.localdate()

    units = list(
        ChurchStructureUnit.objects.filter(is_active=True).order_by(
            "sort_order",
            "code",
            "name",
        )
    )
    children = {}
    for unit in units:
        children.setdefault(unit.parent_id, []).append(unit)

    active_memberships = ChurchStructureMembership.objects.filter(
        status=ChurchStructureMembership.STATUS_ACTIVE,
        start_date__lte=today,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
    primary_memberships = list(
        active_memberships.filter(is_primary=True)
    )
    direct_primary_user_ids_by_unit = {}
    for membership in primary_memberships:
        direct_primary_user_ids_by_unit.setdefault(membership.unit_id, set()).add(
            membership.user_id
        )

    structure_rows = []
    visited = set()
    counters = {
        "direct_parent_memberships": 0,
    }

    def walk(unit, depth, ancestor_ids):
        visited.add(unit.id)
        direct_primary_user_ids = set(
            direct_primary_user_ids_by_unit.get(unit.id, set())
        )
        active_children = children.get(unit.id, [])
        direct_parent_membership_count = (
            len(direct_primary_user_ids) if active_children else 0
        )
        row = {
            "unit": unit,
            "name": unit.display_name(language),
            "depth": depth,
            "parent_id": unit.parent_id,
            "ancestor_ids": ancestor_ids,
            "has_children": bool(active_children),
            "is_root": unit.unit_type == ChurchStructureUnit.UNIT_ROOT,
            "membership_count": 0,
            "direct_parent_membership_count": direct_parent_membership_count,
        }
        structure_rows.append(row)
        if direct_parent_membership_count:
            counters["direct_parent_memberships"] += direct_parent_membership_count
        covered_user_ids = set(direct_primary_user_ids)
        for child in active_children:
            if child.id not in visited:
                child_user_ids = walk(
                    child,
                    depth + 1,
                    ancestor_ids + [unit.id],
                )
                covered_user_ids.update(child_user_ids)
        row["membership_count"] = len(covered_user_ids)
        return covered_user_ids

    roots = [unit for unit in units if unit.parent_id is None]
    roots.sort(
        key=lambda u: (
            u.unit_type != ChurchStructureUnit.UNIT_ROOT,
            u.sort_order,
            u.code,
            u.name,
        )
    )
    for root in roots:
        walk(root, 0, [])
    # Active units whose parent is inactive or missing stay visible at the end.
    for unit in units:
        if unit.id not in visited:
            walk(unit, 0, [])

    indicators = {
        "direct_parent_memberships": counters["direct_parent_memberships"],
        "active_root_units": ChurchStructureUnit.objects.filter(
            is_active=True,
            unit_type=ChurchStructureUnit.UNIT_ROOT,
        ).count(),
        "inactive_units_still_referenced": ChurchStructureUnit.objects.filter(
            is_active=False,
        )
        .filter(
            Q(bible_study_series_audience_scopes__isnull=False)
            | Q(service_event_audience_scope_links__isnull=False)
        )
        .distinct()
        .count(),
    }
    indicators.update(_structure_setup_warning_counts())

    # Edit mode is a lightweight read/write affordance layer (CS-SETUP.1B).
    # The default view stays clean and read-only; entering edit mode only
    # exposes display-name rename and a Details link, gated to staff who can
    # change ChurchStructureUnit in Django Admin. It does not change mappings,
    # membership, audience rows, tree shape, active status, or visibility.
    can_admin_units = request.user.has_perm(
        "accounts.change_churchstructureunit"
    )
    edit_mode = can_admin_units and request.GET.get("edit") == "1"

    return render(
        request,
        "accounts/staff/structure_map.html",
        {
            "active_nav": "staff",
            "structure_rows": structure_rows,
            "indicators": indicators,
            "can_admin_units": can_admin_units,
            "edit_mode": edit_mode,
        },
    )


@staff_member_required
@require_POST
def staff_structure_unit_rename(request, unit_id):
    """Rename only the display labels of a ChurchStructureUnit (CS-SETUP.1B).

    Low-risk slice: updates only ``name`` and ``name_en``. It must not touch
    parent, unit_type, code, is_active, sort_order, legacy mappings,
    memberships, or any ServiceEvent / Bible Study audience scope rows.
    """
    language = get_user_language(request)

    # Write access is at least as strict as the Django Admin change pattern
    # for structure units; staff who cannot change units there cannot rename.
    if not request.user.has_perm("accounts.change_churchstructureunit"):
        return HttpResponseForbidden("Not allowed to rename structure units.")

    unit = get_object_or_404(ChurchStructureUnit, id=unit_id)

    if unit.unit_type == ChurchStructureUnit.UNIT_ROOT:
        return HttpResponseForbidden("Root units cannot be renamed.")

    name = (request.POST.get("name") or "").strip()
    name_en = (request.POST.get("name_en") or "").strip()

    edit_url = f"{reverse('staff_structure_map')}?edit=1"

    if not name:
        messages.error(
            request,
            "请填写显示名称。" if language == "zh"
            else "Please enter a display name.",
        )
        return redirect(edit_url)

    old_name = unit.name
    old_name_en = unit.name_en

    unit.name = name
    unit.name_en = name_en
    unit.save(update_fields=["name", "name_en"])

    # Audit via Django admin LogEntry (no new model/migration in this slice).
    # Record old/new values for both display-name fields so a mistaken rename
    # can be reconstructed without a separate audit model.
    LogEntry.objects.log_action(
        user_id=request.user.pk,
        content_type_id=ContentType.objects.get_for_model(
            ChurchStructureUnit
        ).pk,
        object_id=unit.pk,
        object_repr=str(unit),
        action_flag=CHANGE,
        change_message=(
            "Renamed display name only via staff structure map "
            "(CS-SETUP.1B). "
            f"name: {old_name!r} -> {name!r}; "
            f"name_en: {old_name_en!r} -> {name_en!r}."
        ),
    )

    messages.success(
        request,
        "已更新显示名称。" if language == "zh"
        else "Display name updated.",
    )
    return redirect(edit_url)


@staff_member_required
def staff_moderation_queue(request):
    from comments.models import ReflectionComment, ReflectionReport
    from prayers.models import PrayerReport, PrayerRequest

    open_prayer_reports = (
        PrayerReport.objects
        .filter(status=PrayerReport.STATUS_OPEN)
        .select_related(
            "prayer_request",
            "prayer_request__user",
            "reporter",
        )
        .order_by("-created_at")
    )
    hidden_prayers = (
        PrayerRequest.objects
        .filter(is_hidden=True)
        .select_related("user", "hidden_by")
        .order_by("-hidden_at", "-created_at")
    )
    open_reflection_reports = (
        ReflectionReport.objects
        .filter(status=ReflectionReport.STATUS_OPEN)
        .select_related(
            "comment",
            "comment__user",
            "comment__parent",
            "comment__plan_day",
            "reporter",
        )
        .order_by("-created_at")
    )
    hidden_reflections = (
        ReflectionComment.objects
        .filter(is_hidden=True)
        .select_related("user", "parent", "plan_day", "hidden_by")
        .order_by("-hidden_at", "-created_at")
    )

    reported_reflection_posts = open_reflection_reports.filter(
        comment__parent__isnull=True,
    )
    reported_reflection_replies = open_reflection_reports.filter(
        comment__parent__isnull=False,
    )
    hidden_reflection_posts = hidden_reflections.filter(parent__isnull=True)
    hidden_reflection_replies = hidden_reflections.filter(parent__isnull=False)

    return render(
        request,
        "accounts/staff/moderation_queue.html",
        {
            "active_nav": "staff",
            "open_prayer_reports": open_prayer_reports,
            "hidden_prayers": hidden_prayers,
            "reported_reflection_posts": reported_reflection_posts,
            "reported_reflection_replies": reported_reflection_replies,
            "hidden_reflection_posts": hidden_reflection_posts,
            "hidden_reflection_replies": hidden_reflection_replies,
            "moderation_counts": {
                "reported_prayer_requests": open_prayer_reports.count(),
                "reported_prayer_comments": 0,
                "hidden_prayer_requests": hidden_prayers.count(),
                "hidden_prayer_comments": 0,
                "reported_reflection_posts": reported_reflection_posts.count(),
                "reported_reflection_replies": reported_reflection_replies.count(),
                "hidden_reflection_posts": hidden_reflection_posts.count(),
                "hidden_reflection_replies": hidden_reflection_replies.count(),
            },
        },
    )


def can_manage_church_memberships(user):
    return has_capability(user, CAP_MANAGE_CHURCH_MEMBERSHIPS)


def _active_membership_filter(prefix=""):
    field = f"{prefix}__" if prefix else ""
    today = timezone.localdate()
    return (
        Q(**{f"{field}status": ChurchStructureMembership.STATUS_ACTIVE})
        & Q(**{f"{field}start_date__lte": today})
        & (
            Q(**{f"{field}end_date__isnull": True})
            | Q(**{f"{field}end_date__gte": today})
        )
    )


def _active_membership_queryset():
    return ChurchStructureMembership.objects.filter(_active_membership_filter())


def _structure_setup_warning_counts():
    active_filter = _active_membership_filter("memberships")
    active_units_without_primary_count = (
        ChurchStructureUnit.objects.filter(is_active=True)
        .annotate(
            active_primary_count=Count(
                "memberships",
                filter=active_filter & Q(memberships__is_primary=True),
                distinct=True,
            )
        )
        .filter(active_primary_count=0)
        .count()
    )

    User = get_user_model()
    user_active_filter = _active_membership_filter("church_structure_memberships")
    users_with_multiple_primary_count = (
        User.objects.annotate(
            active_primary_count=Count(
                "church_structure_memberships",
                filter=(
                    user_active_filter
                    & Q(church_structure_memberships__is_primary=True)
                ),
                distinct=True,
            )
        )
        .filter(active_primary_count__gt=1)
        .count()
    )
    users_without_primary_count = (
        User.objects.annotate(
            active_membership_count=Count(
                "church_structure_memberships",
                filter=user_active_filter,
                distinct=True,
            ),
            active_primary_count=Count(
                "church_structure_memberships",
                filter=(
                    user_active_filter
                    & Q(church_structure_memberships__is_primary=True)
                ),
                distinct=True,
            ),
        )
        .filter(active_membership_count__gt=0, active_primary_count=0)
        .count()
    )
    inactive_units_with_active_memberships_count = (
        ChurchStructureUnit.objects.filter(is_active=False)
        .annotate(
            active_member_count=Count(
                "memberships",
                filter=active_filter,
                distinct=True,
            )
        )
        .filter(active_member_count__gt=0)
        .count()
    )

    return {
        "active_units_without_primary": active_units_without_primary_count,
        "users_with_multiple_primary": users_with_multiple_primary_count,
        "users_with_active_memberships_without_primary": users_without_primary_count,
        "inactive_units_with_active_memberships": inactive_units_with_active_memberships_count,
    }


@user_passes_test(can_manage_church_memberships)
def church_structure_unit_detail(request, unit_id):
    language = get_user_language(request)
    unit = get_object_or_404(
        ChurchStructureUnit.objects.select_related("parent"),
        id=unit_id,
    )
    add_form = StructureMembershipAddForm(unit=unit)
    active_memberships = (
        _active_membership_queryset()
        .filter(unit=unit)
        .select_related("user", "unit")
        .order_by("-is_primary", "user__username", "id")
    )
    inactive_memberships = (
        ChurchStructureMembership.objects.filter(unit=unit)
        .exclude(id__in=active_memberships.values("id"))
        .select_related("user")
        .order_by("-updated_at", "user__username", "id")[:20]
    )
    children = unit.children.order_by("sort_order", "code", "name", "id")

    return render(
        request,
        "accounts/staff/church_structure_unit_detail.html",
        {
            "active_nav": "staff",
            "unit": unit,
            "unit_path": unit.path_label(language),
            "children": children,
            "active_memberships": active_memberships,
            "inactive_memberships": inactive_memberships,
            "add_form": add_form,
        },
    )


@user_passes_test(can_manage_church_memberships)
@require_POST
def add_structure_membership(request, unit_id):
    unit = get_object_or_404(ChurchStructureUnit, id=unit_id)
    form = StructureMembershipAddForm(request.POST, unit=unit)
    if form.is_valid():
        membership = form.save(approved_by=request.user)
        messages.success(
            request,
            f"Added active membership for {membership.user.username}.",
        )
    else:
        messages.error(request, "Membership was not added. Please review the form.")
    return redirect("church_structure_unit_detail", unit_id=unit.id)


@user_passes_test(can_manage_church_memberships)
@require_POST
def end_structure_membership(request, membership_id):
    membership = get_object_or_404(
        ChurchStructureMembership.objects.select_related("unit", "user"),
        id=membership_id,
    )
    today = timezone.localdate()
    membership.status = ChurchStructureMembership.STATUS_ENDED
    membership.is_primary = False
    if not membership.end_date:
        membership.end_date = today
    membership.save()
    messages.success(
        request,
        f"Ended membership for {membership.user.username}.",
    )
    return redirect("church_structure_unit_detail", unit_id=membership.unit_id)


@user_passes_test(can_manage_church_memberships)
@require_POST
def set_primary_structure_membership(request, membership_id):
    membership = get_object_or_404(
        ChurchStructureMembership.objects.select_related("unit", "user"),
        id=membership_id,
    )
    if not membership.is_active_membership or not membership.unit.is_active:
        messages.error(request, "Only active memberships on active units can be primary.")
        return redirect("church_structure_unit_detail", unit_id=membership.unit_id)

    with transaction.atomic():
        ChurchStructureMembership.objects.filter(
            user=membership.user,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
        ).exclude(id=membership.id).update(is_primary=False)
        membership.is_primary = True
        membership.save(update_fields=["is_primary", "updated_at"])

    messages.success(
        request,
        f"Set primary membership for {membership.user.username}.",
    )
    return redirect("church_structure_unit_detail", unit_id=membership.unit_id)

def signup(request):
    language = get_user_language(request)
    ui = UI_TEXT[language]

    if request.method == "POST":
        form = SignUpForm(request.POST, request=request)

        if form.is_valid():
            requested_unit = form.cleaned_data.get("requested_unit")
            user = form.save()
            login(request, user)
            set_user_language(request, language)
            message_key = (
                "account_created_with_group_request"
                if requested_unit else "account_created"
            )
            messages.success(request, ui[message_key])
            return redirect("home")
    else:
        form = SignUpForm(request=request)

    return render(request, "registration/signup.html", {"form": form})


def change_language(request):
    if request.method != "POST":
        return redirect("home")

    language = request.POST.get("language", "zh")
    set_user_language(request, language)

    next_url = request.POST.get("next")

    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
    ):
        return redirect(next_url)

    return redirect("home")

@login_required
def profile(request):
    language = get_user_language(request)
    pending_group_request = (
        ChurchStructureMembership.objects
        .filter(
            user=request.user,
            status=ChurchStructureMembership.STATUS_REQUESTED,
        )
        .select_related("unit", "unit__parent")
        .order_by("-updated_at", "-created_at", "id")
        .first()
    )
    pending_group_request_label = (
        pending_group_request.unit.path_label(language)
        if pending_group_request else ""
    )

    if request.method == "POST":
        form = ProfileForm(request.POST, user=request.user, request=request)

        if form.is_valid():
            requested_unit = form.cleaned_data.get("requested_unit")
            profile_obj = form.save()
            set_user_language(request, profile_obj.preferred_language)
            ui = UI_TEXT[profile_obj.preferred_language]
            message_key = (
                "profile_saved_with_group_request"
                if requested_unit else "profile_saved"
            )
            messages.success(request, ui[message_key])
            return redirect("profile")
    else:
        form = ProfileForm(user=request.user, request=request)

    # CS-RETIRE.1A: the user's "current confirmed group" display is the active
    # primary ChurchStructureMembership (the source of truth). The legacy
    # Profile.small_group field was removed in PROFILE-SG-FIELD-RETIRE.1A. No
    # membership => the no-group state.
    active_primary_membership = ChurchStructureMembership.current_primary_for_user(
        request.user,
    )
    active_primary_membership_label = (
        active_primary_membership.unit.path_label(language)
        if active_primary_membership
        else ""
    )

    return render(
        request,
        "accounts/profile.html",
        {
            "form": form,
            "pending_group_request": pending_group_request,
            "pending_group_request_label": pending_group_request_label,
            "active_primary_membership": active_primary_membership,
            "active_primary_membership_label": active_primary_membership_label,
        },
    )

class ProfilePasswordChangeView(PasswordChangeView):
    form_class = LocalizedPasswordChangeForm
    template_name = "accounts/password_change_form.html"
    success_url = reverse_lazy("password_change_done")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)

        profile, _ = Profile.objects.get_or_create(user=self.request.user)

        if profile.must_change_password:
            profile.must_change_password = False
            profile.save(update_fields=["must_change_password"])

        return response


@staff_member_required
def staff_user_list(request):
    User = get_user_model()

    query = (request.GET.get("q") or "").strip()

    users = (
        User.objects
        .select_related("profile")
        .order_by("username")
    )

    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
        ).distinct()

    return render(
        request,
        "accounts/staff/user_list.html",
        {
            "users": users,
            "query": query,
        },
    )


@staff_member_required
def staff_user_password_reset(request, user_id):
    User = get_user_model()

    target_user = get_object_or_404(
        User.objects.select_related("profile"),
        id=user_id,
    )

    ui = UI_TEXT[get_user_language(request)]

    if request.method == "POST":
        form = StaffPasswordResetForm(target_user, request.POST, request=request)

        if form.is_valid():
            form.save()

            profile, _ = Profile.objects.get_or_create(user=target_user)
            profile.must_change_password = form.cleaned_data.get(
                "require_password_change",
                False,
            )
            profile.save(update_fields=["must_change_password"])

            messages.success(
                request,
                ui["password_reset_done"].format(username=target_user.username),
            )

            return redirect("staff_user_list")
    else:
        form = StaffPasswordResetForm(target_user, request=request)

    return render(
        request,
        "accounts/staff/password_reset.html",
        {
            "target_user": target_user,
            "form": form,
        },
    )


@user_passes_test(can_manage_church_memberships)
def staff_membership_request_list(request):
    memberships = (
        ChurchStructureMembership.objects
        .filter(status=ChurchStructureMembership.STATUS_REQUESTED)
        .select_related(
            "user",
            "user__profile",
            "unit",
            "unit__parent",
            "requested_by",
        )
        .order_by("-created_at", "user__username", "id")
    )
    language = get_user_language(request)
    membership_rows = [
        {
            "membership": membership,
            "unit_path": membership.unit.path_label(language),
        }
        for membership in memberships
    ]
    status_summary = {
        "requested": len(membership_rows),
    }

    return render(
        request,
        "accounts/staff/membership_request_list.html",
        {
            "membership_rows": membership_rows,
            "status_summary": status_summary,
        },
    )


def get_requested_membership_or_404(membership_id):
    return get_object_or_404(
        ChurchStructureMembership.objects.select_related(
            "user",
            "user__profile",
            "unit",
            "unit__parent",
            "requested_by",
        ),
        id=membership_id,
        status=ChurchStructureMembership.STATUS_REQUESTED,
    )


@user_passes_test(can_manage_church_memberships)
def staff_membership_request_detail(request, membership_id):
    membership = get_requested_membership_or_404(membership_id)
    language = get_user_language(request)
    active_primary = ChurchStructureMembership.current_primary_for_user(
        membership.user,
    )

    # CS-RETIRE.1A: approval no longer writes any legacy profile group; the
    # legacy Profile.small_group field was removed in PROFILE-SG-FIELD-RETIRE.1A.
    # There is no "sync target" and no sync-on-approval warning, because the
    # active primary ChurchStructureMembership is the source of truth.
    return render(
        request,
        "accounts/staff/membership_request_detail.html",
        {
            "membership": membership,
            "unit_path": membership.unit.path_label(language),
            "active_primary": active_primary,
            "active_primary_path": (
                active_primary.unit.path_label(language) if active_primary else ""
            ),
        },
    )


@user_passes_test(can_manage_church_memberships)
def staff_membership_request_approve(request, membership_id):
    if request.method != "POST":
        return redirect("staff_membership_request_detail", membership_id=membership_id)

    membership = get_requested_membership_or_404(membership_id)
    active_primary = ChurchStructureMembership.current_primary_for_user(
        membership.user,
    )

    if active_primary:
        messages.error(
            request,
            "Approval blocked: this user already has an active future primary membership.",
        )
        return redirect("staff_membership_request_detail", membership_id=membership.id)

    membership.status = ChurchStructureMembership.STATUS_ACTIVE
    membership.is_primary = True
    if not membership.membership_type:
        membership.membership_type = ChurchStructureMembership.TYPE_SMALL_GROUP_MEMBER
    if not membership.start_date:
        membership.start_date = timezone.localdate()
    membership.approved_by = request.user
    membership.approved_at = timezone.now()
    membership.save()

    # CS-RETIRE.1A: the approved ChurchStructureMembership is the source of truth
    # for belonging. The legacy Profile.small_group field was removed in
    # PROFILE-SG-FIELD-RETIRE.1A, so there is no legacy profile group to mirror.
    messages.success(
        request,
        (
            "Group request approved as the user's active primary church-structure "
            "membership."
        ),
    )
    return redirect("staff_membership_request_list")


@user_passes_test(can_manage_church_memberships)
def staff_membership_request_reject(request, membership_id):
    if request.method != "POST":
        return redirect("staff_membership_request_detail", membership_id=membership_id)

    membership = get_requested_membership_or_404(membership_id)
    membership.status = ChurchStructureMembership.STATUS_REJECTED
    membership.is_primary = False
    membership.save()

    messages.success(request, "Group request declined.")
    return redirect("staff_membership_request_list")
