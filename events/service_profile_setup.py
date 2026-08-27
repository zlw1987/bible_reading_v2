"""Bounded Bethany 09:30 ServiceEvent test-data reset support.

MO-S.6D-PROFILE-SETUP.1A is deliberately operator-driven.  Preview is
read-only; apply deletes only ServiceEvent-owned scheduling rows (plus the
documented nullable Bible Study link update) and creates the approved 2026
foundation inside one transaction.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, time

from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from ministry.models import TeamAssignment, TeamAssignmentMember
from notifications.models import Notification
from studies.models import BibleStudyMeeting

from .models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventPlannerAssignment,
    ServiceEventRequiredTeam,
)
from .service_profile_readiness import (
    build_audit,
    build_expected_sundays,
    get_schema_readiness,
)


PROFILE_KEY = "bethany_0930_cm"
PROFILE_YEAR = 2026
PROFILE_LOCAL_TIME = time(9, 30)
PROFILE_EVENT_TYPE = ServiceEvent.EVENT_SUNDAY_SERVICE
PROFILE_TITLE = "主日崇拜"
PROFILE_TITLE_EN = "Sunday Service"

DELETE_COUNT_MODEL_LABELS = {
    "service_events_deleted": "events.ServiceEvent",
    "audience_rows_deleted": "events.ServiceEventAudienceScope",
    "required_team_rows_deleted": "events.ServiceEventRequiredTeam",
    "planner_rows_deleted": "events.ServiceEventPlannerAssignment",
    "team_assignments_deleted": "ministry.TeamAssignment",
    "team_assignment_members_deleted": "ministry.TeamAssignmentMember",
}

ROOT_CODE = "CHURCH"
AUDIENCE_CODE = "CM"
RESET_APPROVAL_CONTRACT_VERSION = "MO-S.6D-PROFILE-SETUP.1A-FU1-v1"
RESET_APPROVAL_TOKEN_LENGTH = 16


class ProfileSetupError(RuntimeError):
    """Base class for safe operator-facing setup failures."""


class ProfileSetupPrerequisiteError(ProfileSetupError):
    """The exact persisted setup identity cannot be resolved safely."""


class ProfileSetupPostconditionError(ProfileSetupError):
    """The rebuilt dataset failed its in-transaction acceptance checks."""


def _stable_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _stable_rows(queryset, *fields):
    return [
        [_stable_value(value) for value in row]
        for row in queryset.order_by("pk").values_list(*fields)
    ]


def _existing_content_type(app_label, model):
    return ContentType.objects.filter(app_label=app_label, model=model).first()


def resolve_bethany_cm_audience():
    """Resolve the exact active CHURCH -> campus -> CM persisted path.

    ``ChurchStructureUnit.code`` is unique only within a parent.  Consequently
    this resolver never selects the first ``CM`` row.  It requires one active
    parentless CHURCH root and exactly one active ministry-context CM below one
    active Campus/Site on that root.  Names and database primary keys are not
    identity inputs; multiple matching campus branches fail closed.
    """

    roots = list(
        ChurchStructureUnit.objects.filter(
            parent__isnull=True,
            code=ROOT_CODE,
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            is_active=True,
        ).order_by("pk")
    )
    if len(roots) != 1:
        raise ProfileSetupPrerequisiteError(
            "Expected exactly one active parentless root with code CHURCH; "
            f"found {len(roots)}. No ServiceEvent was deleted."
        )
    root = roots[0]

    candidates = []
    for unit in ChurchStructureUnit.objects.filter(code=AUDIENCE_CODE).order_by("pk"):
        ancestors = unit.get_ancestors()
        if (
            unit.is_active
            and unit.unit_type == ChurchStructureUnit.UNIT_MINISTRY_CONTEXT
            and len(ancestors) == 2
            and ancestors[0].pk == root.pk
            and ancestors[0].is_active
            and ancestors[1].is_active
            and ancestors[1].unit_type == ChurchStructureUnit.UNIT_CAMPUS
            and unit.parent_id == ancestors[1].pk
        ):
            candidates.append(unit)

    if len(candidates) != 1:
        raise ProfileSetupPrerequisiteError(
            "Expected exactly one active CHURCH -> campus -> CM "
            "ministry-context path; "
            f"found {len(candidates)}. Codes are parent-scoped, so no first-row "
            "or name-based fallback is allowed. No ServiceEvent was deleted."
        )
    return candidates[0]


def _related_history_counts(*, event_ids, assignment_ids, member_ids):
    event_ids_as_text = [str(value) for value in event_ids]
    assignment_ids_as_text = [str(value) for value in assignment_ids]
    member_ids_as_text = [str(value) for value in member_ids]

    event_content_type = _existing_content_type("events", "serviceevent")
    assignment_content_type = _existing_content_type("ministry", "teamassignment")
    return {
        "service_event_log_entries_retained": (
            LogEntry.objects.filter(
                content_type=event_content_type,
                object_id__in=event_ids_as_text,
            ).count()
            if event_content_type
            else 0
        ),
        "team_assignment_log_entries_retained": (
            LogEntry.objects.filter(
                content_type=assignment_content_type,
                object_id__in=assignment_ids_as_text,
            ).count()
            if assignment_content_type
            else 0
        ),
        "service_event_notifications_retained": Notification.objects.filter(
            source_model_label__iexact="events.ServiceEvent",
            source_object_id__in=event_ids_as_text,
        ).count(),
        "team_assignment_notifications_retained": Notification.objects.filter(
            source_model_label__iexact="ministry.TeamAssignment",
            source_object_id__in=assignment_ids_as_text,
        ).count(),
        "assignment_member_notifications_retained": Notification.objects.filter(
            source_model_label__iexact="ministry.TeamAssignmentMember",
            source_object_id__in=member_ids_as_text,
        ).count(),
        "worship_batch_notifications_retained": Notification.objects.filter(
            notification_type="worship_rotation.changed",
        ).count(),
    }


def build_existing_dataset_snapshot():
    """Return counts plus a stable fingerprint of the exact reset surface."""

    event_rows = list(
        ServiceEvent.objects.order_by("pk").values(
            "pk",
            "start_datetime",
            "status",
            "service_profile_key",
            "title",
        )
    )
    event_ids = [row["pk"] for row in event_rows]
    assignments = TeamAssignment.objects.filter(service_event_id__in=event_ids)
    assignment_ids = list(assignments.order_by("pk").values_list("pk", flat=True))
    members = TeamAssignmentMember.objects.filter(assignment_id__in=assignment_ids)
    member_ids = list(members.order_by("pk").values_list("pk", flat=True))

    fingerprint_payload = {
        "events": _stable_rows(
            ServiceEvent.objects.all(),
            "pk",
            "event_type",
            "service_profile_key",
            "start_datetime",
            "end_datetime",
            "status",
            "scheduling_revision",
            "updated_at",
            "host_language_unit_id",
            "rotation_anchor_team_id",
        ),
        "audience": _stable_rows(
            ServiceEventAudienceScope.objects.filter(service_event_id__in=event_ids),
            "pk",
            "service_event_id",
            "unit_id",
        ),
        "required_teams": _stable_rows(
            ServiceEventRequiredTeam.objects.filter(service_event_id__in=event_ids),
            "pk",
            "service_event_id",
            "ministry_team_id",
        ),
        "planners": _stable_rows(
            ServiceEventPlannerAssignment.objects.filter(service_event_id__in=event_ids),
            "pk",
            "service_event_id",
            "user_id",
            "is_active",
            "updated_at",
        ),
        "assignments": _stable_rows(
            assignments,
            "pk",
            "service_event_id",
            "ministry_team_id",
            "status",
            "updated_at",
        ),
        "assignment_members": _stable_rows(
            members,
            "pk",
            "assignment_id",
            "membership_id",
            "confirmed_at",
        ),
        "bible_study_links": _stable_rows(
            BibleStudyMeeting.objects.filter(service_event_id__in=event_ids),
            "pk",
            "service_event_id",
        ),
    }
    encoded = json.dumps(
        fingerprint_payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    counts = {
        "service_events_deleted": len(event_ids),
        "audience_rows_deleted": len(fingerprint_payload["audience"]),
        "required_team_rows_deleted": len(fingerprint_payload["required_teams"]),
        "planner_rows_deleted": len(fingerprint_payload["planners"]),
        "team_assignments_deleted": len(assignment_ids),
        "team_assignment_members_deleted": len(member_ids),
        "bible_study_links_cleared": len(fingerprint_payload["bible_study_links"]),
    }
    counts.update(
        _related_history_counts(
            event_ids=event_ids,
            assignment_ids=assignment_ids,
            member_ids=member_ids,
        )
    )
    return {
        "event_ids": tuple(event_ids),
        "event_rows": tuple(event_rows),
        "fingerprint": hashlib.sha256(encoded).hexdigest(),
        "counts": counts,
    }


def _canonical_start(sunday):
    return timezone.make_aware(
        datetime.combine(sunday, PROFILE_LOCAL_TIME),
        timezone.get_current_timezone(),
    )


def _expected_status(sunday, *, today):
    if sunday < today:
        return ServiceEvent.STATUS_COMPLETED
    return ServiceEvent.STATUS_PUBLISHED


def build_replacement_preview(*, today=None):
    today = today or timezone.localdate()
    rows = [
        {
            "date": sunday,
            "start_datetime": _canonical_start(sunday),
            "status": _expected_status(sunday, today=today),
        }
        for sunday in build_expected_sundays(PROFILE_YEAR)
    ]
    return {
        "rows": rows,
        "count": len(rows),
        "completed": sum(row["status"] == ServiceEvent.STATUS_COMPLETED for row in rows),
        "published": sum(row["status"] == ServiceEvent.STATUS_PUBLISHED for row in rows),
        "today": today,
    }


def build_reset_approval(preview):
    """Bind APPLY to the exact reset surface and reviewed setup contract."""

    audience = preview["audience"]
    audience_path = audience.get_ancestors() + [audience]
    payload = {
        "contract_version": RESET_APPROVAL_CONTRACT_VERSION,
        "reset_surface_sha256": preview["before"]["fingerprint"],
        "audience_path": [
            {
                "pk": unit.pk,
                "parent_pk": unit.parent_id,
                "code": unit.code,
                "unit_type": unit.unit_type,
            }
            for unit in audience_path
        ],
        "replacement_today": preview["replacement"]["today"].isoformat(),
        "setup_contract": {
            "profile_key": PROFILE_KEY,
            "year": PROFILE_YEAR,
            "local_time": PROFILE_LOCAL_TIME.isoformat(timespec="minutes"),
            "timezone": str(timezone.get_current_timezone()),
            "event_type": PROFILE_EVENT_TYPE,
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return {
        "payload_sha256": digest,
        "token": digest[:RESET_APPROVAL_TOKEN_LENGTH],
    }


def build_reset_preview(*, today=None):
    schema = get_schema_readiness()
    if not schema["ready"]:
        raise ProfileSetupPrerequisiteError(
            "Required events migrations/schema through events/0011 are not ready. "
            "No ServiceEvent ORM reset query was attempted."
        )
    audience = resolve_bethany_cm_audience()
    preview = {
        "schema": schema,
        "audience": audience,
        "before": build_existing_dataset_snapshot(),
        "replacement": build_replacement_preview(today=today),
    }
    preview["approval"] = build_reset_approval(preview)
    return preview


def _dataset_is_canonical(*, audience, today):
    expected_sundays = build_expected_sundays(PROFILE_YEAR)
    events = list(
        ServiceEvent.objects.select_related("host_language_unit")
        .prefetch_related("audience_scope_links")
        .order_by("start_datetime", "pk")
    )
    if len(events) != len(expected_sundays):
        return False
    if ServiceEventRequiredTeam.objects.exists():
        return False
    if ServiceEventPlannerAssignment.objects.exists():
        return False
    if TeamAssignment.objects.exists() or TeamAssignmentMember.objects.exists():
        return False

    for event, sunday in zip(events, expected_sundays):
        local_start = timezone.localtime(
            event.start_datetime,
            timezone.get_current_timezone(),
        )
        if (
            local_start.date() != sunday
            or local_start.time().replace(tzinfo=None) != PROFILE_LOCAL_TIME
            or event.title != PROFILE_TITLE
            or event.title_en != PROFILE_TITLE_EN
            or event.description
            or event.description_en
            or event.event_type != PROFILE_EVENT_TYPE
            or event.service_profile_key != PROFILE_KEY
            or event.end_datetime is not None
            or event.location
            or event.meeting_link
            or event.host_language_unit_id != audience.pk
            or event.rotation_anchor_team_id is not None
            or event.status != _expected_status(sunday, today=today)
            or event.scheduling_revision != 0
            or event.created_by_id is not None
            or list(event.audience_scope_links.values_list("unit_id", flat=True))
            != [audience.pk]
        ):
            return False
        if event.status == ServiceEvent.STATUS_PUBLISHED and event.published_at is None:
            return False
        if event.status == ServiceEvent.STATUS_COMPLETED and event.published_at is not None:
            return False
    return True


def _create_canonical_event(*, sunday, audience, today):
    event = ServiceEvent.objects.create(
        title=PROFILE_TITLE,
        title_en=PROFILE_TITLE_EN,
        event_type=PROFILE_EVENT_TYPE,
        service_profile_key=PROFILE_KEY,
        start_datetime=_canonical_start(sunday),
        host_language_unit=audience,
        status=_expected_status(sunday, today=today),
    )
    ServiceEventAudienceScope.objects.create(service_event=event, unit=audience)
    return event


def verify_postconditions(*, audience, today):
    if not _dataset_is_canonical(audience=audience, today=today):
        raise ProfileSetupPostconditionError(
            "Canonical ServiceEvent postconditions failed; the reset transaction "
            "will be rolled back."
        )
    audit = build_audit(
        profile_key=PROFILE_KEY,
        year=PROFILE_YEAR,
        target_time=PROFILE_LOCAL_TIME,
        event_type=PROFILE_EVENT_TYPE,
    )
    if audit["recommendation"] != "PROFILE SETUP READY":
        raise ProfileSetupPostconditionError(
            "The canonical readiness audit did not return PROFILE SETUP READY; "
            "the reset transaction will be rolled back."
        )
    return audit


def apply_reset(*, expected_reset_token, today=None):
    """Atomically delete the approved test dataset and rebuild canonical rows."""

    today = today or timezone.localdate()
    with transaction.atomic():
        # Re-read every prerequisite and the complete reset surface inside the
        # write transaction.  Operators must still use a maintenance window;
        # SQLite supplies single-writer serialization, not row locks.
        preview = build_reset_preview(today=today)
        if not hmac.compare_digest(
            expected_reset_token,
            preview["approval"]["token"],
        ):
            raise ProfileSetupPrerequisiteError(
                "Reset preview changed since product-owner review. Run the "
                "dry-run again and review the new reset approval token. No data "
                "was changed."
            )
        audience = preview["audience"]
        if _dataset_is_canonical(audience=audience, today=today):
            audit = verify_postconditions(audience=audience, today=today)
            zero_deleted = {
                key: 0 for key in preview["before"]["counts"]
            }
            return {
                "no_op": True,
                "data_mutated": False,
                "before": preview["before"],
                "deleted": zero_deleted,
                "created_events": 0,
                "created_audience_rows": 0,
                "audit": audit,
            }

        _total_deleted, deleted_by_model = ServiceEvent.objects.all().delete()
        actual_deleted = dict(preview["before"]["counts"])
        for count_key, model_label in DELETE_COUNT_MODEL_LABELS.items():
            actual_deleted[count_key] = deleted_by_model.get(model_label, 0)
            if actual_deleted[count_key] != preview["before"]["counts"][count_key]:
                raise ProfileSetupPostconditionError(
                    "ServiceEvent cascade counts changed during APPLY; the reset "
                    "transaction will be rolled back."
                )
        created = 0
        for sunday in build_expected_sundays(PROFILE_YEAR):
            _create_canonical_event(sunday=sunday, audience=audience, today=today)
            created += 1

        audit = verify_postconditions(audience=audience, today=today)
        return {
            "no_op": False,
            "data_mutated": True,
            "before": preview["before"],
            "deleted": actual_deleted,
            "created_events": created,
            "created_audience_rows": created,
            "audit": audit,
        }
