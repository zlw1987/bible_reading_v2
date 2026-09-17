"""Focused MO-S.6F.GENERAL.1E generic ZERO-WRITE preview tests."""

from datetime import datetime
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import signing
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.models import ChurchStructureMembership
from core.integration_registry import IntegrationDisabled
from events.models import ServiceEvent, ServiceEventAudienceScope
from events.test_worship_xlsx_preview import (
    WorshipWorkbookDomainTestBase,
    build_known_workbook,
)

from .models import MinistryTeam, TeamAssignment, TeamAssignmentMember, TeamMembership
from .services.team_roster_assignment_preview import (
    ASSIGNMENT_PREVIEW_SIGNING_SALT,
    MAX_TEAM_ROSTER_ASSIGNMENT_PREVIEW_STATE_BYTES,
    TEAM_ROSTER_ASSIGNMENT_PREVIEW_V1,
    TeamRosterAssignmentPreviewError,
    TeamRosterAssignmentPreviewState,
    build_team_roster_assignment_preview,
    decode_team_roster_assignment_preview,
)
from .services.team_roster_column_mapping import (
    finalize_team_roster_column_mapping,
    prepare_team_roster_column_mapping_review,
)
from .services.team_roster_person_mapping import (
    finalize_team_roster_person_mapping,
    prepare_team_roster_person_mapping,
)
from .services.worship_xlsx_preview import INTEGRATION_KEY


