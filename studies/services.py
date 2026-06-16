from django.db import transaction
from django.utils import timezone

from accounts.models import ChurchStructureUnit

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
