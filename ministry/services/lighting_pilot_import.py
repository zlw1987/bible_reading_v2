import csv
from dataclasses import dataclass, field
from datetime import datetime, time

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.db import transaction
from django.utils import timezone

from events.models import ServiceEvent
from ministry.models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)


REQUIRED_COLUMNS = {
    "event_date",
    "event_type",
    "event_title",
    "assigned_member",
}
OPTIONAL_COLUMNS = {
    "event_title_en",
    "start_time",
    "end_time",
    "service_detail",
    "special_event_note",
    "worship_team",
    "member_email",
    "playbook_link",
}
FORBIDDEN_COLUMNS = {
    "phone_number",
    "private_notes",
    "prayer_notes",
    "zoom_password",
}
EVENT_TYPES = {
    ServiceEvent.EVENT_SUNDAY_SERVICE,
    ServiceEvent.EVENT_BIBLE_STUDY,
    ServiceEvent.EVENT_SPECIAL_MEETING,
    ServiceEvent.EVENT_CONFERENCE,
    ServiceEvent.EVENT_GOSPEL_MUSIC,
    ServiceEvent.EVENT_BAPTISM,
    ServiceEvent.EVENT_OTHER,
}
LIGHTING_TEAM_NAME = "灯光组"
LIGHTING_TEAM_NAME_EN = "Lighting Team"
LEGACY_LIGHTING_TEAM_NAME = "Lighting Team"


class ImportStructureError(ValueError):
    pass


@dataclass
class ImportStats:
    teams_created: int = 0
    memberships_created: int = 0
    service_events_created: int = 0
    assignments_created: int = 0
    assignment_members_created: int = 0
    rows_skipped: int = 0
    rows_errors: int = 0
    errors: list[str] = field(default_factory=list)
    row_messages: list[str] = field(default_factory=list)

    def summary_items(self):
        return [
            ("teams_created", self.teams_created),
            ("memberships_created", self.memberships_created),
            ("service_events_created", self.service_events_created),
            ("assignments_created", self.assignments_created),
            ("assignment_members_created", self.assignment_members_created),
            ("rows_skipped", self.rows_skipped),
            ("rows_errors", self.rows_errors),
        ]


def read_csv_path(csv_path):
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as csv_file:
            return read_csv_file(csv_file)
    except FileNotFoundError as exc:
        raise ImportStructureError(f"CSV file not found: {csv_path}") from exc


def read_csv_file(csv_file):
    reader = csv.DictReader(csv_file)
    fieldnames = set(reader.fieldnames or [])
    validate_columns(fieldnames)
    return list(reader)


def validate_columns(fieldnames):
    forbidden = sorted(fieldnames & FORBIDDEN_COLUMNS)
    if forbidden:
        raise ImportStructureError(
            "Forbidden sensitive columns are not supported: "
            + ", ".join(forbidden)
        )

    missing = sorted(REQUIRED_COLUMNS - fieldnames)
    if missing:
        raise ImportStructureError("Missing required columns: " + ", ".join(missing))


def import_lighting_pilot(rows, *, dry_run=False, allow_past=False):
    stats = ImportStats()

    if dry_run:
        with transaction.atomic():
            import_rows(rows, stats, allow_past=allow_past)
            transaction.set_rollback(True)
    else:
        import_rows(rows, stats, allow_past=allow_past)

    return stats


def import_rows(rows, stats, *, allow_past):
    for index, row in enumerate(rows, start=2):
        try:
            if transaction.get_connection().in_atomic_block:
                import_row(row, stats, row_number=index, allow_past=allow_past)
            else:
                with transaction.atomic():
                    import_row(row, stats, row_number=index, allow_past=allow_past)
        except ValueError as exc:
            stats.rows_errors += 1
            stats.errors.append(f"Row {index}: {exc}")
        except Exception as exc:
            stats.rows_errors += 1
            stats.errors.append(f"Row {index}: {exc}")


def import_row(row, stats, *, row_number, allow_past):
    event_date = parse_date(value(row, "event_date"), "event_date")
    today = timezone.localdate()
    if event_date < today and not allow_past:
        stats.rows_skipped += 1
        raise ValueError("event_date is older than today; use --allow-past to import past rows.")

    event_type = value(row, "event_type")
    if event_type not in EVENT_TYPES:
        raise ValueError(f"event_type must be one of: {', '.join(sorted(EVENT_TYPES))}")

    event_title = value(row, "event_title")
    event_title_en = value(row, "event_title_en")
    assigned_member = value(row, "assigned_member")
    start_time = (
        parse_time(value(row, "start_time"), "start_time")
        if value(row, "start_time")
        else time(10, 0)
    )
    end_time = parse_time(value(row, "end_time"), "end_time") if value(row, "end_time") else None

    start_datetime = make_datetime(event_date, start_time)
    end_datetime = make_datetime(event_date, end_time) if end_time else None

    team, team_created = get_or_create_lighting_team(
        stats,
        row_number=row_number,
    )

    # MINISTRY-STRUCTURE.1F: never create a serving assignment for a
    # non-assignable (container/area) ministry unit. A freshly created lighting
    # team defaults to assignable; this only trips if an existing reused team was
    # set non-assignable. The per-row atomic block rolls back any team/event/
    # membership work done above for this row, so no partial assignment is left.
    if not team.is_assignable:
        raise ValueError(
            "Lighting team is not assignable for serving assignments; "
            "no assignment was created for this row."
        )

    playbook_link = value(row, "playbook_link")
    if playbook_link and team.playbook_link != playbook_link:
        team.playbook_link = playbook_link
        team.save(update_fields=["playbook_link", "updated_at"])

    membership = get_or_create_membership(
        team,
        assigned_member,
        value(row, "member_email"),
        stats,
    )

    event, event_created = get_or_create_service_event(
        event_type=event_type,
        event_title=event_title,
        event_title_en=event_title_en,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        row=row,
        stats=stats,
        row_number=row_number,
    )
    if event_created:
        stats.service_events_created += 1

    assignment, assignment_created = TeamAssignment.objects.get_or_create(
        service_event=event,
        ministry_team=team,
        defaults={
            "status": TeamAssignment.STATUS_SCHEDULED,
            "notes": build_assignment_notes(row),
        },
    )
    if assignment_created:
        stats.assignments_created += 1
    elif not assignment.notes:
        notes = build_assignment_notes(row)
        if notes:
            assignment.notes = notes
            assignment.save(update_fields=["notes", "updated_at"])

    _, assignment_member_created = TeamAssignmentMember.objects.get_or_create(
        assignment=assignment,
        membership=membership,
    )
    if assignment_member_created:
        stats.assignment_members_created += 1

    stats.row_messages.append(
        f"Row {row_number}: imported {event_title} for {membership.get_display_name()}."
    )