@override_settings(CMS_ENABLED_INTEGRATIONS=[INTEGRATION_KEY])
class TeamRosterAssignmentPreviewTests(WorshipWorkbookDomainTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.events = []
        for index, row in enumerate(cls.parsed.rows):
            event = ServiceEvent.objects.create(
                title=f"Roster Sunday {index}",
                title_en=f"Roster Sunday {index}",
                service_profile=cls.target_profile,
                event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
                start_datetime=timezone.make_aware(
                    datetime.combine(row.local_date, datetime.min.time()).replace(
                        hour=9, minute=30
                    ),
                    timezone.get_current_timezone(),
                ),
                status=ServiceEvent.STATUS_PUBLISHED,
            )
            ServiceEventAudienceScope.objects.create(service_event=event, unit=cls.cm)
            cls.events.append(event)
        cls.sound = MinistryTeam.objects.create(
            name="Sound", name_en="Sound", team_key="test.generic.sound"
        )
        cls.a = TeamMembership.objects.create(team=cls.sound, display_name="A")
        cls.b = TeamMembership.objects.create(team=cls.sound, display_name="B")
        cls.c = TeamMembership.objects.create(team=cls.sound, display_name="C")
        cls.linked_user = User.objects.create_user("outside-audience", password="pw")
        cls.linked = TeamMembership.objects.create(
            team=cls.sound, user=cls.linked_user, display_name="Linked"
        )
        cls.superuser = User.objects.create_user(
            "preview-super", password="pw", is_superuser=True, is_staff=False
        )
        cls.now = timezone.make_aware(
            datetime(2026, 1, 1, 12), timezone.get_current_timezone()
        )

    def event_for_source_row(self, source_row):
        index = next(
            index
            for index, row in enumerate(self.parsed.rows)
            if row.source_row == source_row
        )
        return self.events[index]

    def assignment(self, source_row, *, status="scheduled", members=()):
        assignment = TeamAssignment.objects.create(
            service_event=self.event_for_source_row(source_row),
            ministry_team=self.sound,
            status=status,
            created_by=self.staff,
        )
        created = []
        for membership in members:
            created.append(
                TeamAssignmentMember.objects.create(
                    assignment=assignment, membership=membership
                )
            )
        return assignment, created

    def reviewed_person_state(self, content, *, mapped=None):
        mapped = mapped or {"F": self.sound}
        column_review = prepare_team_roster_column_mapping_review(
            content=content,
            filename="generic.xlsx",
            user=self.staff,
            language="en",
        )
        selected_teams = {column: None for column in "CDEFGHI"}
        selected_teams.update(
            {column: team.pk for column, team in mapped.items()}
        )
        reviewed_columns = finalize_team_roster_column_mapping(
            review=column_review,
            selected_team_ids=selected_teams,
            user=self.staff,
            language="en",
        )
        person = prepare_team_roster_person_mapping(
            content=content,
            filename="same-bytes.xlsx",
            reviewed_column_state=reviewed_columns.signed_reviewed_state,
            user=self.staff,
            language="en",
        )
        selected_memberships = {}
        for group in person.groups:
            for token in group.token_reviews:
                self.assertIsNotNone(
                    token.prefill_membership_id,
                    msg=f"Test fixture token {token.token!r} needs an exact member",
                )
                selected_memberships[(group.team_id, token.token)] = (
                    token.prefill_membership_id
                )
        reviewed_people = finalize_team_roster_person_mapping(
            input_state=person.signed_input_state,
            reviewed_column_state=reviewed_columns.signed_reviewed_state,
            selected_membership_ids=selected_memberships,
            user=self.staff,
            language="en",
        )
        return reviewed_people.signed_reviewed_state

    def preview(self, content, *, mapped=None, now=None):
        state = self.reviewed_person_state(content, mapped=mapped)
        return state, build_team_roster_assignment_preview(
            reviewed_person_state=state,
            user=self.staff,
            language="en",
            now=now or self.now,
        )

    def rows_by_cell(self, preview):
        return {row.source_cell: row for row in preview.rows}

    def test_precedence_and_create_noop_update_blank_history_source_states(self):
        _noop, noop_members = self.assignment(6, members=(self.b, self.a))
        _add, add_members = self.assignment(7, members=(self.a,))
        _remove, remove_members = self.assignment(8, members=(self.a, self.b))
        self.assignment(9, status=TeamAssignment.STATUS_CONFIRMED, members=(self.a,))
        self.assignment(12, members=(self.a,))
        ServiceEvent.objects.filter(pk=self.event_for_source_row(11).pk).update(
            status=ServiceEvent.STATUS_COMPLETED
        )
        content = build_known_workbook(
            sound_overrides={
                4: "A / B / C",
                6: "A / B",
                7: "A / B",
                8: "A",
                9: "A / B",
                10: "A / / B",
                11: "=1+1",
            }
        )
        _state, preview = self.preview(content)
        rows = self.rows_by_cell(preview)
        self.assertEqual(
            rows["F4"].state, TeamRosterAssignmentPreviewState.CREATE_CANDIDATE
        )
        self.assertEqual(rows["F4"].diff.add_ids, (self.a.pk, self.b.pk, self.c.pk))
        self.assertEqual(rows["F6"].state, TeamRosterAssignmentPreviewState.EXACT_NOOP)
        self.assertEqual(
            rows["F6"].preserved_assignment_member_ids,
            tuple(sorted(item.pk for item in noop_members)),
        )
        self.assertEqual(
            rows["F7"].state,
            TeamRosterAssignmentPreviewState.ROSTER_UPDATE_CANDIDATE,
        )
        self.assertEqual(rows["F7"].diff.preserved_ids, (self.a.pk,))
        self.assertEqual(rows["F7"].diff.add_ids, (self.b.pk,))
        self.assertEqual(
            rows["F7"].preserved_assignment_member_ids, (add_members[0].pk,)
        )
        self.assertEqual(
            rows["F8"].state,
            TeamRosterAssignmentPreviewState.ROSTER_UPDATE_CANDIDATE,
        )
        self.assertEqual(rows["F8"].diff.remove_ids, (self.b.pk,))
        self.assertEqual(
            rows["F8"].preserved_assignment_member_ids, (remove_members[0].pk,)
        )
        self.assertEqual(
            rows["F9"].state,
            TeamRosterAssignmentPreviewState.UNSAFE_ROSTER_UPDATE_BLOCKER,
        )
        self.assertEqual(
            rows["F10"].state, TeamRosterAssignmentPreviewState.SOURCE_BLOCKER
        )
        self.assertEqual(
            rows["F11"].state,
            TeamRosterAssignmentPreviewState.HISTORICAL_EVENT_SKIP,
        )
        self.assertEqual(
            rows["F12"].state,
            TeamRosterAssignmentPreviewState.NO_SOURCE_PROPOSAL,
        )
        self.assertIsNone(rows["F12"].diff)

    def test_create_cardinalities_empty_current_and_mixed_update(self):
        d = TeamMembership.objects.create(team=self.sound, display_name="D")
        empty_assignment, _members = self.assignment(9, members=())
        mixed_assignment, mixed_members = self.assignment(
            10, members=(self.a, self.b)
        )
        content = build_known_workbook(
            sound_overrides={
                4: "A",
                6: "A / B",
                7: "A / B / C",
                8: "A / B / C / D",
                9: "A / B",
                10: "A / C",
            }
        )
        _state, preview = self.preview(content)
        rows = self.rows_by_cell(preview)

        expected_create_ids = {
            "F4": (self.a.pk,),
            "F6": (self.a.pk, self.b.pk),
            "F7": (self.a.pk, self.b.pk, self.c.pk),
            "F8": (self.a.pk, self.b.pk, self.c.pk, d.pk),
        }
        for cell, expected_ids in expected_create_ids.items():
            with self.subTest(cell=cell):
                self.assertEqual(
                    rows[cell].state,
                    TeamRosterAssignmentPreviewState.CREATE_CANDIDATE,
                )
                self.assertEqual(rows[cell].diff.add_ids, expected_ids)

        self.assertEqual(
            rows["F9"].state,
            TeamRosterAssignmentPreviewState.ROSTER_UPDATE_CANDIDATE,
        )
        self.assertEqual(rows["F9"].current_assignment_id, empty_assignment.pk)
        self.assertEqual(rows["F9"].diff.add_ids, (self.a.pk, self.b.pk))
        self.assertEqual(rows["F9"].diff.preserved_ids, ())
        self.assertEqual(rows["F9"].diff.remove_ids, ())

        self.assertEqual(
            rows["F10"].state,
            TeamRosterAssignmentPreviewState.ROSTER_UPDATE_CANDIDATE,
        )
        self.assertEqual(rows["F10"].current_assignment_id, mixed_assignment.pk)
        self.assertEqual(rows["F10"].diff.preserved_ids, (self.a.pk,))
        self.assertEqual(rows["F10"].diff.add_ids, (self.c.pk,))
        self.assertEqual(rows["F10"].diff.remove_ids, (self.b.pk,))
        self.assertEqual(
            rows["F10"].preserved_assignment_member_ids,
            (mixed_members[0].pk,),
        )

    def test_invalid_removed_membership_surfaces_block_the_whole_diff(self):
        other_team = MinistryTeam.objects.create(
            name="Other", name_en="Other", team_key="test.generic.other"
        )
        _wrong_team_assignment, _members = self.assignment(
            4, members=(self.a, self.b)
        )
        _inactive_assignment, _members = self.assignment(
            6, members=(self.a, self.c)
        )
        TeamMembership.objects.filter(pk=self.b.pk).update(team=other_team)
        TeamMembership.objects.filter(pk=self.c.pk).update(is_active=False)

        _state, preview = self.preview(
            build_known_workbook(sound_overrides={4: "A", 6: "A"})
        )
        rows = self.rows_by_cell(preview)
        for cell in ("F4", "F6"):
            with self.subTest(cell=cell):
                self.assertEqual(
                    rows[cell].state,
                    TeamRosterAssignmentPreviewState.UNSAFE_ROSTER_UPDATE_BLOCKER,
                )
                self.assertEqual(rows[cell].reason_code, "protected_member_removal")

    def test_protected_remove_and_assignment_anomaly_states(self):
        _protected, protected_members = self.assignment(4, members=(self.a, self.b))
        protected_members[1].confirmation_note = "keep private"
        protected_members[1].save(update_fields=["confirmation_note"])
        self.assignment(6, members=(self.a,))
        self.assignment(6, members=(self.b,))
        self.assignment(7, status=TeamAssignment.STATUS_COMPLETED, members=(self.a,))
        unknown, _members = self.assignment(8, members=(self.a,))
        TeamAssignment.objects.filter(pk=unknown.pk).update(status="unexpected")
        invalid, _members = self.assignment(9, members=(self.a,))
        TeamAssignment.objects.filter(pk=invalid.pk).update(
            reviewed_worship_context_fingerprint="A" * 64
        )
        content = build_known_workbook(
            sound_overrides={4: "A", 6: "A", 7: "A", 8: "A", 9: "A"}
        )
        _state, preview = self.preview(content)
        rows = self.rows_by_cell(preview)
        self.assertEqual(
            rows["F4"].state,
            TeamRosterAssignmentPreviewState.UNSAFE_ROSTER_UPDATE_BLOCKER,
        )
        self.assertEqual(
            rows["F6"].state,
            TeamRosterAssignmentPreviewState.DUPLICATE_ASSIGNMENT_BLOCKER,
        )
        self.assertEqual(
            rows["F7"].state,
            TeamRosterAssignmentPreviewState.HISTORICAL_ASSIGNMENT_BLOCKER,
        )
        self.assertEqual(
            rows["F8"].state,
            TeamRosterAssignmentPreviewState.UNKNOWN_ASSIGNMENT_BLOCKER,
        )
        self.assertEqual(
            rows["F9"].state,
            TeamRosterAssignmentPreviewState.INVALID_ASSIGNMENT_BLOCKER,
        )

    def test_confirmed_prepared_exact_noop_and_difference_rules(self):
        self.assignment(4, status=TeamAssignment.STATUS_CONFIRMED, members=(self.a,))
        self.assignment(6, status=TeamAssignment.STATUS_PREPARED, members=(self.a,))
        self.assignment(7, status=TeamAssignment.STATUS_PREPARED, members=(self.a,))
        content = build_known_workbook(
            sound_overrides={4: "A", 6: "A", 7: "A / B"}
        )
        _state, preview = self.preview(content)
        rows = self.rows_by_cell(preview)
        self.assertEqual(rows["F4"].state, TeamRosterAssignmentPreviewState.EXACT_NOOP)
        self.assertEqual(rows["F6"].state, TeamRosterAssignmentPreviewState.EXACT_NOOP)
        self.assertEqual(
            rows["F7"].state,
            TeamRosterAssignmentPreviewState.UNSAFE_ROSTER_UPDATE_BLOCKER,
        )

    def test_confirmed_member_remove_is_protected(self):
        _assignment, members = self.assignment(4, members=(self.a, self.b))
        members[1].confirmed_at = self.now
        members[1].save(update_fields=["confirmed_at"])
        _state, preview = self.preview(
            build_known_workbook(sound_overrides={4: "A"})
        )
        row = self.rows_by_cell(preview)["F4"]
        self.assertEqual(
            row.state,
            TeamRosterAssignmentPreviewState.UNSAFE_ROSTER_UPDATE_BLOCKER,
        )
        self.assertEqual(row.diff.remove_ids, (self.b.pk,))

    def test_worship_fingerprint_null_lowercase_and_malformed_contract(self):
        valid, _members = self.assignment(4, members=(self.a,))
        TeamAssignment.objects.filter(pk=valid.pk).update(
            reviewed_worship_context_fingerprint="a" * 64
        )
        upper, _members = self.assignment(6, members=(self.a,))
        mixed, _members = self.assignment(7, members=(self.a,))
        short, _members = self.assignment(8, members=(self.a,))
        TeamAssignment.objects.filter(pk=upper.pk).update(
            reviewed_worship_context_fingerprint="A" * 64
        )
        TeamAssignment.objects.filter(pk=mixed.pk).update(
            reviewed_worship_context_fingerprint="a" * 63 + "B"
        )
        TeamAssignment.objects.filter(pk=short.pk).update(
            reviewed_worship_context_fingerprint="a" * 63
        )
        content = build_known_workbook(
            sound_overrides={4: "A", 6: "A", 7: "A", 8: "A"}
        )
        _state, preview = self.preview(content)
        rows = self.rows_by_cell(preview)
        self.assertEqual(rows["F4"].state, TeamRosterAssignmentPreviewState.EXACT_NOOP)
        self.assertEqual(
            preview.normalized_payload["assignments"][0][
                "reviewed_worship_context_fingerprint"
            ],
            "a" * 64,
        )
        for cell in ("F6", "F7", "F8"):
            self.assertEqual(
                rows[cell].state,
                TeamRosterAssignmentPreviewState.INVALID_ASSIGNMENT_BLOCKER,
            )

    def test_audience_checks_only_new_linked_user_grants(self):
        ChurchStructureMembership.objects.create(
            user=self.staff,
            unit=self.cm,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
            approved_by=self.staff,
            approved_at=timezone.now(),
        )
        linked_in_audience = TeamMembership.objects.create(
            team=self.sound, user=self.staff, display_name="In Audience"
        )
        self.assignment(6, members=(self.linked,))
        content = build_known_workbook(
            sound_overrides={4: "Linked", 6: "Linked", 7: "In Audience"}
        )
        _state, preview = self.preview(content)
        rows = self.rows_by_cell(preview)
        self.assertEqual(
            rows["F4"].state, TeamRosterAssignmentPreviewState.AUDIENCE_BLOCKER
        )
        self.assertEqual(rows["F6"].state, TeamRosterAssignmentPreviewState.EXACT_NOOP)
        self.assertEqual(
            rows["F7"].state, TeamRosterAssignmentPreviewState.CREATE_CANDIDATE
        )
        self.assertEqual(rows["F7"].diff.add_ids, (linked_in_audience.pk,))

    def test_audience_readiness_drift_fails_before_assignment_query(self):
        content = build_known_workbook(sound_overrides={4: "A"})
        person_state = self.reviewed_person_state(content)
        ServiceEventAudienceScope.objects.filter(
            service_event=self.event_for_source_row(4)
        ).delete()
        with patch(
            "ministry.services.team_roster_assignment_preview._assignment_queryset"
        ) as assignment_query, self.assertRaises(TeamRosterAssignmentPreviewError):
            build_team_roster_assignment_preview(
                reviewed_person_state=person_state,
                user=self.staff,
                now=self.now,
            )
        assignment_query.assert_not_called()

    def test_canonical_worship_governance_allows_exact_and_blocks_wrong_target(self):
        MinistryTeam.objects.filter(pk=self.c1.pk).update(
            team_key="test.generic.worship.c1"
        )
        self.c1.refresh_from_db()
        ServiceEvent.objects.filter(pk=self.event_for_source_row(4).pk).update(
            rotation_anchor_team=self.c1
        )
        ServiceEvent.objects.filter(pk=self.event_for_source_row(6).pk).update(
            rotation_anchor_team=self.c2
        )
        worship_member = TeamMembership.objects.create(
            team=self.c1, display_name="Worship Member"
        )
        content = build_known_workbook(
            sound_overrides={4: "Worship Member", 6: "Worship Member"}
        )
        _state, preview = self.preview(content, mapped={"F": self.c1})
        rows = self.rows_by_cell(preview)
        self.assertEqual(
            rows["F4"].state, TeamRosterAssignmentPreviewState.CREATE_CANDIDATE
        )
        self.assertEqual(
            rows["F6"].state, TeamRosterAssignmentPreviewState.GOVERNANCE_BLOCKER
        )
        self.assertEqual(rows["F4"].reviewed_membership_ids, (worship_member.pk,))

    def test_signed_preview_is_private_strict_stale_and_zero_write(self):
        assignment, member_rows = self.assignment(4, members=(self.a,))
        assignment.notes = "private assignment note"
        assignment.save(update_fields=["notes"])
        member_rows[0].confirmation_note = "private confirmation note"
        member_rows[0].save(update_fields=["confirmation_note"])
        content = build_known_workbook(sound_overrides={4: "A"})
        person_state = self.reviewed_person_state(content)
        before = self.domain_snapshot()
        with CaptureQueriesContext(connection) as queries:
            preview = build_team_roster_assignment_preview(
                reviewed_person_state=person_state,
                user=self.staff,
                now=self.now,
            )
            decoded = decode_team_roster_assignment_preview(
                preview.signed_preview_state,
                reviewed_person_state=person_state,
                user=self.staff,
                now=self.now,
            )
        self.assertEqual(decoded.normalized_payload, preview.normalized_payload)
        payload = signing.loads(
            preview.signed_preview_state, salt=ASSIGNMENT_PREVIEW_SIGNING_SALT
        )
        self.assertEqual(payload["contract_version"], TEAM_ROSTER_ASSIGNMENT_PREVIEW_V1)
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("private assignment note", serialized)
        self.assertNotIn("private confirmation note", serialized)
        self.assertIn("notes_digest", serialized)
        self.assertIn("confirmation_note_digest", serialized)
        sql = [item["sql"].lstrip().lower() for item in queries]
        self.assertFalse(
            any(statement.startswith(("insert", "update", "delete")) for statement in sql)
        )
        self.assertEqual(self.domain_snapshot(), before)

        TeamAssignment.objects.filter(pk=assignment.pk).update(notes="changed")
        with self.assertRaises(TeamRosterAssignmentPreviewError):
            decode_team_roster_assignment_preview(
                preview.signed_preview_state,
                reviewed_person_state=person_state,
                user=self.staff,
                now=self.now,
            )

    def test_signed_preview_member_confirmation_and_fingerprint_drift(self):
        assignment, members = self.assignment(4, members=(self.a,))
        content = build_known_workbook(sound_overrides={4: "A"})
        person_state, preview = self.preview(content)

        members[0].confirmation_note = "changed after preview"
        members[0].save(update_fields=["confirmation_note"])
        with self.assertRaises(TeamRosterAssignmentPreviewError):
            decode_team_roster_assignment_preview(
                preview.signed_preview_state,
                reviewed_person_state=person_state,
                user=self.staff,
                now=self.now,
            )

        members[0].confirmation_note = ""
        members[0].save(update_fields=["confirmation_note"])
        TeamAssignment.objects.filter(pk=assignment.pk).update(
            reviewed_worship_context_fingerprint="b" * 64
        )
        with self.assertRaises(TeamRosterAssignmentPreviewError):
            decode_team_roster_assignment_preview(
                preview.signed_preview_state,
                reviewed_person_state=person_state,
                user=self.staff,
                now=self.now,
            )

    def test_strict_decoder_detects_status_timestamp_member_and_revision_drift(self):
        assignments = {}
        member_rows = {}
        for source_row in (4, 6, 7, 8):
            assignment, members = self.assignment(source_row, members=(self.a,))
            assignments[source_row] = assignment
            member_rows[source_row] = members[0]
        content = build_known_workbook(
            sound_overrides={source_row: "A" for source_row in (4, 6, 7, 8)}
        )

        person_state, preview = self.preview(content)
        TeamAssignment.objects.filter(pk=assignments[4].pk).update(
            status=TeamAssignment.STATUS_CONFIRMED
        )
        with self.assertRaises(TeamRosterAssignmentPreviewError):
            decode_team_roster_assignment_preview(
                preview.signed_preview_state,
                reviewed_person_state=person_state,
                user=self.staff,
                now=self.now,
            )

        person_state, preview = self.preview(content)
        TeamAssignment.objects.filter(pk=assignments[6].pk).update(
            updated_at=self.now
        )
        with self.assertRaises(TeamRosterAssignmentPreviewError):
            decode_team_roster_assignment_preview(
                preview.signed_preview_state,
                reviewed_person_state=person_state,
                user=self.staff,
                now=self.now,
            )

        person_state, preview = self.preview(content)
        TeamAssignmentMember.objects.create(
            assignment=assignments[7], membership=self.b
        )
        with self.assertRaises(TeamRosterAssignmentPreviewError):
            decode_team_roster_assignment_preview(
                preview.signed_preview_state,
                reviewed_person_state=person_state,
                user=self.staff,
                now=self.now,
            )

        person_state, preview = self.preview(content)
        TeamAssignmentMember.objects.filter(pk=member_rows[8].pk).update(
            confirmed_at=self.now
        )
        with self.assertRaises(TeamRosterAssignmentPreviewError):
            decode_team_roster_assignment_preview(
                preview.signed_preview_state,
                reviewed_person_state=person_state,
                user=self.staff,
                now=self.now,
            )

        person_state, preview = self.preview(content)
        event = self.event_for_source_row(9)
        ServiceEvent.objects.filter(pk=event.pk).update(
            scheduling_revision=event.scheduling_revision + 1
        )
        with self.assertRaises(TeamRosterAssignmentPreviewError):
            decode_team_roster_assignment_preview(
                preview.signed_preview_state,
                reviewed_person_state=person_state,
                user=self.staff,
                now=self.now,
            )

    def test_signed_preview_rejects_extra_schema_keys(self):
        content = build_known_workbook(sound_overrides={4: "A"})
        person_state, preview = self.preview(content)
        payload = signing.loads(
            preview.signed_preview_state, salt=ASSIGNMENT_PREVIEW_SIGNING_SALT
        )
        payload["extra"] = True
        malformed = signing.dumps(
            payload, salt=ASSIGNMENT_PREVIEW_SIGNING_SALT, compress=True
        )
        with self.assertRaises(TeamRosterAssignmentPreviewError):
            decode_team_roster_assignment_preview(
                malformed,
                reviewed_person_state=person_state,
                user=self.staff,
                now=self.now,
            )

    def domain_snapshot(self):
        return {
            "events": list(
                ServiceEvent.objects.order_by("id").values_list(
                    "id", "scheduling_revision", "rotation_anchor_team_id"
                )
            ),
            "teams": list(
                MinistryTeam.objects.order_by("id").values_list(
                    "id", "is_active", "is_assignable"
                )
            ),
            "memberships": list(
                TeamMembership.objects.order_by("id").values_list(
                    "id", "is_active", "updated_at"
                )
            ),
            "assignments": list(
                TeamAssignment.objects.order_by("id").values_list(
                    "id", "status", "notes", "updated_at"
                )
            ),
            "members": list(
                TeamAssignmentMember.objects.order_by("id").values_list(
                    "id", "membership_id", "confirmed_at", "confirmation_note"
                )
            ),
        }

    def test_authority_tamper_wrong_user_expiry_and_assignment_drift_fail(self):
        content = build_known_workbook(sound_overrides={4: "A"})
        person_state, preview = self.preview(content)
        cases = (
            (preview.signed_preview_state[:-2] + "xx", self.staff, None),
            (preview.signed_preview_state, self.superuser, None),
            (preview.signed_preview_state, self.staff, -1),
        )
        for token, user, max_age in cases:
            with self.subTest(user=user.username, max_age=max_age), self.assertRaises(
                TeamRosterAssignmentPreviewError
            ):
                kwargs = {
                    "token": token,
                    "reviewed_person_state": person_state,
                    "user": user,
                    "now": self.now,
                }
                if max_age is not None:
                    kwargs["max_age"] = max_age
                decode_team_roster_assignment_preview(**kwargs)

        assignment, _members = self.assignment(6, members=(self.a,))
        # This post-review assignment changes the event revision, so GENERAL.1D
        # authority fails before GENERAL.1E queries assignment truth.
        with patch(
            "ministry.services.team_roster_assignment_preview._assignment_queryset"
        ) as assignment_query, self.assertRaises(TeamRosterAssignmentPreviewError):
            decode_team_roster_assignment_preview(
                preview.signed_preview_state,
                reviewed_person_state=person_state,
                user=self.staff,
                now=self.now,
            )
        self.assertIsNotNone(assignment.pk)
        assignment_query.assert_not_called()

    @override_settings(CMS_ENABLED_INTEGRATIONS=[])
    def test_disabled_integration_blocks_before_assignment_query(self):
        with patch(
            "ministry.services.team_roster_assignment_preview._assignment_queryset"
        ) as assignment_query, self.assertRaises(IntegrationDisabled):
            build_team_roster_assignment_preview(
                reviewed_person_state="unused", user=self.staff, now=self.now
            )
        assignment_query.assert_not_called()

    def test_52_rows_seven_mapped_teams_stay_inside_16384_bytes(self):
        extra_teams = [
            MinistryTeam.objects.create(
                name=f"Extra {index}",
                name_en=f"Extra {index}",
                team_key=f"test.generic.extra.{index}",
            )
            for index in range(6)
        ]
        mapped = {
            column: team
            for column, team in zip(
                "CDEFGHI",
                [*extra_teams[:3], self.sound, *extra_teams[3:]],
                strict=True,
            )
        }
        content = build_known_workbook(
            header_overrides={
                "C": "C team",
                "D": "D team",
                "G": "G team",
                "H": "H team",
                "I": "I team",
            },
            sound_overrides={row.source_row: "A" for row in self.parsed.rows},
        )
        _state, preview = self.preview(content, mapped=mapped)
        self.assertEqual(preview.mapped_row_count, 52 * 7)
        self.assertLessEqual(
            preview.signed_state_bytes,
            MAX_TEAM_ROSTER_ASSIGNMENT_PREVIEW_STATE_BYTES,
        )
