from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import PasswordChangeView
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET


from .forms import (
    LocalizedPasswordChangeForm,
    ProfileForm,
    SignUpForm,
    StaffPasswordResetForm,
)
from .language import get_user_language, set_user_language
from .ui_text import UI_TEXT
from .models import (
    ChurchStructureMembership,
    ChurchStructureUnit,
    District,
    MinistryContext,
    Profile,
    SmallGroup,
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
    """Read-only Church Structure Map with setup-readiness indicators (CS-MAP.2).

    Counts only; no member rosters and no write actions. The unit tree and
    membership rows shown here are the future structure foundation. Runtime
    visibility still uses the legacy structure models and Profile.small_group.
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

    # Active legacy rows that reference a unit: display context per row, and
    # the reference set for the "no linked current records" indicator.
    legacy_rows = [
        *MinistryContext.objects.filter(
            is_active=True, church_structure_unit__isnull=False
        ),
        *District.objects.filter(
            is_active=True, church_structure_unit__isnull=False
        ),
        *SmallGroup.objects.filter(
            is_active=True, church_structure_unit__isnull=False
        ),
    ]
    legacy_names_by_unit = {}
    mapped_unit_ids = set()
    for legacy_row in legacy_rows:
        mapped_unit_ids.add(legacy_row.church_structure_unit_id)
        legacy_names_by_unit.setdefault(
            legacy_row.church_structure_unit_id, []
        ).append(str(legacy_row))

    active_memberships = ChurchStructureMembership.objects.filter(
        status=ChurchStructureMembership.STATUS_ACTIVE,
        start_date__lte=today,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
    primary_memberships = list(
        active_memberships.filter(is_primary=True).select_related(
            "user__profile__small_group",
        )
    )
    direct_primary_user_ids_by_unit = {}
    for membership in primary_memberships:
        direct_primary_user_ids_by_unit.setdefault(membership.unit_id, set()).add(
            membership.user_id
        )

    holding_codes = {"UNASSIGNED-DISTRICTS", "UNASSIGNED-GROUPS"}
    structure_rows = []
    visited = set()
    counters = {
        "under_holding": 0,
        "without_linked_records": 0,
        "direct_parent_memberships": 0,
    }

    def walk(unit, depth, under_holding, ancestor_ids):
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
            "membership_count": 0,
            "direct_parent_membership_count": direct_parent_membership_count,
            "legacy_names": legacy_names_by_unit.get(unit.id, []),
            "under_holding": under_holding,
            "without_linked_records": False,
        }
        structure_rows.append(row)
        if under_holding:
            counters["under_holding"] += 1
        if direct_parent_membership_count:
            counters["direct_parent_memberships"] += direct_parent_membership_count
        subtree_mapped = unit.id in mapped_unit_ids
        covered_user_ids = set(direct_primary_user_ids)
        child_under_holding = under_holding or unit.code in holding_codes
        for child in active_children:
            if child.id not in visited:
                child_mapped, child_user_ids = walk(
                    child,
                    depth + 1,
                    child_under_holding,
                    ancestor_ids + [unit.id],
                )
                if child_mapped:
                    subtree_mapped = True
                covered_user_ids.update(child_user_ids)
        if not subtree_mapped and unit.unit_type != ChurchStructureUnit.UNIT_ROOT:
            row["without_linked_records"] = True
            counters["without_linked_records"] += 1
        row["membership_count"] = len(covered_user_ids)
        return subtree_mapped, covered_user_ids

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
        walk(root, 0, False, [])
    # Active units whose parent is inactive or missing stay visible at the end.
    for unit in units:
        if unit.id not in visited:
            walk(unit, 0, False, [])

    # Drift between the current runtime group and the approved active primary
    # membership. Categories are reported separately and may overlap with the
    # unmapped-group indicator; an unmapped current group counts as a mismatch
    # because it cannot agree with any membership unit.
    membership_without_group = 0
    membership_group_mismatch = 0
    primary_user_ids = set()
    for membership in primary_memberships:
        primary_user_ids.add(membership.user_id)
        profile = getattr(membership.user, "profile", None)
        group = getattr(profile, "small_group", None)
        if group is None:
            membership_without_group += 1
        elif group.church_structure_unit_id != membership.unit_id:
            membership_group_mismatch += 1
    group_without_membership = (
        Profile.objects.filter(small_group__isnull=False)
        .exclude(user_id__in=primary_user_ids)
        .count()
    )

    indicators = {
        "unmapped_ministry_contexts": MinistryContext.objects.filter(
            is_active=True,
            church_structure_unit__isnull=True,
        ).count(),
        "unmapped_districts": District.objects.filter(
            is_active=True,
            church_structure_unit__isnull=True,
        ).count(),
        "unmapped_small_groups": SmallGroup.objects.filter(
            is_active=True,
            church_structure_unit__isnull=True,
        ).count(),
        "units_without_linked_records": counters["without_linked_records"],
        "units_under_holding": counters["under_holding"],
        "direct_parent_memberships": counters["direct_parent_memberships"],
        "users_in_unmapped_group": Profile.objects.filter(
            small_group__isnull=False,
            small_group__church_structure_unit__isnull=True,
        ).count(),
        "membership_without_group": membership_without_group,
        "group_without_membership": group_without_membership,
        "membership_group_mismatch": membership_group_mismatch,
        "active_root_units": ChurchStructureUnit.objects.filter(
            is_active=True,
            unit_type=ChurchStructureUnit.UNIT_ROOT,
        ).count(),
        "inactive_units_still_referenced": ChurchStructureUnit.objects.filter(
            is_active=False,
        )
        .filter(
            Q(legacy_ministry_contexts__isnull=False)
            | Q(legacy_districts__isnull=False)
            | Q(legacy_small_groups__isnull=False)
            | Q(bible_study_series_audience_scopes__isnull=False)
            | Q(service_event_audience_scope_links__isnull=False)
        )
        .distinct()
        .count(),
    }

    return render(
        request,
        "accounts/staff/structure_map.html",
        {
            "active_nav": "staff",
            "structure_rows": structure_rows,
            "indicators": indicators,
        },
    )


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

    return render(
        request,
        "accounts/profile.html",
        {
            "form": form,
            "pending_group_request": pending_group_request,
            "pending_group_request_label": pending_group_request_label,
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
        .select_related("profile", "profile__small_group")
        .order_by("username")
    )

    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(profile__small_group__name__icontains=query)
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
        User.objects.select_related("profile", "profile__small_group"),
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
            "user__profile__small_group",
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
            "user__profile__small_group",
            "unit",
            "unit__parent",
            "requested_by",
        ),
        id=membership_id,
        status=ChurchStructureMembership.STATUS_REQUESTED,
    )


def _get_single_active_legacy_small_group_for_unit(unit):
    groups = list(
        SmallGroup.objects.filter(
            church_structure_unit=unit,
            is_active=True,
        )[:2]
    )
    if len(groups) == 1:
        return groups[0]
    return None


@user_passes_test(can_manage_church_memberships)
def staff_membership_request_detail(request, membership_id):
    membership = get_requested_membership_or_404(membership_id)
    language = get_user_language(request)
    active_primary = ChurchStructureMembership.current_primary_for_user(
        membership.user,
    )
    mapped_legacy_small_group = _get_single_active_legacy_small_group_for_unit(
        membership.unit,
    )
    current_small_group = membership.user.profile.small_group
    show_profile_sync_warning = bool(
        mapped_legacy_small_group
        and current_small_group
        and current_small_group != mapped_legacy_small_group
    )

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
            "mapped_legacy_small_group": mapped_legacy_small_group,
            "show_profile_sync_warning": show_profile_sync_warning,
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

    mapped_legacy_small_group = None
    if (
        membership.status == ChurchStructureMembership.STATUS_ACTIVE
        and membership.is_primary
    ):
        mapped_legacy_small_group = _get_single_active_legacy_small_group_for_unit(
            membership.unit,
        )

    if mapped_legacy_small_group:
        profile, _ = Profile.objects.get_or_create(user=membership.user)
        profile.small_group = mapped_legacy_small_group
        profile.save(update_fields=["small_group"])
        messages.success(
            request,
            (
                "Group request confirmed. Current runtime small group updated to "
                f"{mapped_legacy_small_group.name}."
            ),
        )
    else:
        messages.warning(
            request,
            (
                "Group request confirmed. Current runtime small group was not "
                "changed because there is not exactly one active mapped small group."
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