def get_or_create_lighting_team(stats, *, row_number):
    team = (
        MinistryTeam.objects.filter(
            Q(name=LIGHTING_TEAM_NAME)
            | Q(name_en=LIGHTING_TEAM_NAME_EN)
            | Q(name=LEGACY_LIGHTING_TEAM_NAME)
        )
        .order_by("id")
        .first()
    )
    if not team:
        team = MinistryTeam.objects.create(
            name=LIGHTING_TEAM_NAME,
            name_en=LIGHTING_TEAM_NAME_EN,
        )
        stats.teams_created += 1
        return team, True

    updates = []
    if team.name != LIGHTING_TEAM_NAME:
        team.name = LIGHTING_TEAM_NAME
        updates.append("name")
    if team.name_en != LIGHTING_TEAM_NAME_EN:
        team.name_en = LIGHTING_TEAM_NAME_EN
        updates.append("name_en")
    if updates:
        team.save(update_fields=updates + ["updated_at"])
        stats.row_messages.append(
            f"Row {row_number}: normalized Lighting Team to {LIGHTING_TEAM_NAME} / {LIGHTING_TEAM_NAME_EN}."
        )
    return team, False


def get_or_create_service_event(
    *,
    event_type,
    event_title,
    event_title_en,
    start_datetime,
    end_datetime,
    row,
    stats,
    row_number,
):
    title_matches = Q(title=event_title)
    if event_title_en:
        title_matches |= Q(title=event_title_en) | Q(title_en=event_title_en)

    event = (
        ServiceEvent.objects.filter(
            title_matches,
            event_type=event_type,
            start_datetime=start_datetime,
        )
        .exclude(status=ServiceEvent.STATUS_CANCELLED)
        .order_by("id")
        .first()
    )

    if not event:
        event = ServiceEvent.objects.create(
            event_type=event_type,
            title=event_title,
            title_en=event_title_en,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            description=build_event_description(row),
            description_en=build_event_description(row),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        return event, True

    updates = []
    if event.title != event_title:
        event.title = event_title
        updates.append("title")
    if event_title_en and event.title_en != event_title_en:
        event.title_en = event_title_en
        updates.append("title_en")
    if updates:
        event.save(update_fields=updates + ["updated_at"])
        stats.row_messages.append(
            f"Row {row_number}: normalized ServiceEvent title to {event_title}"
            + (f" / {event_title_en}." if event_title_en else ".")
        )
    return event, False


def get_or_create_membership(team, assigned_member, member_email, stats):
    User = get_user_model()
    user = None
    if member_email:
        user = User.objects.filter(email__iexact=member_email).first()

    if user:
        membership = TeamMembership.objects.filter(
            team=team,
            user=user,
            is_active=True,
        ).first()
        if membership:
            return membership

        membership = TeamMembership.objects.create(
            team=team,
            user=user,
            display_name=assigned_member,
            email=member_email,
        )
        stats.memberships_created += 1
        return membership

    membership = TeamMembership.objects.filter(
        team=team,
        display_name__iexact=assigned_member,
        is_active=True,
    ).first()
    if membership:
        return membership

    if member_email:
        membership = TeamMembership.objects.filter(
            team=team,
            email__iexact=member_email,
            is_active=True,
        ).first()
        if membership:
            return membership

    membership = TeamMembership.objects.create(
        team=team,
        display_name=assigned_member,
        email=member_email,
    )
    stats.memberships_created += 1
    return membership


def value(row, key):
    return (row.get(key) or "").strip()


def parse_date(raw_value, field_name):
    if not raw_value:
        raise ValueError(f"{field_name} is required.")
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format.") from exc


def parse_time(raw_value, field_name):
    try:
        return datetime.strptime(raw_value, "%H:%M").time()
    except ValueError as exc:
        raise ValueError(f"{field_name} must use HH:MM format.") from exc


def make_datetime(event_date, event_time):
    naive = datetime.combine(event_date, event_time)
    return timezone.make_aware(naive, timezone.get_current_timezone())


def build_event_description(row):
    service_detail = value(row, "service_detail")
    return service_detail[:1000]


def build_assignment_notes(row):
    note_parts = []
    for label, key in [
        ("Service detail", "service_detail"),
        ("Special event note", "special_event_note"),
        ("Worship team", "worship_team"),
    ]:
        note_value = value(row, key)
        if note_value:
            note_parts.append(f"{label}: {note_value}")
    return "\n".join(note_parts)[:1000]
