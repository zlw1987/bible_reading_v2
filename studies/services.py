from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from accounts.models import ChurchStructureUnit, SmallGroup

from .models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
)
from .visibility import get_small_group_structure_unit


def cancel_non_final_meetings_for_lesson(lesson):
    return lesson.meetings.filter(
        status__in=[
            BibleStudyMeeting.STATUS_DRAFT,
            BibleStudyMeeting.STATUS_PUBLISHED,
        ],
    ).update(
        status=BibleStudyMeeting.STATUS_CANCELLED,
        updated_at=timezone.now(),
    )


def cancel_bible_study_lesson_with_meetings(lesson):
    with transaction.atomic():
        lesson.status = BibleStudyLesson.STATUS_CANCELLED
        lesson.save()
        return cancel_non_final_meetings_for_lesson(lesson)


def resolve_normal_small_group_unit(small_group):
    """Return the active ``UNIT_SMALL_GROUP`` unit a legacy small group maps to.

    Returns ``None`` when the mapping is missing, the mapped unit is inactive, or
    the mapped unit is not a ``UNIT_SMALL_GROUP`` (e.g. a district / CM / EM
    mapping is drift for a normal small-group meeting). This is the single shared
    validation used by both the generation-side writer and the manual-form sync
    so they agree on what counts as a valid normal small-group mapping.
    """
    unit = get_small_group_structure_unit(small_group)
    if (
        unit is None
        or not unit.is_active
        or unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP
    ):
        return None
    return unit


def write_normal_meeting_audience_scope(meeting):
    """BS-STRUCT.1D generation-side writer (moved here in BS-STRUCT.1H).

    Attaches a structure-native audience row to a freshly generated normal
    group-level meeting. Resolves the meeting's legacy ``small_group`` mapped
    ``ChurchStructureUnit`` and, only when that unit exists, is active, and is
    ``UNIT_SMALL_GROUP``, creates one ``BibleStudyMeetingAudienceScope`` row and
    sets ``anchor_unit`` to that unit when it is currently null. Returns ``True``
    when a row was written, ``False`` when the group has no valid active
    small-group unit mapping (the meeting is then left exactly as the pre-1D
    legacy-only zero-row meeting and the caller surfaces a warning).

    Create-only: it assumes a freshly generated meeting with zero existing
    audience rows, so it never deletes or replaces rows. Fail-closed by design:
    an invalid mapping never produces an audience row, so a meeting is never
    falsely presented as structure-native. Never mutates ``small_group``; never
    overwrites an existing ``anchor_unit``; never changes ``meeting_kind`` (stays
    ``normal``). The manual-form path uses
    :func:`sync_normal_meeting_audience_scope` instead, which additionally
    repairs/replaces a stale row after a group change.
    """
    unit = resolve_normal_small_group_unit(meeting.small_group)
    if unit is None:
        return False

    BibleStudyMeetingAudienceScope.objects.get_or_create(
        meeting=meeting,
        unit=unit,
    )
    if meeting.anchor_unit_id is None:
        meeting.anchor_unit = unit
        meeting.save(update_fields=["anchor_unit", "updated_at"])
    return True


