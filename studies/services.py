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
    mapping is drift for a normal small-group meeting). Since BS-STRUCT.1P the
    only caller is the manual ``BibleStudyMeetingForm`` edit path, which uses it
    to pre-fill the ``audience_unit`` from an existing legacy ``small_group`` when
    a meeting has no audience row / anchor yet (priority 3 of the edit initial
    resolution). It is never a write path; ``small_group`` remains only a
    compatibility mirror and zero-row runtime fallback source.
    """
    unit = get_small_group_structure_unit(small_group)
    if (
        unit is None
        or not unit.is_active
        or unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP
    ):
        return None
    return unit


def sync_normal_meeting_audience_scope_for_unit(meeting, unit):
    """BS-STRUCT.1O manual-form writer keyed on a structure unit, not a group.

    The manual normal small-group meeting form now chooses a
    ``UNIT_SMALL_GROUP`` ``ChurchStructureUnit`` as the source of truth. This
    helper aligns the meeting to that unit. The caller (the form's ``clean()``)
    must have already validated that the meeting is a normal single-unit
    small-group meeting — never a higher-level / joint / multi-unit meeting — so
    the stale-row deletion below can never clobber a district / joint audience.

    Behavior:

    * create/get the single audience row for ``unit``;
    * delete any other (stale) audience rows so the runtime row matches the
      selected unit after a unit change;
    * set ``anchor_unit`` to ``unit``;
    * set ``meeting_kind`` to ``normal``;
    * set the structure-native ``generation_key`` (``normal-unit:{unit_id}``) so
      a manual normal meeting shares the per-unit idempotency key with
      generation, giving one normal meeting per (lesson, unit);
    * set the legacy ``small_group`` mirror from ``unit`` using the exact-one-
      active-legacy-group rule — ``None`` when no active legacy group maps to the
      unit or the mapping is ambiguous (two or more active groups).

    The legacy ``small_group`` is only ever written here as a mirror; it is never
    consulted as a source of truth. Returns the mirror ``SmallGroup`` (or
    ``None``) so callers/tests can assert the mirror result.
    """
    mirror, _ambiguous = resolve_unit_small_group_mirror(unit)

    BibleStudyMeetingAudienceScope.objects.get_or_create(meeting=meeting, unit=unit)
    meeting.audience_scope_links.exclude(unit=unit).delete()

    meeting.anchor_unit = unit
    meeting.meeting_kind = BibleStudyMeeting.KIND_NORMAL
    meeting.generation_key = normal_generation_key_for_unit(unit)
    meeting.small_group = mirror
    meeting.save(
        update_fields=[
            "anchor_unit",
            "meeting_kind",
            "generation_key",
            "small_group",
            "updated_at",
        ]
    )
    return mirror


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
# service layer knowing about request language. (BS-STRUCT.1P removed the
# obsolete ``unmapped_group`` warning: since BS-STRUCT.1L/1M generation no longer
# resolves legacy ``SmallGroup`` rows, so an unmapped-legacy-group warning can no
# longer be produced.)
GENERATION_WARNING_AMBIGUOUS_MIRROR = "ambiguous_mirror"
# BS-STRUCT.1M: a series with zero BibleStudySeriesAudienceScope rows no longer
# falls back to legacy scope; generation fails closed and surfaces this warning.
GENERATION_WARNING_MISSING_SERIES_AUDIENCE = "missing_series_audience"


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


def resolve_unit_small_group_mirror(unit):
    """Public ``(mirror, ambiguous)`` for a unit's exact-one legacy ``SmallGroup``.

    Thin public wrapper over :func:`_resolve_unit_small_group_mirror` so callers
    outside generation (e.g. the manual ``BibleStudyMeetingForm`` duplicate
    check) share the exact-one-active-legacy-group semantics rather than
    re-deriving them. Returns ``(group, False)`` only when exactly one active
    legacy group maps to ``unit``; ``(None, True)`` when ambiguous (two or more);
    ``(None, False)`` when none.
    """
    return _resolve_unit_small_group_mirror(unit)


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
    * ``warnings`` — a list of :class:`GenerationWarning` describing units whose
      legacy mirror was dropped as ambiguous, or (when the series has no
      structure audience rows) a single
      ``GENERATION_WARNING_MISSING_SERIES_AUDIENCE`` warning.

    Resolution (BS-STRUCT.1M — structure-audience-required):

    * **Structure audience rows present** — each selected
      ``BibleStudySeriesAudienceScope`` unit expands to its active
      descendant-or-self ``UNIT_SMALL_GROUP`` units; each such unit becomes one
      target. This is the structure-native path and can produce targets for
      units that have no legacy ``SmallGroup`` mirror. The legacy ``small_group``
      mirror is attached only when exactly one active legacy group maps to the
      target unit.
    * **Zero audience rows** — generation **fails closed**. The legacy
      ``series.get_eligible_small_groups()`` / ``scope_type`` / ``district`` /
      ``small_group`` fields are **no longer** consulted as a generation source.
      No targets are produced; instead a single
      ``GENERATION_WARNING_MISSING_SERIES_AUDIENCE`` warning is returned so the
      view can tell the manager to configure the schedule audience scope first.
    """
    warnings = []
    seen_unit_ids = set()
    targets = []

    audience_units = list(series.get_audience_scope_units())

    if not audience_units:
        # BS-STRUCT.1M fail-closed: no structure audience rows => no generation.
        # No legacy-only meeting, no zero-row meeting, no hidden fallback.
        return [], [
            GenerationWarning(kind=GENERATION_WARNING_MISSING_SERIES_AUDIENCE)
        ]

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
