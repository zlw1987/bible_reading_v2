"""Guarded purge for retired legacy BibleStudySession pilot data.

BS-V1-PURGE.1A cleanup tooling only. Dry-run is the default and writes
nothing. Destructive mode is intentionally double-gated and limited to V1
``BibleStudySession`` rows plus V1-only child rows.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date

from studies.models import (
    BibleStudyGuide,
    BibleStudySession,
    BibleStudyWorshipSong,
)


_ZERO_PROTECTED_COUNTERS = (
    "v2_series_deleted",
    "v2_lessons_deleted",
    "v2_meetings_deleted",
    "v2_meeting_roles_deleted",
    "v2_meeting_worship_songs_deleted",
    "church_structure_rows_deleted",
)


def _bool(value):
    return "true" if value else "false"


def _group_label(group):
    if group is None:
        return "(none)"
    return f"#{group.id} {group.name}"


def _series_label(series):
    if series is None:
        return "(none)"
    return f"#{series.id} {series.title}"


def _build_session_queryset(*, session_id=None, status=None, before=None):
    sessions = BibleStudySession.objects.select_related(
        "series",
        "small_group",
    ).order_by("id")

    if session_id is not None:
        sessions = sessions.filter(id=session_id)
    if status:
        sessions = sessions.filter(status=status)
    if before is not None:
        sessions = sessions.filter(study_datetime__date__lt=before)

    return sessions


def _collect_plan(*, session_id=None, status=None, before=None, example_limit=20):
    sessions = _build_session_queryset(
        session_id=session_id,
        status=status,
        before=before,
    )
    session_ids = list(sessions.values_list("id", flat=True))

    guides = BibleStudyGuide.objects.filter(session_id__in=session_ids)
    worship_songs = BibleStudyWorshipSong.objects.filter(session_id__in=session_ids)

    examples = list(sessions[:example_limit]) if example_limit else []
    return {
        "session_ids": session_ids,
        "v1_sessions_matched": len(session_ids),
        "v1_guides_matched": guides.count(),
        "v1_worship_songs_matched": worship_songs.count(),
        "examples": examples,
        "example_limit": example_limit,
        "examples_omitted": max(len(session_ids) - len(examples), 0),
    }


def _delete_plan(plan):
    with transaction.atomic():
        guide_deleted_total, guide_details = BibleStudyGuide.objects.filter(
            session_id__in=plan["session_ids"],
        ).delete()
        song_deleted_total, song_details = BibleStudyWorshipSong.objects.filter(
            session_id__in=plan["session_ids"],
        ).delete()
        session_deleted_total, session_details = BibleStudySession.objects.filter(
            id__in=plan["session_ids"],
        ).delete()

    return {
        "v1_guides_deleted": guide_deleted_total,
        "v1_worship_songs_deleted": song_deleted_total,
        "v1_sessions_deleted": session_deleted_total,
        "django_delete_details": {
            **guide_details,
            **song_details,
            **session_details,
        },
    }


class Command(BaseCommand):
    help = (
        "Dry-run or explicitly purge retired legacy V1 BibleStudySession pilot "
        "rows and V1-only child rows. Destructive mode requires both --apply "
        "and --confirm-v1-bible-study-retirement. It never deletes Bible Study "
        "V2 rows, church-structure rows, users, profiles, roles, events, "
        "reading data, prayers, or reflections."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually delete matched V1 BibleStudySession, BibleStudyGuide, "
                "and BibleStudyWorshipSong rows. Requires "
                "--confirm-v1-bible-study-retirement."
            ),
        )
        parser.add_argument(
            "--confirm-v1-bible-study-retirement",
            action="store_true",
            help=(
                "Required confirmation for --apply. This acknowledges V1 "
                "BibleStudySession app runtime is retired and the matched rows "
                "are pilot/archive cleanup data."
            ),
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            dest="verbose_examples",
            help=(
                "Print capped examples of matched V1 sessions. Does not print "
                "guide body, discussion questions, or worship notes."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help=(
                "Maximum verbose example rows to print. This does not limit "
                "the matched purge scope; use --session-id, --status, or "
                "--before to narrow scope."
            ),
        )
        parser.add_argument(
            "--session-id",
            type=int,
            default=None,
            help="Match only one V1 BibleStudySession id.",
        )
        parser.add_argument(
            "--status",
            choices=[choice[0] for choice in BibleStudySession.STATUS_CHOICES],
            default=None,
            help="Match only V1 sessions with this status.",
        )
        parser.add_argument(
            "--before",
            default=None,
            help="Match only V1 sessions with study_datetime before YYYY-MM-DD.",
        )

    def handle(self, *args, **options):
        apply_mode = options["apply"]
        confirmation_present = options["confirm_v1_bible_study_retirement"]

        if options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        if apply_mode and not confirmation_present:
            raise CommandError(
                "--apply requires --confirm-v1-bible-study-retirement. "
                "No data was deleted."
            )

        before = None
        if options["before"]:
            before = parse_date(options["before"])
            if before is None:
                raise CommandError("--before must use YYYY-MM-DD.")

        plan = _collect_plan(
            session_id=options["session_id"],
            status=options["status"],
            before=before,
            example_limit=options["limit"],
        )

        deleted = {
            "v1_sessions_deleted": 0,
            "v1_guides_deleted": 0,
            "v1_worship_songs_deleted": 0,
            "django_delete_details": {},
        }
        if apply_mode:
            deleted = _delete_plan(plan)

        self._print_report(
            plan=plan,
            deleted=deleted,
            apply_mode=apply_mode,
            confirmation_present=confirmation_present,
            verbose_examples=options["verbose_examples"],
            filters={
                "session_id": options["session_id"],
                "status": options["status"],
                "before": options["before"] or "",
            },
        )

    def _print_report(
        self,
        *,
        plan,
        deleted,
        apply_mode,
        confirmation_present,
        verbose_examples,
        filters,
    ):
        write = self.stdout.write

        write("Legacy BibleStudySession V1 purge (BS-V1-PURGE.1A)")
        write("=" * 58)
        write(f"mode: {'apply' if apply_mode else 'dry-run'}")
        write(f"apply_option_present: {_bool(apply_mode)}")
        write(f"confirmation_present: {_bool(confirmation_present)}")
        write(f"data_mutated: {_bool(apply_mode)}")
        write(f"filter_session_id: {filters['session_id'] or ''}")
        write(f"filter_status: {filters['status'] or ''}")
        write(f"filter_before: {filters['before']}")
        write(f"v1_sessions_matched: {plan['v1_sessions_matched']}")
        write(f"v1_guides_matched: {plan['v1_guides_matched']}")
        write(f"v1_worship_songs_matched: {plan['v1_worship_songs_matched']}")
        write(f"v1_sessions_deleted: {deleted['v1_sessions_deleted']}")
        write(f"v1_guides_deleted: {deleted['v1_guides_deleted']}")
        write(f"v1_worship_songs_deleted: {deleted['v1_worship_songs_deleted']}")
        for key in _ZERO_PROTECTED_COUNTERS:
            write(f"{key}: 0")

        if apply_mode:
            write(
                "apply_result: deleted matched V1 sessions and V1-only child "
                "rows inside one transaction"
            )
            write(f"django_delete_details: {deleted['django_delete_details']}")
        else:
            write(
                "dry_run_result: no rows deleted; rerun with --apply and "
                "--confirm-v1-bible-study-retirement to purge explicitly"
            )

        if verbose_examples:
            write("")
            write(f"verbose_examples_limit: {plan['example_limit']}")
            if plan["examples"]:
                write("matched_v1_session_examples:")
                for session in plan["examples"]:
                    write(
                        "  session id: {id} | title: {title} | series: {series} "
                        "| study_datetime: {study_datetime} | status: {status} "
                        "| small_group: {small_group}".format(
                            id=session.id,
                            title=session.title,
                            series=_series_label(session.series),
                            study_datetime=session.study_datetime,
                            status=session.status,
                            small_group=_group_label(session.small_group),
                        )
                    )
            else:
                write("matched_v1_session_examples: (none)")
            if plan["examples_omitted"]:
                write(
                    "stopped at --limit {shown}; {omitted} more matched V1 "
                    "session(s) not printed".format(
                        shown=len(plan["examples"]),
                        omitted=plan["examples_omitted"],
                    )
                )