def sync_normal_meeting_audience_scope(meeting):
    """BS-STRUCT.1H manual-form writer: create or repair the normal audience row.

    Used by ``BibleStudyMeetingForm`` create/edit (not generation) to keep the
    structure-native audience row and the legacy ``small_group`` mirror aligned
    for a normal small-group meeting. The caller (the form's ``clean()``) must
    have already validated that:

    * ``meeting.small_group`` resolves to a valid active ``UNIT_SMALL_GROUP``
      unit (so this returns ``True`` in practice); and
    * any existing audience rows are a single normal small-group row, never a
      higher-level / multi-unit set — so the stale-row deletion below can never
      clobber a district / joint meeting's audience.

    Behavior:

    * create the row when missing (zero-row meeting repair);
    * after a group change, drop the stale prior small-group row so no stale row
      survives and the runtime row matches the selected group;
    * set ``anchor_unit`` when it is null **or** when it still mirrors the old
      selected group's small-group unit; never overwrite an unrelated anchor;
    * never mutate ``small_group``; never change ``meeting_kind``.

    Returns ``True`` when the row was written, ``False`` when the mapping is
    invalid (defensive — the form rejects that case before save).
    """
    unit = resolve_normal_small_group_unit(meeting.small_group)
    if unit is None:
        return False

    existing_unit_ids = set(
        meeting.audience_scope_links.values_list("unit_id", flat=True)
    )

    BibleStudyMeetingAudienceScope.objects.get_or_create(
        meeting=meeting,
        unit=unit,
    )
    # Drop a stale prior small-group row left by a group change. Safe only
    # because the form validated existing rows are a single normal small-group
    # row, never a higher-level / multi-unit set.
    meeting.audience_scope_links.exclude(unit=unit).delete()

    # Only move the anchor when it is unset or clearly a mirror of the old
    # selected group's unit; an unrelated (e.g. manually set higher-level)
    # anchor is preserved.
    anchor_id = meeting.anchor_unit_id
    anchor_mirrors_old_group = anchor_id is not None and anchor_id in existing_unit_ids
    if (anchor_id is None or anchor_mirrors_old_group) and anchor_id != unit.id:
        meeting.anchor_unit = unit
        meeting.save(update_fields=["anchor_unit", "updated_at"])
    return True


# ---------------------------------------------------------------------------
# BS-STRUCT.1L: structure-unit-native normal meeting generation.
#
# Normal Bible Study generation now targets ``ChurchStructureUnit`` leaf
# small-group units instead of fundamentally targeting legacy ``SmallGroup``
# rows. The legacy ``small_group`` FK is kept only as a compatibility mirror
# attached when exactly one active legacy group maps to the target unit.
# ---------------------------------------------------------------------------

# Stable per-unit idempotency key prefix for a normal group-level meeting.
NORMAL_GENERATION_KEY_PREFIX = "normal-unit:"

# Warning kinds surfaced by ``resolve_normal_generation_targets`` so the view
# layer can format manager-visible, language-specific messages without the
# service layer knowing about request language.
GENERATION_WARNING_UNMAPPED_GROUP = "unmapped_group"
GENERATION_WARNING_AMBIGUOUS_MIRROR = "ambiguous_mirror"


def normal_generation_key_for_unit(unit):
    """Return the stable generation key for a normal meeting on ``unit``.

    Format: ``normal-unit:{unit_id}``. Keyed on the ``ChurchStructureUnit``
    leaf id (not the legacy ``small_group``) because the generation target is
    now a structure unit; the legacy group is only a mirror. Combined with the
    ``(lesson, generation_key)`` conditional unique constraint this gives one
    normal meeting per (lesson, unit) and makes generation idempotent even for
    a structure-native unit that has no legacy ``SmallGroup`` mirror.
    """
    return f"{NORMAL_GENERATION_KEY_PREFIX}{unit.id}"


@dataclass(frozen=True)
class GenerationTarget:
    """One normal group-level generation target.

    ``unit`` is an active ``UNIT_SMALL_GROUP`` ``ChurchStructureUnit`` that
    should receive exactly one normal ``BibleStudyMeeting`` per lesson.
    ``small_group`` is the optional legacy compatibility mirror, set only when
    exactly one active legacy ``SmallGroup`` maps to ``unit`` (``None`` for a
    structure-native unit with no legacy group, or an ambiguous many-to-one
    mapping).
    """

    unit: ChurchStructureUnit
    small_group: Optional[SmallGroup]


@dataclass(frozen=True)
class GenerationWarning:
    """A manager-visible reason a legacy group / unit did not yield a clean target."""

    kind: str
    small_group: Optional[SmallGroup] = None
    unit: Optional[ChurchStructureUnit] = None


