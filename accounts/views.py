from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import PasswordChangeView
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST


from .forms import (
    ChurchStructureUnitChildForm,
    LocalizedPasswordChangeForm,
    ProfileForm,
    SignUpForm,
    StaffPasswordResetForm,
    StructureMembershipAddForm,
    StructureUnitCoworkerAssignmentForm,
    StructureUnitRoleProfileForm,
    coworker_assignment_local_user_queryset,
)
from .language import get_user_language, set_user_language
from .ui_text import UI_TEXT
from .models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
    ChurchStructureUnitRoleAssignment,
    ChurchStructureUnitRoleProfile,
    ChurchStructureUnitRoleType,
    Profile,
)
from .ordering import (
    order_by_related_user_visible_identity,
    order_units_by_sibling_key,
    order_users_by_visible_identity,
    structure_unit_sibling_sort_key,
)
from .permissions import CAP_MANAGE_CHURCH_MEMBERSHIPS, has_capability
from .serving_readiness import add_serving_readiness_warnings
from .unit_management import (
    can_manage_unit_coworkers,
    get_manageable_structure_units,
)


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

    The default map view is review-first: counts only, no member rosters.
    Edit mode is gated to users who can change ChurchStructureUnit and exposes
    rename, sibling sort-order edits, same-parent bulk sibling ordering,
    add-child, safe soft-disable, inactive-unit review/re-enable, and
    detail/admin links. Membership maintenance lives on the unit detail page.

    Edit mode does not hard-delete units, move/reparent units,
    cascade-disable/re-enable children, automatically end/create memberships,
    rewrite audience or role scopes, change serving assignments, change
    visibility semantics, or infer leadership/serving from membership.
    Ordinary-user matching remains consumer-specific as documented; the
    structure map is counts/setup context only and does not itself grant
    visibility.
    """
    language = get_user_language(request)
    today = timezone.localdate()

    units = list(
        order_units_by_sibling_key(
            ChurchStructureUnit.objects.filter(is_active=True),
            language,
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
            *structure_unit_sibling_sort_key(u, language),
        )
    )
    for root in roots:
        walk(root, 0, [])
    # Active units whose parent is inactive or missing stay visible at the end.
    for unit in units:
        if unit.id not in visited:
            walk(unit, 0, [])

    sibling_groups = {}
    parent_names = {
        unit.id: unit.display_name(language)
        for unit in units
    }
    for row in structure_rows:
        sibling_groups.setdefault(row["parent_id"], []).append(
            {
                "id": row["unit"].id,
                "name": row["name"],
            }
        )
        row["sibling_order_parent_key"] = (
            str(row["parent_id"]) if row["parent_id"] else "root"
        )
        row["sibling_order_index"] = 0
        row["sibling_order_count"] = 1
        row["can_order_up"] = False
        row["can_order_down"] = False
        row["shows_sibling_order_form"] = False
        row["sibling_order_units"] = []
        row["sibling_order_parent_label"] = ""

    rows_by_unit_id = {
        row["unit"].id: row
        for row in structure_rows
    }
    for sibling_units in sibling_groups.values():
        sibling_count = len(sibling_units)
        for index, sibling_unit in enumerate(sibling_units):
            row = rows_by_unit_id[sibling_unit["id"]]
            row["sibling_order_index"] = index
            row["sibling_order_count"] = sibling_count
            row["can_order_up"] = index > 0
            row["can_order_down"] = index < sibling_count - 1

    seen_parent_ids = set()
    for row in structure_rows:
        parent_id = row["parent_id"]
        sibling_units = sibling_groups.get(parent_id, [])
        if parent_id in seen_parent_ids or len(sibling_units) < 2:
            continue
        seen_parent_ids.add(parent_id)
        row["shows_sibling_order_form"] = True
        row["sibling_order_units"] = sibling_units
        if parent_id:
            row["sibling_order_parent_label"] = parent_names.get(parent_id) or (
                "上级单元" if language == "zh" else "Parent unit"
            )
        else:
            row["sibling_order_parent_label"] = (
                "顶层" if language == "zh" else "Root level"
            )

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
    active_units = ChurchStructureUnit.objects.filter(is_active=True)
    active_units_without_role_profile = active_units.filter(
        role_profile__isnull=True,
    ).count()
    active_units_with_missing_required_coworker_roles = sum(
        1
        for unit in active_units.filter(role_profile__isnull=False).select_related(
            "role_profile",
        )
        if unit.missing_required_role_types(today)
    )
    indicators.update(
        {
            "active_units_without_role_profile": active_units_without_role_profile,
            "active_units_with_missing_required_coworker_roles": (
                active_units_with_missing_required_coworker_roles
            ),
            "coworker_role_profiles_count": (
                ChurchStructureUnitRoleProfile.objects.count()
            ),
            "coworker_role_types_count": ChurchStructureUnitRoleType.objects.count(),
        }
    )

    # Edit mode is a lightweight read/write affordance layer. The default view
    # stays review-first and read-only; entering edit mode exposes rename,
    # sibling sort-order edits, same-parent bulk sibling ordering, add-child,
    # safe soft-disable, and detail/admin links to users who can change
    # ChurchStructureUnit. It does not hard-delete, move/reparent,
    # cascade-disable, auto-end memberships, rewrite audience/role scopes,
    # change serving or visibility semantics, or infer leadership/serving from
    # membership.
    can_admin_units = request.user.has_perm(
        "accounts.change_churchstructureunit"
    )
    edit_mode = can_admin_units and request.GET.get("edit") == "1"
    inactive_unit_count = ChurchStructureUnit.objects.filter(
        is_active=False,
    ).count()
    inactive_unit_rows = (
        _inactive_structure_unit_rows(language) if edit_mode else []
    )

    return render(
        request,
        "accounts/staff/structure_map.html",
        {
            "active_nav": "staff",
            "structure_rows": structure_rows,
            "indicators": indicators,
            "inactive_unit_rows": inactive_unit_rows,
            "inactive_unit_count": inactive_unit_count,
            "can_admin_units": can_admin_units,
            "child_unit_type_choices": [
                choice
                for choice in ChurchStructureUnit.UNIT_TYPE_CHOICES
                if choice[0] != ChurchStructureUnit.UNIT_ROOT
            ],
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


def can_change_church_structure_units(user):
    return (
        getattr(user, "is_authenticated", False)
        and user.has_perm("accounts.change_churchstructureunit")
    )


def _staff_structure_edit_url():
    return f"{reverse('staff_structure_map')}?edit=1"


def _staff_structure_order_siblings_error(request, language):
    messages.error(
        request,
        (
            "排序保存失败；只能重排同一上级下的启用单元。"
            if language == "zh"
            else "Order was not saved. Only active siblings under the same parent can be reordered."
        ),
    )
    return redirect(_staff_structure_edit_url())


@staff_member_required
@user_passes_test(can_change_church_structure_units)
@require_POST
def staff_structure_unit_update_sort_order(request, unit_id):
    language = get_user_language(request)
    raw_sort_order = (request.POST.get("sort_order") or "").strip()

    try:
        sort_order = int(raw_sort_order)
    except (TypeError, ValueError):
        messages.error(
            request,
            "排序必须是整数。" if language == "zh"
            else "Sort order must be an integer.",
        )
        return redirect(_staff_structure_edit_url())

    if sort_order < 0:
        messages.error(
            request,
            "排序必须是整数。" if language == "zh"
            else "Sort order must be an integer.",
        )
        return redirect(_staff_structure_edit_url())

    with transaction.atomic():
        unit = get_object_or_404(
            ChurchStructureUnit.objects.select_for_update(),
            id=unit_id,
        )
        old_sort_order = unit.sort_order
        unit.sort_order = sort_order
        unit.save(update_fields=["sort_order", "updated_at"])
        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=ContentType.objects.get_for_model(
                ChurchStructureUnit
            ).pk,
            object_id=unit.pk,
            object_repr=str(unit),
            action_flag=CHANGE,
            change_message=(
                "Updated structure unit sort_order via staff structure map "
                "(STRUCTURE-TREE-ORDER-UI.1D). "
                f"sort_order: {old_sort_order!r} -> {sort_order!r}. "
                "No parent, child, membership, audience scope, role scope, "
                "serving assignment, or visibility data was changed."
            ),
        )

    messages.success(
        request,
        "结构单元排序已更新。" if language == "zh"
        else "Structure unit order updated.",
    )
    return redirect(_staff_structure_edit_url())


@staff_member_required
@user_passes_test(can_change_church_structure_units)
@require_POST
def staff_structure_units_order_siblings(request):
    language = get_user_language(request)
    raw_parent_id = (request.POST.get("parent_id") or "").strip()
    raw_unit_ids = request.POST.getlist("unit_ids")

    if raw_parent_id in ("", "root"):
        parent = None
        parent_id = None
    else:
        try:
            parent_id = int(raw_parent_id)
        except (TypeError, ValueError):
            return _staff_structure_order_siblings_error(request, language)

        parent = ChurchStructureUnit.objects.filter(id=parent_id).first()
        if parent is None:
            return _staff_structure_order_siblings_error(request, language)

    try:
        ordered_unit_ids = [int(unit_id) for unit_id in raw_unit_ids]
    except (TypeError, ValueError):
        return _staff_structure_order_siblings_error(request, language)

    if not ordered_unit_ids or len(ordered_unit_ids) != len(set(ordered_unit_ids)):
        return _staff_structure_order_siblings_error(request, language)

    with transaction.atomic():
        units = list(
            ChurchStructureUnit.objects.select_for_update().filter(
                id__in=ordered_unit_ids
            )
        )
        if len(units) != len(ordered_unit_ids):
            return _staff_structure_order_siblings_error(request, language)

        units_by_id = {unit.id: unit for unit in units}
        if any(not unit.is_active for unit in units):
            return _staff_structure_order_siblings_error(request, language)

        if any(unit.parent_id != parent_id for unit in units):
            return _staff_structure_order_siblings_error(request, language)

        active_sibling_ids = set(
            ChurchStructureUnit.objects.filter(
                parent_id=parent_id,
                is_active=True,
            ).values_list("id", flat=True)
        )
        if set(ordered_unit_ids) != active_sibling_ids:
            return _staff_structure_order_siblings_error(request, language)

        old_new_parts = []
        for index, unit_id in enumerate(ordered_unit_ids, start=1):
            unit = units_by_id[unit_id]
            old_sort_order = unit.sort_order
            new_sort_order = index * 10
            old_new_parts.append(f"{unit_id}: {old_sort_order!r} -> {new_sort_order!r}")
            if old_sort_order != new_sort_order:
                unit.sort_order = new_sort_order
                unit.save(update_fields=["sort_order"])

        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=ContentType.objects.get_for_model(
                ChurchStructureUnit
            ).pk,
            object_id=parent.pk if parent else None,
            object_repr=str(parent) if parent else "Root-level structure units",
            action_flag=CHANGE,
            change_message=(
                "Reordered same-parent structure unit siblings via staff "
                "structure map (STRUCTURE-TREE-ORDER-DRAG.1E). "
                f"parent_id={parent_id!r}; ordered_unit_ids={ordered_unit_ids!r}; "
                f"sort_order changes: {'; '.join(old_new_parts)}. "
                "Only sibling sort_order values were changed; no parent, "
                "child, membership, audience scope, role scope, serving "
                "assignment, or visibility data was changed."
            ),
        )

    messages.success(
        request,
        "同层排序已保存。" if language == "zh" else "Sibling order saved.",
    )
    return redirect(_staff_structure_edit_url())


@user_passes_test(can_change_church_structure_units)
@require_POST
def staff_structure_unit_add_child(request, parent_id):
    language = get_user_language(request)
    parent = get_object_or_404(ChurchStructureUnit, id=parent_id)
    form = ChurchStructureUnitChildForm(request.POST, parent=parent)

    if form.is_valid():
        unit = form.save()
        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=ContentType.objects.get_for_model(
                ChurchStructureUnit
            ).pk,
            object_id=unit.pk,
            object_repr=str(unit),
            action_flag=ADDITION,
            change_message=(
                "Created child structure unit via staff structure map "
                "(STRUCTURE-SETUP-ACTIONS.1A). "
                f"parent_id={parent.pk!r}; code={unit.code!r}."
            ),
        )
        messages.success(
            request,
            "已新增下级单元。" if language == "zh"
            else "Child unit added.",
        )
    else:
        messages.error(
            request,
            "无法新增下级单元，请检查表单。" if language == "zh"
            else "Child unit was not added. Please review the form.",
        )

    return redirect(_staff_structure_edit_url())


def _structure_unit_disable_blockers(unit):
    from comments.models import ReflectionComment
    from events.models import ServiceEvent
    from prayers.models import PrayerRequest
    from studies.models import (
        BibleStudyMeeting,
        BibleStudySeries,
    )

    blockers = []

    if unit.unit_type == ChurchStructureUnit.UNIT_ROOT:
        blockers.append("root_unit")

    if unit.children.filter(is_active=True).exists():
        blockers.append("active_child_units")

    if _active_membership_queryset().filter(unit=unit).exists():
        blockers.append("active_memberships")

    if unit.role_assignments.filter(is_active=True).exists():
        blockers.append("active_role_scopes")

    if unit.service_event_audience_scope_links.exclude(
        service_event__status=ServiceEvent.STATUS_CANCELLED,
    ).exists():
        blockers.append("service_event_audience_scopes")

    if unit.host_language_service_events.exclude(
        status=ServiceEvent.STATUS_CANCELLED,
    ).exists():
        blockers.append("service_event_host_language_refs")

    if unit.bible_study_series_audience_scopes.exclude(
        series__status=BibleStudySeries.STATUS_CANCELLED,
    ).exists():
        blockers.append("bible_study_schedule_audience_scopes")

    if unit.bible_study_meeting_audience_scopes.exclude(
        meeting__status=BibleStudyMeeting.STATUS_CANCELLED,
    ).exists():
        blockers.append("bible_study_meeting_audience_scopes")

    if unit.anchored_bible_study_meetings.exclude(
        status=BibleStudyMeeting.STATUS_CANCELLED,
    ).exists():
        blockers.append("bible_study_meeting_anchors")

    if PrayerRequest.objects.filter(
        structure_unit_at_post=unit,
        is_deleted=False,
    ).exists():
        blockers.append("prayer_snapshots")

    if ReflectionComment.objects.filter(
        structure_unit_at_post=unit,
        is_deleted=False,
    ).exists():
        blockers.append("reflection_snapshots")

    return blockers


def _structure_unit_disable_blocker_labels(blockers, language):
    labels = {
        "root_unit": {
            "en": "root unit",
            "zh": "全教会根单元",
        },
        "active_child_units": {
            "en": "active child units",
            "zh": "启用中的下级单元",
        },
        "active_memberships": {
            "en": "active memberships",
            "zh": "启用中的归属记录",
        },
        "active_role_scopes": {
            "en": "active role scopes",
            "zh": "启用中的职分范围",
        },
        "service_event_audience_scopes": {
            "en": "ServiceEvent audience scopes",
            "zh": "教会聚会适用范围",
        },
        "service_event_host_language_refs": {
            "en": "ServiceEvent host/language display refs",
            "zh": "教会聚会主办/语言显示引用",
        },
        "bible_study_schedule_audience_scopes": {
            "en": "Bible Study schedule audience scopes",
            "zh": "查经安排适用范围",
        },
        "bible_study_meeting_audience_scopes": {
            "en": "Bible Study meeting audience scopes",
            "zh": "查经聚会适用范围",
        },
        "bible_study_meeting_anchors": {
            "en": "Bible Study meeting anchors",
            "zh": "查经聚会归属单元",
        },
        "prayer_snapshots": {
            "en": "prayer snapshots",
            "zh": "代祷归属快照",
        },
        "reflection_snapshots": {
            "en": "reflection snapshots",
            "zh": "默想归属快照",
        },
    }
    key = "zh" if language == "zh" else "en"
    return [labels.get(blocker, {}).get(key, blocker) for blocker in blockers]


def _structure_unit_enable_blockers(unit):
    blockers = []

    if unit.parent_id and unit.parent and not unit.parent.is_active:
        blockers.append("inactive_parent")

    if (
        unit.unit_type == ChurchStructureUnit.UNIT_ROOT
        and ChurchStructureUnit.objects.filter(
            is_active=True,
            unit_type=ChurchStructureUnit.UNIT_ROOT,
        )
        .exclude(id=unit.id)
        .exists()
    ):
        blockers.append("multiple_active_roots")

    return blockers


def _structure_unit_enable_blocker_labels(blockers, language):
    labels = {
        "inactive_parent": {
            "en": "parent unit is inactive",
            "zh": "上级单元已停用",
        },
        "multiple_active_roots": {
            "en": "another active root unit already exists",
            "zh": "已经有另一个启用的全教会根单元",
        },
        "validation_error": {
            "en": "model validation did not pass",
            "zh": "模型验证未通过",
        },
    }
    key = "zh" if language == "zh" else "en"
    return [labels.get(blocker, {}).get(key, blocker) for blocker in blockers]


def _inactive_structure_unit_rows(language):
    active_filter = _active_membership_filter("memberships")
    inactive_units = (
        order_units_by_sibling_key(
            ChurchStructureUnit.objects.filter(is_active=False),
            language,
        )
        .select_related("parent")
        .annotate(
            active_membership_count=Count(
                "memberships",
                filter=active_filter,
                distinct=True,
            )
        )
    )
    rows = []
    reference_blocker_keys = {
        "active_role_scopes",
        "service_event_audience_scopes",
        "service_event_host_language_refs",
        "bible_study_schedule_audience_scopes",
        "bible_study_meeting_audience_scopes",
        "bible_study_meeting_anchors",
        "prayer_snapshots",
        "reflection_snapshots",
    }

    for unit in inactive_units:
        disable_blockers = _structure_unit_disable_blockers(unit)
        reference_blockers = [
            blocker
            for blocker in disable_blockers
            if blocker in reference_blocker_keys
        ]
        enable_blockers = _structure_unit_enable_blockers(unit)
        rows.append(
            {
                "unit": unit,
                "name": unit.display_name(language),
                "path": unit.path_label(language),
                "parent_name": unit.parent.display_name(language)
                if unit.parent else "",
                "active_membership_count": unit.active_membership_count,
                "reference_warning_count": len(reference_blockers),
                "reference_warning_labels": _structure_unit_disable_blocker_labels(
                    reference_blockers,
                    language,
                ),
                "can_enable": not enable_blockers,
                "enable_blocker_labels": _structure_unit_enable_blocker_labels(
                    enable_blockers,
                    language,
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            (row["path"] or "").casefold(),
            row["unit"].sort_order,
            (row["name"] or "").casefold(),
            row["unit"].code or "",
            row["unit"].id or 0,
        )
    )
    return rows


@user_passes_test(can_change_church_structure_units)
@require_POST
def staff_structure_unit_disable(request, unit_id):
    language = get_user_language(request)

    if request.POST.get("confirm_disable") != "on":
        messages.error(
            request,
            "请先确认停用。" if language == "zh"
            else "Please confirm before disabling the unit.",
        )
        return redirect(_staff_structure_edit_url())

    with transaction.atomic():
        unit = get_object_or_404(
            ChurchStructureUnit.objects.select_for_update(),
            id=unit_id,
        )
        if not unit.is_active:
            messages.warning(
                request,
                "此单元已经停用。" if language == "zh"
                else "This unit is already inactive.",
            )
            return redirect(_staff_structure_edit_url())

        blockers = _structure_unit_disable_blockers(unit)
        if blockers:
            blocker_labels = _structure_unit_disable_blocker_labels(
                blockers,
                language,
            )
            messages.error(
                request,
                (
                    "无法停用此单元；请先处理："
                    + "、".join(blocker_labels)
                )
                if language == "zh"
                else (
                    "This unit was not disabled. Resolve first: "
                    + ", ".join(blocker_labels)
                    + "."
                ),
            )
            return redirect(_staff_structure_edit_url())

        unit.is_active = False
        unit.save(update_fields=["is_active", "updated_at"])
        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=ContentType.objects.get_for_model(
                ChurchStructureUnit
            ).pk,
            object_id=unit.pk,
            object_repr=str(unit),
            action_flag=CHANGE,
            change_message=(
                "Soft-disabled structure unit via staff structure map "
                "(STRUCTURE-SETUP-ACTIONS.1A). No related memberships, "
                "audience rows, role assignments, serving assignments, or "
                "history rows were changed."
            ),
        )

    messages.success(
        request,
        "已停用单元。" if language == "zh"
        else "Unit disabled.",
    )
    return redirect(_staff_structure_edit_url())


@user_passes_test(can_change_church_structure_units)
@require_POST
def staff_structure_unit_enable(request, unit_id):
    language = get_user_language(request)

    with transaction.atomic():
        unit = get_object_or_404(
            ChurchStructureUnit.objects.select_for_update().select_related("parent"),
            id=unit_id,
        )

        if unit.is_active:
            messages.warning(
                request,
                "此单元已经启用。" if language == "zh"
                else "This unit is already active.",
            )
            return redirect(_staff_structure_edit_url())

        blockers = _structure_unit_enable_blockers(unit)
        if blockers:
            blocker_labels = _structure_unit_enable_blocker_labels(
                blockers,
                language,
            )
            messages.error(
                request,
                (
                    "无法恢复启用此单元；请先处理："
                    + "、".join(blocker_labels)
                )
                if language == "zh"
                else (
                    "This unit was not re-enabled. Resolve first: "
                    + ", ".join(blocker_labels)
                    + "."
                ),
            )
            return redirect(_staff_structure_edit_url())

        unit.is_active = True
        try:
            unit.full_clean()
        except ValidationError:
            messages.error(
                request,
                "无法恢复启用此单元；模型验证未通过。"
                if language == "zh"
                else "This unit was not re-enabled. Model validation did not pass.",
            )
            return redirect(_staff_structure_edit_url())

        unit.save(update_fields=["is_active", "updated_at"])
        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=ContentType.objects.get_for_model(
                ChurchStructureUnit
            ).pk,
            object_id=unit.pk,
            object_repr=str(unit),
            action_flag=CHANGE,
            change_message=(
                "Re-enabled structure unit via staff structure map "
                "(STRUCTURE-SETUP-INACTIVE.1B). No child units, memberships, "
                "audience rows, role assignments, serving assignments, or "
                "Bible Study role rows were changed."
            ),
        )

    messages.success(
        request,
        "已恢复启用单元。" if language == "zh"
        else "Unit re-enabled.",
    )
    return redirect(_staff_structure_edit_url())


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


def _structure_unit_descendant_ids(unit):
    descendant_ids = []
    seen_ids = {unit.id}
    parent_ids = [unit.id]

    while parent_ids:
        child_ids = list(
            ChurchStructureUnit.objects.filter(parent_id__in=parent_ids)
            .exclude(id__in=seen_ids)
            .values_list("id", flat=True)
        )
        if not child_ids:
            break
        descendant_ids.extend(child_ids)
        seen_ids.update(child_ids)
        parent_ids = child_ids

    return descendant_ids


def _structure_unit_move_impact_preview(unit, language):
    from comments.models import ReflectionComment
    from events.models import ServiceEvent, ServiceEventAudienceScope
    from prayers.models import PrayerRequest
    from studies.models import (
        BibleStudyMeeting,
        BibleStudyMeetingAudienceScope,
        BibleStudySeriesAudienceScope,
    )

    descendant_ids = _structure_unit_descendant_ids(unit)
    scoped_unit_ids = [unit.id] + descendant_ids
    descendant_units = ChurchStructureUnit.objects.filter(id__in=descendant_ids)
    active_memberships = _active_membership_queryset()

    counts = {
        "active_descendant_units": descendant_units.filter(is_active=True).count(),
        "inactive_descendant_units": descendant_units.filter(is_active=False).count(),
        "active_memberships_direct": active_memberships.filter(unit=unit).count(),
        "active_memberships_descendants": active_memberships.filter(
            unit_id__in=descendant_ids,
        ).count(),
        "active_role_scopes": ChurchRoleAssignment.objects.filter(
            is_active=True,
            structure_unit_id__in=scoped_unit_ids,
        ).count(),
        "service_event_audience_scopes": ServiceEventAudienceScope.objects.filter(
            unit_id__in=scoped_unit_ids,
        ).count(),
        "service_event_host_language_refs": ServiceEvent.objects.filter(
            host_language_unit_id__in=scoped_unit_ids,
        ).count(),
        "bible_study_schedule_audience_scopes": (
            BibleStudySeriesAudienceScope.objects.filter(
                unit_id__in=scoped_unit_ids,
            ).count()
        ),
        "bible_study_meeting_audience_scopes": (
            BibleStudyMeetingAudienceScope.objects.filter(
                unit_id__in=scoped_unit_ids,
            ).count()
        ),
        "bible_study_meeting_anchors": BibleStudyMeeting.objects.filter(
            anchor_unit_id__in=scoped_unit_ids,
        ).count(),
        "prayer_snapshots": PrayerRequest.objects.filter(
            structure_unit_at_post_id__in=scoped_unit_ids,
        ).count(),
        "reflection_snapshots": ReflectionComment.objects.filter(
            structure_unit_at_post_id__in=scoped_unit_ids,
        ).count(),
    }

    labels = {
        "active_descendant_units": {
            "en": "Active descendant units",
            "zh": "启用中的下级后代单元",
        },
        "inactive_descendant_units": {
            "en": "Inactive descendant units",
            "zh": "停用的下级后代单元",
        },
        "active_memberships_direct": {
            "en": "Active memberships directly on this unit",
            "zh": "直接在此单元上的启用归属",
        },
        "active_memberships_descendants": {
            "en": "Active memberships in descendants",
            "zh": "下级后代中的启用归属",
        },
        "active_role_scopes": {
            "en": "Active role scopes on this unit or descendants",
            "zh": "此单元或下级后代上的启用职分范围",
        },
        "service_event_audience_scopes": {
            "en": "ServiceEvent audience scope rows on this unit or descendants",
            "zh": "此单元或下级后代上的教会聚会适用范围行",
        },
        "service_event_host_language_refs": {
            "en": "ServiceEvent host/language references on this unit or descendants",
            "zh": "此单元或下级后代上的教会聚会主办/语言引用",
        },
        "bible_study_schedule_audience_scopes": {
            "en": "Bible Study schedule audience rows on this unit or descendants",
            "zh": "此单元或下级后代上的查经安排适用范围行",
        },
        "bible_study_meeting_audience_scopes": {
            "en": "Bible Study meeting audience rows on this unit or descendants",
            "zh": "此单元或下级后代上的查经聚会适用范围行",
        },
        "bible_study_meeting_anchors": {
            "en": "Bible Study meeting anchors on this unit or descendants",
            "zh": "此单元或下级后代上的查经聚会归属单元",
        },
        "prayer_snapshots": {
            "en": "Prayer snapshots on this unit or descendants",
            "zh": "此单元或下级后代上的代祷快照",
        },
        "reflection_snapshots": {
            "en": "Reflection snapshots on this unit or descendants",
            "zh": "此单元或下级后代上的默想快照",
        },
    }
    label_key = "zh" if language == "zh" else "en"
    rows = [
        {
            "key": key,
            "label": labels[key][label_key],
            "count": counts[key],
        }
        for key in (
            "active_descendant_units",
            "inactive_descendant_units",
            "active_memberships_direct",
            "active_memberships_descendants",
            "active_role_scopes",
            "service_event_audience_scopes",
            "service_event_host_language_refs",
            "bible_study_schedule_audience_scopes",
            "bible_study_meeting_audience_scopes",
            "bible_study_meeting_anchors",
            "prayer_snapshots",
            "reflection_snapshots",
        )
    ]
    return {
        "counts": counts,
        "rows": rows,
    }


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


def _first_form_error(form):
    for errors in form.errors.values():
        if errors:
            return errors[0]
    return ""


@user_passes_test(can_manage_church_memberships)
def church_structure_unit_detail(request, unit_id):
    language = get_user_language(request)
    unit = get_object_or_404(
        ChurchStructureUnit.objects.select_related("parent", "role_profile"),
        id=unit_id,
    )
    add_form = StructureMembershipAddForm(unit=unit)
    can_admin_coworker_roles = request.user.has_perm(
        "accounts.change_churchstructureunit"
    )
    role_profile_form = (
        StructureUnitRoleProfileForm(unit=unit, language=language)
        if can_admin_coworker_roles
        else None
    )
    coworker_user_scope = (
        StructureUnitCoworkerAssignmentForm.USER_SCOPE_ALL
        if request.GET.get("coworker_user_scope")
        == StructureUnitCoworkerAssignmentForm.USER_SCOPE_ALL
        else StructureUnitCoworkerAssignmentForm.USER_SCOPE_LOCAL
    )
    coworker_assignment_local_user_count = (
        coworker_assignment_local_user_queryset(unit).count()
        if can_admin_coworker_roles
        else 0
    )
    coworker_assignment_form_action_url = reverse(
        "add_structure_unit_coworker_assignment",
        args=[unit.id],
    )
    if coworker_user_scope == StructureUnitCoworkerAssignmentForm.USER_SCOPE_ALL:
        coworker_assignment_form_action_url += "?coworker_user_scope=all"
    coworker_assignment_form = (
        StructureUnitCoworkerAssignmentForm(
            unit=unit,
            language=language,
            user_scope=coworker_user_scope,
        )
        if can_admin_coworker_roles
        else None
    )
    active_memberships = order_by_related_user_visible_identity(
        _active_membership_queryset()
        .filter(unit=unit)
        .select_related("user", "unit")
    )
    inactive_memberships = (
        order_by_related_user_visible_identity(
            ChurchStructureMembership.objects.filter(unit=unit)
            .exclude(id__in=active_memberships.values("id"))
            .select_related("user")
        )[:20]
    )
    children = order_units_by_sibling_key(unit.children.all(), language)
    active_coworker_assignments = (
        ChurchStructureUnitRoleAssignment.objects.filter(unit=unit, is_active=True)
        .select_related("role_type", "user")
        .order_by("role_type__sort_order", "role_type__code", "user__username", "id")
    )
    historical_coworker_assignments = (
        ChurchStructureUnitRoleAssignment.objects.filter(unit=unit)
        .exclude(id__in=active_coworker_assignments.values("id"))
        .select_related("role_type", "user")
        .order_by("-updated_at", "role_type__sort_order", "user__username", "id")[:20]
    )
    missing_required_coworker_roles = unit.missing_required_role_types()
    coworker_defaults_missing = (
        not ChurchStructureUnitRoleProfile.objects.exists()
        or not ChurchStructureUnitRoleType.objects.exists()
    )
    can_enable_unit = False
    enable_blocker_labels = []
    if request.user.has_perm("accounts.change_churchstructureunit"):
        enable_blockers = _structure_unit_enable_blockers(unit)
        can_enable_unit = not unit.is_active and not enable_blockers
        enable_blocker_labels = _structure_unit_enable_blocker_labels(
            enable_blockers,
            language,
        )

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
            "role_profile_form": role_profile_form,
            "coworker_assignment_form": coworker_assignment_form,
            "can_admin_coworker_roles": can_admin_coworker_roles,
            "coworker_user_scope": coworker_user_scope,
            "coworker_assignment_form_action_url": (
                coworker_assignment_form_action_url
            ),
            "coworker_assignment_local_user_count": (
                coworker_assignment_local_user_count
            ),
            "active_coworker_assignments": active_coworker_assignments,
            "historical_coworker_assignments": historical_coworker_assignments,
            "missing_required_coworker_roles": missing_required_coworker_roles,
            "coworker_defaults_missing": coworker_defaults_missing,
            "can_enable_unit": can_enable_unit,
            "enable_blocker_labels": enable_blocker_labels,
            "move_impact_preview": _structure_unit_move_impact_preview(
                unit,
                language,
            ),
        },
    )


@user_passes_test(can_change_church_structure_units)
@require_POST
def update_structure_unit_role_profile(request, unit_id):
    language = get_user_language(request)
    unit = get_object_or_404(ChurchStructureUnit, id=unit_id)
    form = StructureUnitRoleProfileForm(
        request.POST,
        unit=unit,
        language=language,
    )

    if form.is_valid():
        form.save()
        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=ContentType.objects.get_for_model(
                ChurchStructureUnit
            ).pk,
            object_id=unit.pk,
            object_repr=str(unit),
            action_flag=CHANGE,
            change_message=(
                "Updated explicit structure unit coworker role profile "
                "(UNIT-COWORKER.1C). No memberships, permissions, serving "
                "assignments, or Bible Study roles were changed."
            ),
        )
        messages.success(
            request,
            "已更新同工角色模板。" if language == "zh"
            else "Coworker role profile updated.",
        )
    else:
        detail = _first_form_error(form)
        messages.error(
            request,
            (
                "同工角色模板未更新。"
                if language == "zh"
                else "Coworker role profile was not updated."
            )
            + (f" {detail}" if detail else ""),
        )

    return redirect("church_structure_unit_detail", unit_id=unit.id)


@user_passes_test(can_change_church_structure_units)
@require_POST
def add_structure_unit_coworker_assignment(request, unit_id):
    language = get_user_language(request)
    unit = get_object_or_404(ChurchStructureUnit, id=unit_id)
    coworker_user_scope = (
        StructureUnitCoworkerAssignmentForm.USER_SCOPE_ALL
        if request.GET.get("coworker_user_scope")
        == StructureUnitCoworkerAssignmentForm.USER_SCOPE_ALL
        else StructureUnitCoworkerAssignmentForm.USER_SCOPE_LOCAL
    )
    form = StructureUnitCoworkerAssignmentForm(
        request.POST,
        unit=unit,
        language=language,
        user_scope=coworker_user_scope,
    )

    if form.is_valid():
        assignment = form.save()
        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=ContentType.objects.get_for_model(
                ChurchStructureUnitRoleAssignment
            ).pk,
            object_id=assignment.pk,
            object_repr=str(assignment),
            action_flag=ADDITION,
            change_message=(
                "Added structure unit coworker role assignment "
                "(UNIT-COWORKER.1C). No memberships, permissions, TeamAssignment "
                "rows, TeamAssignmentMember rows, or BibleStudyMeetingRole rows "
                "were created."
            ),
        )
        messages.success(
            request,
            (
                f"已添加 {assignment.user.username} 的同工角色。"
                if language == "zh"
                else f"Added coworker role for {assignment.user.username}."
            ),
        )
        # SERVING-READINESS.1C: advisory, warning-only readiness reminder for the
        # assigned user. Never blocks the save above.
        add_serving_readiness_warnings(request, assignment.user, language=language)
    else:
        detail = _first_form_error(form)
        messages.error(
            request,
            (
                "同工角色未添加。"
                if language == "zh"
                else "Coworker role was not added."
            )
            + (f" {detail}" if detail else ""),
        )

    return redirect("church_structure_unit_detail", unit_id=unit.id)


@user_passes_test(can_change_church_structure_units)
@require_POST
def end_structure_unit_coworker_assignment(request, assignment_id):
    language = get_user_language(request)
    assignment = get_object_or_404(
        ChurchStructureUnitRoleAssignment.objects.select_related(
            "unit",
            "user",
            "role_type",
        ),
        id=assignment_id,
    )
    today = timezone.localdate()

    assignment.is_active = False
    if not assignment.end_date or assignment.end_date > today:
        assignment.end_date = (
            assignment.start_date
            if assignment.start_date and assignment.start_date > today
            else today
        )
    assignment.save(update_fields=["is_active", "end_date", "updated_at"])
    LogEntry.objects.log_action(
        user_id=request.user.pk,
        content_type_id=ContentType.objects.get_for_model(
            ChurchStructureUnitRoleAssignment
        ).pk,
        object_id=assignment.pk,
        object_repr=str(assignment),
        action_flag=CHANGE,
        change_message=(
            "Ended/deactivated structure unit coworker role assignment "
            "(UNIT-COWORKER.1C). Row was retained; no memberships, permissions, "
            "TeamAssignment rows, TeamAssignmentMember rows, or "
            "BibleStudyMeetingRole rows were changed."
        ),
    )
    messages.success(
        request,
        (
            f"已结束 {assignment.user.username} 的同工角色。"
            if language == "zh"
            else f"Ended coworker role for {assignment.user.username}."
        ),
    )
    return redirect(
        "church_structure_unit_detail",
        unit_id=assignment.unit_id,
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

@login_required
def my_units(request):
    """Read-only "My Units" / 我负责的单位 delegated-management discovery.

    UNIT-LEAD-MANAGE.1B / MYUNITS-UX.1A: lists the structure units the signed-in
    user may manage coworkers for (active lead ancestor-or-self, or staff/superuser
    sees all). MYUNITS-UX.1A reshapes this into a compact, hierarchy-aware overview
    with search/attention filters so that large manage scopes (especially
    staff/superuser, who can manage every active unit) are not a flat wall of full
    roster cards. The full roster and add/end coworker actions live on the detail
    page (``/my-units/<id>/``).

    This is a read-only operational surface, NOT the admin structure tree editor
    (``/staff/structure/``), and it exposes no add/end coworker actions. Management
    is never inferred from membership, audience visibility, serving, or non-lead
    coworker roles. The filters below only narrow the already permission-scoped
    list; they never expand what the user may manage.
    """
    language = get_user_language(request)
    today = timezone.localdate()
    units = get_manageable_structure_units(request.user)

    manageable_ids = {unit.id for unit in units}

    # Active coworker counts for every manageable unit in a single grouped query
    # (read-only; the full per-role roster stays on the detail page).
    coworker_counts = {}
    if manageable_ids:
        for row in (
            ChurchStructureUnitRoleAssignment.objects.filter(
                unit_id__in=manageable_ids,
                is_active=True,
                start_date__lte=today,
            )
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
            .values("unit_id")
            .annotate(active_count=Count("id"))
        ):
            coworker_counts[row["unit_id"]] = row["active_count"]

    all_cards = []
    for unit in units:
        # Indent depth is relative to the user's manageable set (pre-filter), so a
        # delegated lead's subtree reads from depth 0 rather than its absolute tree
        # depth. ``get_manageable_structure_units`` already returns path-ordered
        # units, so each unit renders after its ancestors.
        ancestors = unit.get_ancestors()
        depth = sum(1 for ancestor in ancestors if ancestor.id in manageable_ids)
        path = " > ".join(
            ancestor_or_self.display_name(language)
            for ancestor_or_self in ancestors + [unit]
        )
        has_role_profile = bool(unit.role_profile_id)
        missing_required_count = len(unit.missing_required_role_types(today))
        needs_attention = missing_required_count > 0 or not has_role_profile
        all_cards.append(
            {
                "unit": unit,
                "depth": depth,
                "indent": depth * 18,
                "path": path,
                "name": unit.display_name(language),
                "code": unit.code,
                "name_zh": unit.name,
                "name_en": unit.name_en,
                "unit_type_label": unit.get_unit_type_display(),
                "has_role_profile": has_role_profile,
                "role_profile_label": (
                    unit.role_profile.display_name(language)
                    if unit.role_profile_id
                    else ""
                ),
                "missing_required_count": missing_required_count,
                "active_coworker_count": coworker_counts.get(unit.id, 0),
                "needs_attention": needs_attention,
            }
        )

    # --- Filters / search (read-only; never widen the manageable set) ----------
    query = (request.GET.get("q") or "").strip()
    filter_attention = request.GET.get("attention") == "1"
    filter_missing_required = request.GET.get("missing_required") == "1"
    filter_no_role_profile = request.GET.get("no_role_profile") == "1"
    filters_active = bool(
        query
        or filter_attention
        or filter_missing_required
        or filter_no_role_profile
    )
    query_lower = query.lower()

    def _card_matches(card):
        if query_lower:
            haystack = " ".join(
                part
                for part in (
                    card["code"],
                    card["name_zh"],
                    card["name_en"],
                    card["path"],
                )
                if part
            ).lower()
            if query_lower not in haystack:
                return False
        if filter_attention and not card["needs_attention"]:
            return False
        if filter_missing_required and card["missing_required_count"] <= 0:
            return False
        if filter_no_role_profile and card["has_role_profile"]:
            return False
        return True

    unit_cards = (
        [card for card in all_cards if _card_matches(card)]
        if filters_active
        else all_cards
    )

    return render(
        request,
        "accounts/my_units.html",
        {
            "active_nav": "my_units",
            "unit_cards": unit_cards,
            "has_manageable_units": bool(all_cards),
            "manageable_unit_count": len(all_cards),
            "shown_unit_count": len(unit_cards),
            "filters_active": filters_active,
            "filter_q": query,
            "filter_attention": filter_attention,
            "filter_missing_required": filter_missing_required,
            "filter_no_role_profile": filter_no_role_profile,
        },
    )


def _delegated_coworker_user_scope(request):
    """Resolve the coworker candidate scope for the delegated My Units surface.

    UNIT-LEAD-MANAGE.1C: the "all active users" fallback is reserved for
    staff/superuser. Non-staff delegated leads are always pinned to local
    candidates (active primary membership on the unit or its immediate parent),
    matching the UNIT-COWORKER.1D candidate rule, and cannot widen the picker.
    """
    is_admin = bool(
        getattr(request.user, "is_staff", False)
        or getattr(request.user, "is_superuser", False)
    )
    requested_all = (
        request.GET.get("coworker_user_scope")
        == StructureUnitCoworkerAssignmentForm.USER_SCOPE_ALL
    )
    if is_admin and requested_all:
        return StructureUnitCoworkerAssignmentForm.USER_SCOPE_ALL
    return StructureUnitCoworkerAssignmentForm.USER_SCOPE_LOCAL


def _build_active_coworker_role_groups(unit, today, language):
    """Active coworker assignments for ``unit`` grouped by role type.

    Returns a list of ``{role_type, role_label, assignments}`` dicts ordered by
    role-type sort order. Read-only helper; mutates nothing.
    """
    active_assignments = (
        ChurchStructureUnitRoleAssignment.objects.filter(
            unit=unit,
            is_active=True,
            start_date__lte=today,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        .select_related("role_type", "user")
        .order_by(
            "role_type__sort_order",
            "role_type__code",
            "user__username",
            "id",
        )
    )

    role_groups = []
    current_role_type_id = None
    current_group = None
    for assignment in active_assignments:
        if assignment.role_type_id != current_role_type_id:
            current_role_type_id = assignment.role_type_id
            current_group = {
                "role_type": assignment.role_type,
                "role_label": assignment.role_type.display_name(language),
                "assignments": [],
            }
            role_groups.append(current_group)
        current_group["assignments"].append(assignment)
    return role_groups


@login_required
def my_unit_detail(request, unit_id):
    """Delegated coworker-management page for one manageable structure unit.

    UNIT-LEAD-MANAGE.1C: authorized leads (active ``lead`` ancestor-or-self) and
    staff/superuser may add and end long-term coworker role assignments for the
    active units they manage, gated by ``can_manage_unit_coworkers``. This is the
    operational My Units surface, separate from the admin structure tree at
    ``/staff/structure/``. It changes only ``ChurchStructureUnitRoleAssignment``
    rows; it never touches membership, permissions, serving, or meeting roles.
    """
    language = get_user_language(request)
    today = timezone.localdate()
    unit = get_object_or_404(
        ChurchStructureUnit.objects.select_related("parent", "role_profile"),
        id=unit_id,
    )
    if not can_manage_unit_coworkers(request.user, unit):
        raise Http404("Unit is not manageable by this user.")

    is_coworker_admin = bool(
        getattr(request.user, "is_staff", False)
        or getattr(request.user, "is_superuser", False)
    )
    coworker_user_scope = _delegated_coworker_user_scope(request)

    role_groups = _build_active_coworker_role_groups(unit, today, language)
    missing_required_roles = unit.missing_required_role_types(today)
    coworker_defaults_missing = (
        not ChurchStructureUnitRoleProfile.objects.exists()
        or not ChurchStructureUnitRoleType.objects.exists()
    )

    add_form = StructureUnitCoworkerAssignmentForm(
        unit=unit,
        language=language,
        user_scope=coworker_user_scope,
    )
    add_form_action_url = reverse(
        "add_my_unit_coworker_assignment",
        args=[unit.id],
    )
    if coworker_user_scope == StructureUnitCoworkerAssignmentForm.USER_SCOPE_ALL:
        add_form_action_url += "?coworker_user_scope=all"

    return render(
        request,
        "accounts/my_unit_detail.html",
        {
            "active_nav": "my_units",
            "unit": unit,
            "unit_path": unit.path_label(language),
            "unit_name": unit.display_name(language),
            "has_role_profile": bool(unit.role_profile_id),
            "role_profile_label": (
                unit.role_profile.display_name(language)
                if unit.role_profile_id
                else ""
            ),
            "missing_required_roles": [
                role_type.display_name(language)
                for role_type in missing_required_roles
            ],
            "role_groups": role_groups,
            "coworker_defaults_missing": coworker_defaults_missing,
            "add_form": add_form,
            "add_form_action_url": add_form_action_url,
            "coworker_user_scope": coworker_user_scope,
            "is_coworker_admin": is_coworker_admin,
            "coworker_local_user_count": (
                coworker_assignment_local_user_queryset(unit).count()
            ),
        },
    )


@login_required
@require_POST
def add_my_unit_coworker_assignment(request, unit_id):
    """Create a coworker role assignment from the delegated My Units surface.

    UNIT-LEAD-MANAGE.1C: gated by ``can_manage_unit_coworkers``. Reuses the
    UNIT-COWORKER.1C/1D ``StructureUnitCoworkerAssignmentForm`` (local candidate
    scope for non-staff leads). Creates only a ``ChurchStructureUnitRoleAssignment``
    row; no membership, capability, serving, or meeting-role rows.
    """
    language = get_user_language(request)
    unit = get_object_or_404(ChurchStructureUnit, id=unit_id)
    if not can_manage_unit_coworkers(request.user, unit):
        raise Http404("Unit is not manageable by this user.")

    coworker_user_scope = _delegated_coworker_user_scope(request)
    form = StructureUnitCoworkerAssignmentForm(
        request.POST,
        unit=unit,
        language=language,
        user_scope=coworker_user_scope,
    )

    if form.is_valid():
        assignment = form.save()
        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=ContentType.objects.get_for_model(
                ChurchStructureUnitRoleAssignment
            ).pk,
            object_id=assignment.pk,
            object_repr=str(assignment),
            action_flag=ADDITION,
            change_message=(
                "Added structure unit coworker role assignment via delegated My "
                "Units surface (UNIT-LEAD-MANAGE.1C). No memberships, permissions, "
                "TeamAssignment rows, TeamAssignmentMember rows, or "
                "BibleStudyMeetingRole rows were created."
            ),
        )
        messages.success(
            request,
            (
                f"已添加 {assignment.user.username} 的同工角色。"
                if language == "zh"
                else f"Added coworker role for {assignment.user.username}."
            ),
        )
        # SERVING-READINESS.1C: advisory, warning-only readiness reminder shown only
        # to the assigning lead/staff user. Never blocks the save above and never
        # appears on ordinary My Serving / Today.
        add_serving_readiness_warnings(request, assignment.user, language=language)
    else:
        detail = _first_form_error(form)
        messages.error(
            request,
            (
                "同工角色未添加。"
                if language == "zh"
                else "Coworker role was not added."
            )
            + (f" {detail}" if detail else ""),
        )

    redirect_url = reverse("my_unit_detail", args=[unit.id])
    if coworker_user_scope == StructureUnitCoworkerAssignmentForm.USER_SCOPE_ALL:
        redirect_url += "?coworker_user_scope=all"
    return redirect(redirect_url)


@login_required
@require_POST
def end_my_unit_coworker_assignment(request, assignment_id):
    """End/deactivate a coworker assignment from the delegated My Units surface.

    UNIT-LEAD-MANAGE.1C: gated by ``can_manage_unit_coworkers`` on the
    assignment's unit. Sets ``is_active=False`` and an ``end_date`` (mirroring the
    staff end behavior); the row is retained, never deleted, and no unrelated
    assignment, membership, serving, or meeting-role rows are touched.
    """
    language = get_user_language(request)
    assignment = get_object_or_404(
        ChurchStructureUnitRoleAssignment.objects.select_related(
            "unit",
            "user",
            "role_type",
        ),
        id=assignment_id,
    )
    if not can_manage_unit_coworkers(request.user, assignment.unit):
        raise Http404("Assignment is not manageable by this user.")

    if not assignment.is_active:
        messages.info(
            request,
            (
                "该同工角色已经结束。"
                if language == "zh"
                else "That coworker role is already ended."
            ),
        )
        return redirect("my_unit_detail", unit_id=assignment.unit_id)

    today = timezone.localdate()
    assignment.is_active = False
    if not assignment.end_date or assignment.end_date > today:
        assignment.end_date = (
            assignment.start_date
            if assignment.start_date and assignment.start_date > today
            else today
        )
    assignment.save(update_fields=["is_active", "end_date", "updated_at"])
    LogEntry.objects.log_action(
        user_id=request.user.pk,
        content_type_id=ContentType.objects.get_for_model(
            ChurchStructureUnitRoleAssignment
        ).pk,
        object_id=assignment.pk,
        object_repr=str(assignment),
        action_flag=CHANGE,
        change_message=(
            "Ended/deactivated structure unit coworker role assignment via "
            "delegated My Units surface (UNIT-LEAD-MANAGE.1C). Row was retained; "
            "no memberships, permissions, TeamAssignment rows, "
            "TeamAssignmentMember rows, or BibleStudyMeetingRole rows were changed."
        ),
    )
    messages.success(
        request,
        (
            f"已结束 {assignment.user.username} 的同工角色。"
            if language == "zh"
            else f"Ended coworker role for {assignment.user.username}."
        ),
    )
    return redirect("my_unit_detail", unit_id=assignment.unit_id)


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

    users = order_users_by_visible_identity(
        User.objects.select_related("profile")
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
    memberships = order_by_related_user_visible_identity(
        ChurchStructureMembership.objects
        .filter(status=ChurchStructureMembership.STATUS_REQUESTED)
        .select_related(
            "user",
            "user__profile",
            "unit",
            "unit__parent",
            "requested_by",
        )
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
