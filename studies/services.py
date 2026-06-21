from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from accounts.models import ChurchStructureUnit

from .models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
)


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


def sync_normal_meeting_audience_scope_for_unit(meeting, unit):
    """BS-STRUCT.1O manual-form writer keyed on a structure unit, not a group.

    The manual normal small-group meeting form chooses a ``UNIT_SMALL_GROUP``
    ``ChurchStructureUnit`` as the source of truth. This helper aligns the
    meeting to that unit. The caller (the form's ``clean()``) must have already
    validated that the meeting is a normal single-unit small-group meeting —
    never a higher-level / joint / multi-unit meeting — so the stale-row
    deletion below can never clobber a district / joint audience.

    Behavior:

    * create/get the single audience row for ``unit``;
    * delete any other (stale) audience rows so the runtime row matches the
      selected unit after a unit change;
    * set ``anchor_unit`` to ``unit``;
    * set ``meeting_kind`` to ``normal``;
    * set the structure-native ``generation_key`` (``normal-unit:{unit_id}``) so
      a manual normal meeting shares the per-unit idempotency key with
      generation, giving one normal meeting per (lesson, unit).

    BS-MEETING-MIRROR.1A removed the legacy ``small_group`` mirror, so this
    helper is fully structure-native.
    """
    BibleStudyMeetingAudienceScope.objects.get_or_create(meeting=meeting, unit=unit)
    meeting.audience_scope_links.exclude(unit=unit).delete()

    meeting.anchor_unit = unit
    meeting.meeting_kind = BibleStudyMeeting.KIND_NORMAL
    meeting.generation_key = normal_generation_key_for_unit(unit)
    meeting.save(
        update_fields=[
            "anchor_unit",
            "meeting_kind",
            "generation_key",
            "updated_at",
        ]
    )


# ---------------------------------------------------------------------------
# BS-STRUCT.1L: structure-unit-native normal meeting generation.
#
# Normal Bible Study generation targets ``ChurchStructureUnit`` leaf
# small-group units. BS-MEETING-MIRROR.1A removed the legacy
# ``BibleStudyMeeting.small_group`` mirror, so generation and idempotency are
# fully structure-native (``generation_key`` + audience rows).
# ---------------------------------------------------------------------------

# Stable per-unit idempotency key prefix for a normal group-level meeting.
NORMAL_GENERATION_KEY_PREFIX = "normal-unit:"

# Warning kinds surfaced by ``resolve_normal_generation_targets`` so the view
# layer can format manager-visible, language-specific messages without the
# service layer knowing about request language. BS-STRUCT.1L/1M made generation
# structure-unit-native (it no longer resolves legacy ``SmallGroup`` rows), and
# BS-MEETING-MIRROR.1A removed the legacy ``small_group`` mirror, so the old
# ambiguous-mirror warning is gone.
# BS-STRUCT.1M: a series with zero BibleStudySeriesAudienceScope rows no longer
# falls back to legacy scope; generation fails closed and surfaces this warning.
GENERATION_WARNING_MISSING_SERIES_AUDIENCE = "missing_series_audience"


def normal_generation_key_for_unit(unit):
    """Return the stable generation key for a normal meeting on ``unit``.

    Format: ``normal-unit:{unit_id}``. Keyed on the ``ChurchStructureUnit``
    leaf id because the generation target is a structure unit. Combined with the
    ``(lesson, generation_key)`` conditional unique constraint this gives one
    normal meeting per (lesson, unit) and makes generation idempotent.
    """
    return f"{NORMAL_GENERATION_KEY_PREFIX}{unit.id}"


@dataclass(frozen=True)
class GenerationTarget:
    """One normal group-level generation target.

    ``unit`` is an active ``UNIT_SMALL_GROUP`` ``ChurchStructureUnit`` that
    should receive exactly one normal ``BibleStudyMeeting`` per lesson.
    """

    unit: ChurchStructureUnit


@dataclass(frozen=True)
class GenerationWarning:
    """A manager-visible reason a unit did not yield a clean target."""

    kind: str
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
    * ``warnings`` — a list of :class:`GenerationWarning`; currently only a
      single ``GENERATION_WARNING_MISSING_SERIES_AUDIENCE`` warning when the
      series has no structure audience rows.

    Resolution (BS-STRUCT.1M — structure-audience-required):

    * **Structure audience rows present** — each selected
      ``BibleStudySeriesAudienceScope`` unit expands to its active
      descendant-or-self ``UNIT_SMALL_GROUP`` units; each such unit becomes one
      structure-native target. BS-MEETING-MIRROR.1A removed the legacy
      ``small_group`` mirror, so targets carry only their structure unit.
    * **Zero audience rows** — generation **fails closed**. The legacy
      ``BibleStudySeries.scope_type`` / ``ministry_context`` / ``district`` /
      ``small_group`` fields were removed in BS-SERIES-FIELD-RETIRE.1A and are
      not a generation source. No targets are produced; instead a single
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
        targets.append(GenerationTarget(unit=unit))

    return _ordered_targets(targets), warnings


def build_existing_normal_meeting_index(lesson):
    """Index a lesson's existing meetings for generation-target matching.

    Existing meetings are matched against a target by either of two
    structure-native keys so that both newly generated meetings and pre-key
    meetings are recognized and never duplicated:

    * ``by_generation_key`` — the ``normal-unit:{unit_id}`` key written by
      generation;
    * ``by_single_audience_unit_id`` — a meeting whose audience rows are exactly
      one unit, recognizing a meeting that has a single small-group audience row
      but no generation key. A multi-unit (joint / higher-level) meeting is
      intentionally not indexed here so it never absorbs a normal target.

    BS-MEETING-MIRROR.1A removed the legacy ``small_group`` idempotency key.

    All non-cancelled and cancelled meetings are indexed; cancelled meetings
    still count as existing so generation never regenerates over them.
    """
    by_generation_key = {}
    by_single_audience_unit_id = {}

    meetings = lesson.meetings.all().prefetch_related("audience_scope_links")
    for meeting in meetings:
        if meeting.generation_key:
            by_generation_key.setdefault(meeting.generation_key, meeting)
        audience_unit_ids = [link.unit_id for link in meeting.audience_scope_links.all()]
        if len(audience_unit_ids) == 1:
            by_single_audience_unit_id.setdefault(audience_unit_ids[0], meeting)

    return {
        "by_generation_key": by_generation_key,
        "by_single_audience_unit_id": by_single_audience_unit_id,
    }


def find_existing_meeting_for_target(index, target):
    """Return an existing meeting matching ``target``, or ``None``.

    Checks, in order: generation key, then a single-unit audience row matching
    the target unit. BS-MEETING-MIRROR.1A removed the legacy ``small_group``
    fallback match.
    """
    meeting = index["by_generation_key"].get(normal_generation_key_for_unit(target.unit))
    if meeting is not None:
        return meeting
    return index["by_single_audience_unit_id"].get(target.unit.id)


def create_normal_meeting_for_target(lesson, target, *, meeting_datetime, created_by):
    """Create one structure-native normal meeting for ``target``.

    Writes a meeting with ``anchor_unit`` and one audience row set to the target
    unit, ``meeting_kind`` normal, and the stable per-unit ``generation_key``.
    Returns the created meeting. Assumes the caller has confirmed no existing
    meeting matches the target (idempotency is enforced by the caller via
    :func:`find_existing_meeting_for_target` plus the database unique
    constraints).
    """
    meeting = BibleStudyMeeting.objects.create(
        lesson=lesson,
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