def _collect_descendant_or_self_unit_ids(units):
    """Return ids of the given units plus all their descendants."""
    collected = set()
    frontier = [unit.id for unit in units if getattr(unit, "id", None) is not None]
    while frontier:
        collected.update(frontier)
        frontier = list(
            ChurchStructureUnit.objects.filter(parent_id__in=frontier)
            .exclude(id__in=collected)
            .values_list("id", flat=True)
        )
    return collected


def _resolve_unit_small_group_mirror(unit):
    """Return (mirror, ambiguous) for a target unit's legacy ``SmallGroup``.

    The legacy ``small_group`` mirror is attached only when exactly one active
    legacy ``SmallGroup`` maps to the unit. Zero mappings yield ``(None,
    False)`` (a structure-native unit with no legacy group). Two or more active
    mappings are ambiguous and yield ``(None, True)`` so generation never
    silently mirrors a meeting to an arbitrary one of several groups; the unit
    still becomes a single structure-native target and the caller surfaces a
    warning.
    """
    active_groups = list(unit.legacy_small_groups.filter(is_active=True)[:2])
    if len(active_groups) == 1:
        return active_groups[0], False
    if len(active_groups) > 1:
        return None, True
    return None, False


def _ordered_targets(targets):
    """Deterministically order targets by unit path / order / name / id."""
    return sorted(
        targets,
        key=lambda target: (
            target.unit.sort_order,
            target.unit.code or "",
            target.unit.name or "",
            target.unit.id,
        ),
    )


def resolve_normal_generation_targets(series):
    """Resolve a series to normal group-level generation targets.

    Returns ``(targets, warnings)``:

    * ``targets`` — a deduplicated (by unit id), deterministically ordered list
      of :class:`GenerationTarget`.
    * ``warnings`` — a list of :class:`GenerationWarning` describing legacy
      groups skipped because their structure mapping is missing / inactive /
      wrong type, and units whose legacy mirror was dropped as ambiguous.

    Two resolution paths:

    * **Structure audience rows present** — each selected
      ``BibleStudySeriesAudienceScope`` unit expands to its active
      descendant-or-self ``UNIT_SMALL_GROUP`` units; each such unit becomes one
      target. This is the structure-native path and can produce targets for
      units that have no legacy ``SmallGroup`` mirror.
    * **Legacy fallback (zero audience rows)** — start from the legacy
      ``series.get_eligible_small_groups()`` and convert each eligible group to
      its mapped active ``UNIT_SMALL_GROUP`` unit via
      :func:`resolve_normal_small_group_unit`. An invalid (unmapped / inactive /
      wrong-type) mapping is skipped with a warning rather than creating a
      legacy-only zero-row meeting, preserving the fail-closed invariant that a
      generated meeting is never falsely presented as structure-native.

    In both paths the legacy ``small_group`` mirror is attached only when
    exactly one active legacy group maps to the target unit.
    """
    warnings = []
    seen_unit_ids = set()
    targets = []

    audience_units = list(series.get_audience_scope_units())

    if audience_units:
        unit_ids = _collect_descendant_or_self_unit_ids(audience_units)
        leaf_units = ChurchStructureUnit.objects.filter(
            id__in=unit_ids,
            is_active=True,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
        )
        for unit in leaf_units:
            if unit.id in seen_unit_ids:
                continue
            seen_unit_ids.add(unit.id)
            mirror, ambiguous = _resolve_unit_small_group_mirror(unit)
            if ambiguous:
                warnings.append(
                    GenerationWarning(
                        kind=GENERATION_WARNING_AMBIGUOUS_MIRROR,
                        unit=unit,
                    )
                )
            targets.append(GenerationTarget(unit=unit, small_group=mirror))
        return _ordered_targets(targets), warnings

    # Legacy fallback: zero structure audience rows.
    for group in series.get_eligible_small_groups():
        unit = resolve_normal_small_group_unit(group)
        if unit is None:
            warnings.append(
                GenerationWarning(
                    kind=GENERATION_WARNING_UNMAPPED_GROUP,
                    small_group=group,
                )
            )
            continue
        if unit.id in seen_unit_ids:
            # Two eligible groups map to the same unit: one structure-native
            # target, no duplicate meeting. The mirror was already resolved by
            # the single-active-group rule below (so duplicates drop the mirror).
            continue
        seen_unit_ids.add(unit.id)
        mirror, ambiguous = _resolve_unit_small_group_mirror(unit)
        if ambiguous:
            warnings.append(
                GenerationWarning(
                    kind=GENERATION_WARNING_AMBIGUOUS_MIRROR,
                    unit=unit,
                )
            )
        targets.append(GenerationTarget(unit=unit, small_group=mirror))

    return _ordered_targets(targets), warnings


