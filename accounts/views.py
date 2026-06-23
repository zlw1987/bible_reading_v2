from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import PasswordChangeView
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.http import Http404, HttpResponseForbidden
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
    """Church Structure Map with setup-readiness indicators (CS-MAP.2).

    The default map view is review-first: counts only, no member rosters. On
    top of that, CS-SETUP.1B adds an opt-in display-name-only edit mode for
    admin-capable staff (per-row rename + Details link); no other structure
    edits happen here. Ordinary-user matching remains consumer-specific during
    the transition: ServiceEvent audience rows now match through active primary
    ChurchStructureMembership, and zero-row ServiceEvents fail closed for
    ordinary users (the zero-row legacy fallback was retired in SE-RETIRE.1B),
    while Bible Study member visibility/generation, reading/privacy/progress,
    permissions, and My Serving remain legacy/consumer-specific as documented.
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
        active_memberships.filter(is_primary=True)
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
            "is_root": unit.unit_type == ChurchStructureUnit.UNIT_ROOT,
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


# CS-SETUP.1D.1: supported legacy -> structure mapping types. Each legacy model
# maps to exactly one ChurchStructureUnit type and is gated by the matching
# Django Admin change permission. The edit dropdown is filtered to active units
# of the matching type for convenience, but the POST handler re-validates
# required / exists / active / type-match / duplicate-active authoritatively.
LEGACY_MAPPING_TYPES = {
    "ministry-context": {
        "model": MinistryContext,
        "unit_type": ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
        "perm": "accounts.change_ministrycontext",
    },
    "district": {
        "model": District,
        "unit_type": ChurchStructureUnit.UNIT_DISTRICT,
        "perm": "accounts.change_district",
    },
    "small-group": {
        "model": SmallGroup,
        "unit_type": ChurchStructureUnit.UNIT_SMALL_GROUP,
        "perm": "accounts.change_smallgroup",
    },
}

# Status filter keys accepted by the mapping review page; reused when an edit
# action round-trips the prior filter back to the review list.
MAPPING_REVIEW_STATUSES = {
    "all",
    "needs_review",
    "mapped_active",
    "unmapped",
    "mapped_inactive",
    "mapped_holding",
    # Display-only conflict/warning overlay filters (CS-SETUP.1D.3). They narrow
    # the list by overlay flag rather than primary status_key and write nothing.
    "conflicts",
    "type_mismatch",
    "duplicate_active",
}


@staff_member_required
@require_GET
def staff_structure_mapping_review(request):
    """Legacy -> structure mapping review (CS-SETUP.1C.1 / .1C.2 / .1D.1 /
    .1D.2 / .1D.3).

    Staff-only final-retirement/setup diagnostic page that lists every legacy
    MinistryContext / District / SmallGroup row beside the ChurchStructureUnit it is mapped to, with a
    mapping-status label and (CS-SETUP.1D.2) display-only type-mismatch /
    duplicate-active conflict badges. CS-SETUP.1C.2 adds summary counts and
    primary ``?status=`` filter links so a long mapping list can be narrowed to
    the rows that need review. CS-SETUP.1D.3 adds three more display-only
    overlay filters (``?status=conflicts`` / ``type_mismatch`` /
    ``duplicate_active``) that narrow the same list by conflict-badge flag
    instead of primary status; like the primary filters they are GET-only
    navigation, leave the badges and all counts as true totals, and write
    nothing. This view itself is GET-only and writes nothing: the
    ``status`` filter only hides/shows already-loaded rows. When the viewer
    holds the matching Django Admin change permission, each permitted row offers
    a one-row mapping edit link (CS-SETUP.1D.1) to the separate
    ``staff_structure_mapping_edit`` view; Django Admin edit links appear under
    the same permission. Those edits change the legacy -> structure mapping
    only: they do not directly edit members, audience rows, serving schedules,
    permissions, ordinary visibility, or normal Bible Study V2 generation. Like
    /staff/structure/, this page never uses ChurchStructureMembership as a
    runtime visibility source. Since CS-CORE.2B-A, ServiceEvent audience rows
    match by active primary membership instead of these mapping fields; normal
    Bible Study V2 generation is now structure-native, while final-retirement
    setup/admin/diagnostic resolution can still read this mapping.
    """
    language = get_user_language(request)
    holding_codes = {"UNASSIGNED-DISTRICTS", "UNASSIGNED-GROUPS"}

    # Read-only status filter. "needs_review" is the union of the three
    # attention statuses; an unknown value falls back to showing all rows.
    # The overlay filters (CS-SETUP.1D.3) narrow by display-only conflict flag
    # instead of the primary status_key, so they sit alongside the primary
    # status filters without changing what status_key a row carries.
    needs_review_keys = ("unmapped", "mapped_inactive", "mapped_holding")
    overlay_statuses = ("conflicts", "type_mismatch", "duplicate_active")
    valid_statuses = (
        ("all", "needs_review", "mapped_active")
        + needs_review_keys
        + overlay_statuses
    )
    status = request.GET.get("status", "all")
    if status not in valid_statuses:
        status = "all"

    def row_matches(row):
        if status == "all":
            return True
        if status == "needs_review":
            return row["status_key"] in needs_review_keys
        # Overlay filters inspect the display-only conflict flags on the full
        # row rather than the primary status_key, so a mapped_active row can
        # still surface under a conflict filter.
        if status == "conflicts":
            return row["is_type_mismatch"] or row["is_duplicate_active"]
        if status == "type_mismatch":
            return row["is_type_mismatch"]
        if status == "duplicate_active":
            return row["is_duplicate_active"]
        return row["status_key"] == status

    # Counts are tallied across every loaded row, independent of the active
    # filter, so the summary always shows true totals for the filter links.
    # ``type_mismatch`` / ``duplicate_active`` are display-only conflict
    # overlays (CS-SETUP.1D.2): they sit on top of the primary status_key
    # rather than replacing it, so a row can be both ``mapped_active`` and a
    # duplicate-conflict at once. ``conflicts`` counts rows carrying either
    # overlay (a row with both is counted once).
    counts = {
        "all": 0,
        "mapped_active": 0,
        "unmapped": 0,
        "mapped_inactive": 0,
        "mapped_holding": 0,
        "type_mismatch": 0,
        "duplicate_active": 0,
        "conflicts": 0,
    }

    can_change_unit = request.user.has_perm(
        "accounts.change_churchstructureunit"
    )

    def build_rows(
        queryset, legacy_admin_viewname, can_change_legacy, legacy_type_slug
    ):
        # The mapping config drives the two conflict overlays: ``unit_type``
        # is the type a row of this legacy kind is expected to map to, and the
        # duplicate set lists units that more than one *active* row of this
        # same kind point at (the exact condition the edit POST handler
        # blocks). Both are display-only here; nothing is written.
        config = LEGACY_MAPPING_TYPES[legacy_type_slug]
        expected_unit_type = config["unit_type"]
        legacy_model = config["model"]
        duplicate_unit_ids = set(
            legacy_model.objects.filter(
                is_active=True, church_structure_unit__isnull=False
            )
            .values("church_structure_unit")
            .annotate(n=Count("church_structure_unit"))
            .filter(n__gt=1)
            .values_list("church_structure_unit", flat=True)
        )

        all_rows = []
        for obj in queryset:
            unit = obj.church_structure_unit
            if unit is None:
                status_key = "unmapped"
                unit_path = ""
                unit_is_active = None
                is_type_mismatch = False
                is_duplicate_active = False
            else:
                # Reuse a single ancestor walk for both the path label and the
                # cheap holding-node check, rather than calling path_label()
                # and re-walking parents separately.
                chain = unit.get_ancestors() + [unit]
                unit_path = " > ".join(
                    node.display_name(language) for node in chain
                )
                unit_is_active = unit.is_active
                if not unit.is_active:
                    status_key = "mapped_inactive"
                elif any(node.code in holding_codes for node in chain):
                    status_key = "mapped_holding"
                else:
                    status_key = "mapped_active"
                # Conflict overlays. Wrong-type mappings cannot be produced by
                # the in-app edit (it re-validates type), but legacy data or a
                # direct Admin edit can leave one, so it is surfaced. Duplicate
                # only flags active rows, matching the active-only edit guard.
                is_type_mismatch = unit.unit_type != expected_unit_type
                is_duplicate_active = (
                    obj.is_active and unit.pk in duplicate_unit_ids
                )
            counts["all"] += 1
            counts[status_key] += 1
            if is_type_mismatch:
                counts["type_mismatch"] += 1
            if is_duplicate_active:
                counts["duplicate_active"] += 1
            if is_type_mismatch or is_duplicate_active:
                counts["conflicts"] += 1
            all_rows.append(
                {
                    "label": str(obj),
                    "is_active": obj.is_active,
                    "unit": unit,
                    "unit_path": unit_path,
                    "unit_is_active": unit_is_active,
                    "status_key": status_key,
                    "is_type_mismatch": is_type_mismatch,
                    "is_duplicate_active": is_duplicate_active,
                    "legacy_admin_url": (
                        reverse(legacy_admin_viewname, args=[obj.pk])
                        if can_change_legacy
                        else None
                    ),
                    "unit_admin_url": (
                        reverse(
                            "admin:accounts_churchstructureunit_change",
                            args=[unit.pk],
                        )
                        if unit is not None and can_change_unit
                        else None
                    ),
                    # In-app mapping edit (CS-SETUP.1D.1). Offered only to staff
                    # holding the matching legacy change permission; read-only
                    # staff see no edit action.
                    "mapping_edit_url": (
                        reverse(
                            "staff_structure_mapping_edit",
                            args=[legacy_type_slug, obj.pk],
                        )
                        if can_change_legacy
                        else None
                    ),
                }
            )
        # Tally happens on every row above; only matching rows are rendered.
        return [row for row in all_rows if row_matches(row)]

    sections = [
        {
            "key": "ministry_contexts",
            "rows": build_rows(
                MinistryContext.objects.select_related(
                    "church_structure_unit"
                ).order_by("sort_order", "code", "name"),
                "admin:accounts_ministrycontext_change",
                request.user.has_perm("accounts.change_ministrycontext"),
                "ministry-context",
            ),
        },
        {
            "key": "districts",
            "rows": build_rows(
                District.objects.select_related(
                    "church_structure_unit"
                ).order_by("name"),
                "admin:accounts_district_change",
                request.user.has_perm("accounts.change_district"),
                "district",
            ),
        },
        {
            "key": "small_groups",
            "rows": build_rows(
                SmallGroup.objects.select_related(
                    "church_structure_unit"
                ).order_by("name"),
                "admin:accounts_smallgroup_change",
                request.user.has_perm("accounts.change_smallgroup"),
                "small-group",
            ),
        },
    ]

    counts["needs_review"] = (
        counts["unmapped"] + counts["mapped_inactive"] + counts["mapped_holding"]
    )

    return render(
        request,
        "accounts/staff/structure_mapping_review.html",
        {
            "active_nav": "staff",
            "sections": sections,
            "counts": counts,
            "status": status,
        },
    )


@staff_member_required
def staff_structure_mapping_edit(request, legacy_type, legacy_id):
    """Edit one legacy row's church_structure_unit mapping (CS-SETUP.1D.1).

    Narrow staff workflow that sets or changes a single MinistryContext /
    District / SmallGroup row's ``church_structure_unit`` to one existing
    *active* ChurchStructureUnit of the matching unit type. GET renders a
    review/edit form; the save is an explicit POST only (no inline autosave).
    Backend validation is authoritative (required / exists / active /
    type-match / duplicate-active); the filtered dropdown is convenience only.

    It writes nothing else directly: no unit lifecycle, no membership, no
    audience-scope rows (ServiceEventAudienceScope / BibleStudySeriesAudienceScope),
    and no TeamAssignment. It does not edit members,
    audience rows, serving schedules, or permissions. Since CS-CORE.2B-A,
    ServiceEvent audience rows match by active primary ChurchStructureMembership
    instead of this mapping bridge. Normal Bible Study V2 generation is now
    structure-native, while final-retirement setup/admin/diagnostic resolution
    can still read this mapping. To keep that effect explicit, the POST requires a
    staff acknowledgement checkbox before it will save; without it the mapping
    is left unchanged. Each successful update
    is audited via a Django admin
    ``LogEntry`` CHANGE record carrying the before/after mapped-unit context.
    """
    language = get_user_language(request)

    config = LEGACY_MAPPING_TYPES.get(legacy_type)
    if config is None:
        raise Http404("Unknown legacy mapping type.")

    # Write access is strictly the matching Django Admin change permission for
    # the legacy model; read-only staff structure access is not write access.
    if not request.user.has_perm(config["perm"]):
        return HttpResponseForbidden("Not allowed to edit this mapping.")

    model = config["model"]
    unit_type = config["unit_type"]
    obj = get_object_or_404(model, pk=legacy_id)

    review_url = reverse("staff_structure_mapping_review")
    # Preserve the prior status filter only when the review page accepts it.
    status = request.POST.get("status") or request.GET.get("status") or ""
    if status not in MAPPING_REVIEW_STATUSES:
        status = ""
    redirect_url = f"{review_url}?status={status}" if status else review_url

    target_units = list(
        ChurchStructureUnit.objects.filter(
            is_active=True, unit_type=unit_type
        ).order_by("sort_order", "code", "name")
    )

    current_unit = obj.church_structure_unit
    # Default selection echoes the current mapping. If the current unit is
    # inactive or the wrong type it is not among target_units, so the dropdown
    # falls back to the placeholder until staff pick an active matching unit.
    selected_unit_id = current_unit.pk if current_unit else None
    error = None
    acknowledged = False

    if request.method == "POST":
        # Required impact acknowledgement (CS-SETUP.1D.4). A mapping edit does
        # not directly touch members/audience/schedule/permission rows, but it
        # can still affect remaining Bible Study bridge/admin/diagnostic
        # resolution, so staff must confirm they understand that before any save.
        acknowledged = bool(request.POST.get("acknowledge_impact"))
        raw = (request.POST.get("church_structure_unit") or "").strip()
        selected_unit_id = None
        if raw:
            try:
                selected_unit_id = int(raw)
            except (TypeError, ValueError):
                selected_unit_id = None

        target = None
        if not raw:
            error = (
                "请选择一个结构单元。" if language == "zh"
                else "Please choose a structure unit."
            )
        else:
            target = (
                ChurchStructureUnit.objects.filter(pk=selected_unit_id).first()
                if selected_unit_id is not None
                else None
            )
            if target is None:
                error = (
                    "所选结构单元不存在。" if language == "zh"
                    else "The selected structure unit does not exist."
                )
            elif not target.is_active:
                error = (
                    "所选结构单元已停用，无法对应。" if language == "zh"
                    else "The selected structure unit is inactive."
                )
            elif target.unit_type != unit_type:
                error = (
                    "所选结构单元类型不匹配。" if language == "zh"
                    else "The selected structure unit type does not match "
                    "this record."
                )
            else:
                # Duplicate guard: do not let two active legacy rows of the
                # same type map to the same unit. Keeping the current row's
                # existing mapping is always allowed (no change to enforce).
                is_change = (
                    current_unit is None or current_unit.pk != target.pk
                )
                if is_change and obj.is_active:
                    conflict = (
                        model.objects.filter(
                            is_active=True, church_structure_unit=target
                        )
                        .exclude(pk=obj.pk)
                        .exists()
                    )
                    if conflict:
                        error = (
                            "已有另一条启用记录对应到该结构单元。"
                            if language == "zh"
                            else "Another active record is already mapped to "
                            "this structure unit."
                        )

        # Acknowledgement is enforced only once the target itself is valid, so
        # existing target validation messages (required / exists / active /
        # type / duplicate) keep surfacing unchanged for an invalid target.
        if error is None and not acknowledged:
            error = (
                "保存前请确认你了解此对应关系更改仅用于最终退役准备、设置检查、管理或诊断解析。"
                if language == "zh"
                else "Please confirm that you understand this mapping change "
                "is for final-retirement preparation, setup checks, admin, or "
                "diagnostic resolution before saving."
            )

        if error is None:
            old_unit = current_unit
            obj.church_structure_unit = target
            obj.save(update_fields=["church_structure_unit"])

            old_repr = (
                f"{old_unit} (id={old_unit.pk})" if old_unit else "None"
            )
            new_repr = f"{target} (id={target.pk})"
            LogEntry.objects.log_action(
                user_id=request.user.pk,
                content_type_id=ContentType.objects.get_for_model(model).pk,
                object_id=obj.pk,
                object_repr=str(obj),
                action_flag=CHANGE,
                change_message=(
                    "Updated legacy structure mapping via staff mapping "
                    "maintenance (CS-SETUP.1D.1). "
                    f"church_structure_unit: {old_repr} -> {new_repr}."
                ),
            )
            messages.success(
                request,
                "已更新对应关系。" if language == "zh"
                else "Mapping updated.",
            )
            return redirect(redirect_url)

        messages.error(request, error)

    type_labels = {
        ChurchStructureUnit.UNIT_MINISTRY_CONTEXT: (
            "事工范围" if language == "zh" else "Ministry Context"
        ),
        ChurchStructureUnit.UNIT_DISTRICT: (
            "区" if language == "zh" else "District"
        ),
        ChurchStructureUnit.UNIT_SMALL_GROUP: (
            "小组" if language == "zh" else "Small Group"
        ),
    }
    unit_options = [
        {"id": unit.pk, "label": unit.path_label(language)}
        for unit in target_units
    ]

    return render(
        request,
        "accounts/staff/structure_mapping_edit.html",
        {
            "active_nav": "staff",
            "legacy_label": str(obj),
            "legacy_type_label": type_labels.get(unit_type, ""),
            "legacy_is_active": obj.is_active,
            "current_unit": current_unit,
            "current_unit_path": (
                current_unit.path_label(language) if current_unit else ""
            ),
            "current_unit_is_active": (
                current_unit.is_active if current_unit else None
            ),
            "unit_options": unit_options,
            "selected_unit_id": selected_unit_id,
            "status": status,
            "redirect_url": redirect_url,
            "error": error,
            "acknowledged": acknowledged,
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
