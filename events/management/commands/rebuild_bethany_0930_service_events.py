"""MO-S.6D-PROFILE-SETUP.1A operator command."""

import re

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from events.service_profile_setup import (
    PROFILE_EVENT_TYPE,
    PROFILE_KEY,
    PROFILE_LOCAL_TIME,
    PROFILE_YEAR,
    RESET_APPROVAL_TOKEN_LENGTH,
    ProfileSetupError,
    apply_reset,
    build_reset_preview,
)


class Command(BaseCommand):
    help = (
        "Preview or explicitly apply the bounded TEST ServiceEvent reset and "
        "canonical 2026 Bethany 09:30 setup. Dry-run is the default."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview the reset without writing. This is the default mode.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the TEST ServiceEvent reset atomically.",
        )
        parser.add_argument(
            "--confirm-test-data-reset",
            action="store_true",
            help=(
                "Acknowledge that every current ServiceEvent and its event-owned "
                "scheduling children are disposable test data."
            ),
        )
        parser.add_argument(
            "--expected-reset-token",
            help=(
                "The 16-character lowercase hexadecimal token from the exact "
                "product-owner-reviewed dry-run."
            ),
        )

    def handle(self, *args, **options):
        if options["dry_run"] and options["apply"]:
            raise CommandError("Use either --dry-run or --apply, not both.")
        if options["apply"] and not options["confirm_test_data_reset"]:
            raise CommandError(
                "--apply requires --confirm-test-data-reset. No data was changed."
            )
        expected_token = options["expected_reset_token"]
        if options["apply"] and not expected_token:
            raise CommandError(
                "--apply requires --expected-reset-token from the reviewed "
                "dry-run. No data was changed."
            )
        if options["apply"] and not re.fullmatch(
            rf"[0-9a-f]{{{RESET_APPROVAL_TOKEN_LENGTH}}}",
            expected_token,
        ):
            raise CommandError(
                "--expected-reset-token must be exactly 16 lowercase hexadecimal "
                "characters. No data was changed."
            )

        if options["apply"]:
            self.stdout.write("TEST-DATA RESET APPLY")
            self.stdout.write(
                self.style.WARNING(
                    "Run APPLY only in a maintenance window. SQLite provides a "
                    "single-writer boundary, not ServiceEvent row locks."
                )
            )
            try:
                result = apply_reset(expected_reset_token=expected_token)
            except ProfileSetupError as exc:
                raise CommandError(str(exc)) from exc
            self._write_apply_result(result)
            return

        self.stdout.write("TEST-DATA RESET PREVIEW")
        self.stdout.write("NO DATA CHANGED")
        try:
            preview = build_reset_preview()
        except ProfileSetupError as exc:
            raise CommandError(str(exc)) from exc
        self._write_preview(preview)

    def _write_preview(self, preview):
        counts = preview["before"]["counts"]
        replacement = preview["replacement"]
        audience = preview["audience"]
        self.stdout.write(
            "Existing dataset fingerprint: " + preview["before"]["fingerprint"]
        )
        self.stdout.write(
            "Approval payload SHA-256: " + preview["approval"]["payload_sha256"]
        )
        self.stdout.write("Reset approval token: " + preview["approval"]["token"])
        self.stdout.write("Existing ServiceEvent rows to delete:")
        if not preview["before"]["event_rows"]:
            self.stdout.write("  (none)")
        for event in preview["before"]["event_rows"]:
            local_start = timezone.localtime(event["start_datetime"])
            self.stdout.write(
                f"  id={event['pk']}; local_start={local_start.isoformat()}; "
                f"status={event['status']}; service_profile_id="
                f"{event['service_profile_id']}; compatibility_key="
                f"{event['service_profile_key']!r}; "
                f"title={event['title']!r}"
            )
        self.stdout.write("Deletion / dependent-change scope:")
        for key in (
            "service_events_deleted",
            "audience_rows_deleted",
            "required_team_rows_deleted",
            "planner_rows_deleted",
            "team_assignments_deleted",
            "team_assignment_members_deleted",
        ):
            self.stdout.write(f"  {key}: {counts[key]} (DB cascade/delete)")
        self.stdout.write(
            "  bible_study_links_cleared: "
            f"{counts['bible_study_links_cleared']} (SET_NULL; meeting rows survive)"
        )
        self.stdout.write("Retained historical records:")
        for key in (
            "service_event_log_entries_retained",
            "team_assignment_log_entries_retained",
            "service_event_notifications_retained",
            "team_assignment_notifications_retained",
            "assignment_member_notifications_retained",
            "worship_batch_notifications_retained",
        ):
            self.stdout.write(f"  {key}: {counts[key]}")
        self.stdout.write("Canonical replacement:")
        self.stdout.write(
            f"  events: {replacement['count']} ({replacement['rows'][0]['date']} "
            f"through {replacement['rows'][-1]['date']})"
        )
        for row in replacement["rows"]:
            self.stdout.write(
                f"  create local_start={row['start_datetime'].isoformat()}; "
                f"status={row['status']}"
            )
        self.stdout.write(
            f"  lifecycle at local today {replacement['today']}: "
            f"completed={replacement['completed']}; published={replacement['published']}"
        )
        self.stdout.write(
            f"  identity: profile_id={preview['profile'].pk}; "
            f"profile_key={PROFILE_KEY}; {PROFILE_EVENT_TYPE}; "
            f"{PROFILE_LOCAL_TIME.isoformat(timespec='minutes')} "
            f"{preview['replacement']['rows'][0]['start_datetime'].tzinfo}"
        )
        self.stdout.write(
            "  audience: unit_id="
            f"{audience.pk}; code={audience.code}; path={audience.path_label('en')!r}"
        )
        self.stdout.write("  Worship Team: unset; scheduling_revision: 0")
        self.stdout.write("Preserved / not changed:")
        self.stdout.write(
            "  users/admin accounts; Church Structure and memberships; Ministry "
            "Teams, memberships, hierarchy and role assignments; Worship pools; "
            "permissions; Bible Study rows; Reading; Prayer; Community Activities; "
            "Announcements; generic Notification and LogEntry history."
        )
        self.stdout.write(
            "Apply requires --apply, --confirm-test-data-reset, and "
            "--expected-reset-token with the exact reviewed token above."
        )

    def _write_apply_result(self, result):
        deleted = result["deleted"]
        if result["no_op"]:
            self.stdout.write(
                "Canonical Bethany 09:30 setup already matched exactly; no reset "
                "was needed."
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "TEST ServiceEvent dataset reset and canonical Bethany 09:30 "
                    "series created."
                )
            )
        self.stdout.write(
            "deleted: "
            f"ServiceEvent={deleted['service_events_deleted']}; "
            f"ServiceEventAudienceScope={deleted['audience_rows_deleted']}; "
            f"ServiceEventRequiredTeam={deleted['required_team_rows_deleted']}; "
            f"ServiceEventPlannerAssignment={deleted['planner_rows_deleted']}; "
            f"TeamAssignment={deleted['team_assignments_deleted']}; "
            f"TeamAssignmentMember={deleted['team_assignment_members_deleted']}"
        )
        self.stdout.write(
            f"BibleStudyMeeting links cleared by SET_NULL: "
            f"{deleted['bible_study_links_cleared']}"
        )
        self.stdout.write(
            f"created: ServiceEvent={result['created_events']}; "
            f"ServiceEventAudienceScope={result['created_audience_rows']}"
        )
        self.stdout.write(
            "postcondition: " + result["audit"]["recommendation"]
        )
        self.stdout.write(f"data_mutated: {str(result['data_mutated']).lower()}")