def build_existing_normal_meeting_index(lesson):
    """Index a lesson's existing meetings for generation-target matching.

    Existing meetings are matched against a target by any of three keys so that
    both newly generated meetings and pre-BS-STRUCT.1L meetings are recognized
    and never duplicated:

    * ``by_generation_key`` — the ``normal-unit:{unit_id}`` key written by this
      slice's generation;
    * ``by_small_group_id`` — the legacy ``small_group`` mirror, recognizing
      meetings generated before generation keys existed;
    * ``by_single_audience_unit_id`` — a meeting whose audience rows are exactly
      one unit, recognizing a pre-1L meeting that has a single small-group
      audience row but no generation key. A multi-unit (joint / higher-level)
      meeting is intentionally not indexed here so it never absorbs a normal
      target.

    All non-cancelled and cancelled meetings are indexed; cancelled meetings
    still count as existing so generation never regenerates over them.
    """
    by_generation_key = {}
    by_small_group_id = {}
    by_single_audience_unit_id = {}

    meetings = lesson.meetings.all().prefetch_related("audience_scope_links")
    for meeting in meetings:
        if meeting.generation_key:
            by_generation_key.setdefault(meeting.generation_key, meeting)
        if meeting.small_group_id:
            by_small_group_id.setdefault(meeting.small_group_id, meeting)
        audience_unit_ids = [link.unit_id for link in meeting.audience_scope_links.all()]
        if len(audience_unit_ids) == 1:
            by_single_audience_unit_id.setdefault(audience_unit_ids[0], meeting)

    return {
        "by_generation_key": by_generation_key,
        "by_small_group_id": by_small_group_id,
        "by_single_audience_unit_id": by_single_audience_unit_id,
    }


def find_existing_meeting_for_target(index, target):
    """Return an existing meeting matching ``target``, or ``None``.

    Checks, in order: generation key, legacy ``small_group`` mirror (when the
    target has one), and a single-unit audience row matching the target unit.
    """
    meeting = index["by_generation_key"].get(normal_generation_key_for_unit(target.unit))
    if meeting is not None:
        return meeting
    if target.small_group is not None:
        meeting = index["by_small_group_id"].get(target.small_group.id)
        if meeting is not None:
            return meeting
    return index["by_single_audience_unit_id"].get(target.unit.id)


def create_normal_meeting_for_target(lesson, target, *, meeting_datetime, created_by):
    """Create one structure-native normal meeting for ``target``.

    Writes a meeting with the legacy ``small_group`` mirror (when present),
    ``anchor_unit`` and one audience row set to the target unit, ``meeting_kind``
    normal, and the stable per-unit ``generation_key``. Returns the created
    meeting. Assumes the caller has confirmed no existing meeting matches the
    target (idempotency is enforced by the caller via
    :func:`find_existing_meeting_for_target` plus the database unique
    constraints).
    """
    meeting = BibleStudyMeeting.objects.create(
        lesson=lesson,
        small_group=target.small_group,
        anchor_unit=target.unit,
        meeting_kind=BibleStudyMeeting.KIND_NORMAL,
        generation_key=normal_generation_key_for_unit(target.unit),
        meeting_datetime=meeting_datetime,
        status=BibleStudyMeeting.STATUS_DRAFT,
        created_by=created_by,
    )
    BibleStudyMeetingAudienceScope.objects.get_or_create(
        meeting=meeting,
        unit=target.unit,
    )
    return meeting
