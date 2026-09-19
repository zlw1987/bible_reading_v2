"""Focused MO-S.6F.GENERAL.1F-1A generic confirmation-writer tests."""

import copy
from copy import deepcopy
from datetime import datetime
from io import BytesIO
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth.models import User
from django.core import signing
from django.core.management import call_command
from django.db import OperationalError, connections
from django.db.models import F
from django.test import override_settings
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from events.models import ServiceEvent, ServiceEventAudienceScope, ServiceProfile
from events.scheduling_revision import SchedulingRevisionError
from events.test_worship_xlsx_preview import (
    WorshipWorkbookDomainTestBase,
    build_known_workbook,
)
from notifications.models import Notification

from .models import MinistryTeam, TeamAssignment, TeamAssignmentMember, TeamMembership
from .services.team_roster_assignment_confirmation import (
    MAX_TEAM_ROSTER_CONFIRMATION_STATE_BYTES,
    TEAM_ROSTER_CONFIRMATION_SIGNING_SALT,
    TEAM_ROSTER_CONFIRMATION_V1,
    TeamRosterConfirmationAuditError,
    TeamRosterConfirmationError,
    TeamRosterConfirmationProposalError,
    TeamRosterConfirmationStaleError,
    apply_team_roster_confirmation,
    build_team_roster_confirmation_proposal,
    decode_team_roster_confirmation,
)
from .services.team_roster_assignment_preview import (
    MAX_TEAM_ROSTER_ASSIGNMENT_PREVIEW_STATE_BYTES,
    TeamRosterAssignmentPreviewStateTooLarge,
    TeamRosterAssignmentPreviewState,
    build_team_roster_assignment_preview,
)
from .services.team_roster_column_mapping import (
    finalize_team_roster_column_mapping,
    prepare_team_roster_column_mapping_review,
)
from .services.team_roster_person_mapping import (
    finalize_team_roster_person_mapping,
    prepare_team_roster_person_mapping,
)
from .services.worship_xlsx_preview import INTEGRATION_KEY, parse_known_worship_workbook


_XML_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def add_inline_workbook_cells(content, values):
    """Add exact text cells without disturbing cached date-formula values."""

    source = ZipFile(BytesIO(content), "r")
    root = ElementTree.fromstring(source.read("xl/worksheets/sheet1.xml"))
    sheet_data = root.find(f"{{{_XML_NS}}}sheetData")
    rows = {
        int(item.attrib["r"]): item
        for item in sheet_data.findall(f"{{{_XML_NS}}}row")
    }
    for coordinate, value in values.items():
        row_number = int(
            "".join(character for character in coordinate if character.isdigit())
        )
        row = rows[row_number]
        cell = ElementTree.Element(
            f"{{{_XML_NS}}}c", {"r": coordinate, "t": "inlineStr"}
        )
        inline = ElementTree.SubElement(cell, f"{{{_XML_NS}}}is")
        text = ElementTree.SubElement(inline, f"{{{_XML_NS}}}t")
        text.text = value
        row.append(cell)
    ElementTree.register_namespace("", _XML_NS)
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                data = ElementTree.tostring(
                    root, encoding="utf-8", xml_declaration=True
                )
            target.writestr(info, data)
    source.close()
    return output.getvalue()


@override_settings(CMS_ENABLED_INTEGRATIONS=[INTEGRATION_KEY])
class TeamRosterAssignmentConfirmationTests(WorshipWorkbookDomainTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.events = []
        for index, row in enumerate(cls.parsed.rows):
            event = ServiceEvent.objects.create(
                title=f"Confirmation Sunday {index}",
                title_en=f"Confirmation Sunday {index}",
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
        cls.projection = MinistryTeam.objects.create(
            name="Projection",
            name_en="Projection",
            team_key="test.generic.projection",
        )
        cls.sound_a = TeamMembership.objects.create(
            team=cls.sound, display_name="A"
        )
        cls.sound_b = TeamMembership.objects.create(
            team=cls.sound, display_name="B"
        )
        cls.sound_c = TeamMembership.objects.create(
            team=cls.sound, display_name="C"
        )
        cls.projection_a = TeamMembership.objects.create(
            team=cls.projection, display_name="A"
        )
        cls.projection_b = TeamMembership.objects.create(
            team=cls.projection, display_name="B"
        )
        cls.other_superuser = User.objects.create_user(
            "confirmation-other", password="pw", is_superuser=True
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

    def assignment(self, source_row, *, team=None, members=(), notes=""):
        assignment = TeamAssignment.objects.create(
            service_event=self.event_for_source_row(source_row),
            ministry_team=team or self.sound,
            status=TeamAssignment.STATUS_SCHEDULED,
            notes=notes,
            created_by=self.staff,
        )
        through = [
            TeamAssignmentMember.objects.create(
                assignment=assignment, membership=membership
            )
            for membership in members
        ]
        return assignment, through

    def reviewed_person_state(self, content, *, mapped=None):
        mapped = mapped or {"F": self.sound}
        column_review = prepare_team_roster_column_mapping_review(
            content=content,
            filename="generic.xlsx",
            user=self.staff,
            language="en",
        )
        selected_teams = {column: None for column in "CDEFGHI"}
        selected_teams.update({column: team.pk for column, team in mapped.items()})
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
        selected = {
            (group.team_id, token.token): token.prefill_membership_id
            for group in person.groups
            for token in group.token_reviews
        }
        self.assertTrue(all(selected.values()))
        reviewed = finalize_team_roster_person_mapping(
            input_state=person.signed_input_state,
            reviewed_column_state=reviewed_columns.signed_reviewed_state,
            selected_membership_ids=selected,
            user=self.staff,
            language="en",
        )
        return reviewed.signed_reviewed_state

    def workflow(self, content, *, mapped=None):
        person = self.reviewed_person_state(content, mapped=mapped)
        preview = build_team_roster_assignment_preview(
            reviewed_person_state=person,
            user=self.staff,
            language="en",
            now=self.now,
        )
        proposal = build_team_roster_confirmation_proposal(
            reviewed_person_state=person,
            assignment_preview_state=preview.signed_preview_state,
            user=self.staff,
            language="en",
            now=self.now,
        )
        return person, preview, proposal

    def apply(self, person, preview, proposal):
        return apply_team_roster_confirmation(
            reviewed_person_state=person,
            assignment_preview_state=preview.signed_preview_state,
            confirmation_state=proposal.signed_confirmation_state,
            user=self.staff,
            language="en",
            now=self.now,
        )

    def snapshot(self):
        return {
            "events": list(
                ServiceEvent.objects.order_by("id").values_list(
                    "id", "scheduling_revision", "updated_at"
                )
            ),
            "assignments": list(
                TeamAssignment.objects.order_by("id").values_list(
                    "id",
                    "service_event_id",
                    "ministry_team_id",
                    "status",
                    "notes",
                    "created_by_id",
                    "created_at",
                    "updated_at",
                    "reviewed_worship_context_fingerprint",
                )
            ),
            "members": list(
                TeamAssignmentMember.objects.order_by("id").values_list(
                    "id",
                    "assignment_id",
                    "membership_id",
                    "created_at",
                    "confirmed_at",
                    "confirmation_note",
                )
            ),
            "logs": list(LogEntry.objects.order_by("id").values_list("id", flat=True)),
        }

    def test_proposal_requires_changes_and_zero_hard_blockers(self):
        person, preview, proposal = self.workflow(build_known_workbook())
        self.assertFalse(preview.has_changes)
        self.assertIsNone(proposal)

        content = build_known_workbook(sound_overrides={4: "=1+1"})
        person = self.reviewed_person_state(content)
        preview = build_team_roster_assignment_preview(
            reviewed_person_state=person, user=self.staff, now=self.now
        )
        self.assertTrue(preview.has_hard_blockers)
        self.assertIsNone(
            build_team_roster_confirmation_proposal(
                reviewed_person_state=person,
                assignment_preview_state=preview.signed_preview_state,
                user=self.staff,
                now=self.now,
            )
        )

    def test_strict_schema_hash_user_expiry_and_tamper(self):
        person, preview, proposal = self.workflow(
            build_known_workbook(sound_overrides={4: "A"})
        )
        decoded = decode_team_roster_confirmation(
            proposal.signed_confirmation_state,
            reviewed_person_state=person,
            assignment_preview_state=preview.signed_preview_state,
            user=self.staff,
            now=self.now,
        )
        self.assertEqual(decoded.payload["contract_version"], TEAM_ROSTER_CONFIRMATION_V1)

        payload = signing.loads(
            proposal.signed_confirmation_state,
            salt=TEAM_ROSTER_CONFIRMATION_SIGNING_SALT,
        )
        malformed = deepcopy(payload)
        malformed["extra"] = True
        cases = (
            (
                signing.dumps(
                    malformed,
                    salt=TEAM_ROSTER_CONFIRMATION_SIGNING_SALT,
                    compress=True,
                ),
                person,
                preview.signed_preview_state,
                self.staff,
                None,
            ),
            (
                proposal.signed_confirmation_state[:-2] + "xx",
                person,
                preview.signed_preview_state,
                self.staff,
                None,
            ),
            (
                proposal.signed_confirmation_state,
                person,
                preview.signed_preview_state,
                self.other_superuser,
                None,
            ),
            (
                proposal.signed_confirmation_state,
                person + "x",
                preview.signed_preview_state,
                self.staff,
                None,
            ),
            (
                proposal.signed_confirmation_state,
                person,
                preview.signed_preview_state + "x",
                self.staff,
                None,
            ),
            (
                proposal.signed_confirmation_state,
                person,
                preview.signed_preview_state,
                self.staff,
                -1,
            ),
        )
        for token, person_token, preview_token, user, max_age in cases:
            with self.subTest(user=user.pk, max_age=max_age), self.assertRaises(
                TeamRosterConfirmationProposalError
            ):
                kwargs = {
                    "token": token,
                    "reviewed_person_state": person_token,
                    "assignment_preview_state": preview_token,
                    "user": user,
                    "now": self.now,
                }
                if max_age is not None:
                    kwargs["max_age"] = max_age
                decode_team_roster_confirmation(**kwargs)

    def test_mixed_same_event_create_update_claims_once_and_replays_stale(self):
        existing, existing_rows = self.assignment(
            4, members=(self.sound_a,), notes="keep exact"
        )
        parent_before = self.snapshot()["assignments"][-1]
        content = build_known_workbook(
            projection_overrides={4: "A"},
            sound_overrides={4: "A / B"},
        )
        person, preview, proposal = self.workflow(
            content, mapped={"E": self.projection, "F": self.sound}
        )
        self.assertEqual(proposal.create_count, 1)
        self.assertEqual(proposal.update_count, 1)
        result = self.apply(person, preview, proposal)

        event = self.event_for_source_row(4)
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 2)
        self.assertEqual(result.claimed_event_ids, (event.pk,))
        existing.refresh_from_db()
        self.assertEqual(self.snapshot()["assignments"][0], parent_before)
        self.assertTrue(
            TeamAssignmentMember.objects.filter(
                assignment=existing, pk=existing_rows[0].pk
            ).exists()
        )
        self.assertEqual(
            set(
                TeamAssignmentMember.objects.filter(assignment=existing).values_list(
                    "membership_id", flat=True
                )
            ),
            {self.sound_a.pk, self.sound_b.pk},
        )
        created = TeamAssignment.objects.get(
            service_event=event, ministry_team=self.projection
        )
        self.assertEqual(created.status, TeamAssignment.STATUS_SCHEDULED)
        self.assertIsNone(created.reviewed_worship_context_fingerprint)
        self.assertEqual(result.log_entry_count, 2)
        logs = {
            int(item.object_id): item
            for item in LogEntry.objects.filter(
                object_id__in=(str(existing.pk), str(created.pk))
            )
        }
        self.assertEqual(logs[existing.pk].action_flag, CHANGE)
        self.assertEqual(logs[created.pk].action_flag, ADDITION)
        self.assertEqual(
            {
                json.loads(item.change_message)["operation_id"]
                for item in logs.values()
            },
            {result.operation_id},
        )
        self.assertEqual(Notification.objects.count(), 0)

        with self.assertRaises(TeamRosterConfirmationProposalError):
            decode_team_roster_confirmation(
                proposal.signed_confirmation_state,
                reviewed_person_state=person,
                assignment_preview_state=preview.signed_preview_state,
                user=self.staff,
                now=self.now,
            )
        fresh_person = self.reviewed_person_state(
            content, mapped={"E": self.projection, "F": self.sound}
        )
        fresh_preview = build_team_roster_assignment_preview(
            reviewed_person_state=fresh_person, user=self.staff, now=self.now
        )
        changed = [
            row
            for row in fresh_preview.rows
            if row.source_cell in {"E4", "F4"}
        ]
        self.assertTrue(
            all(row.state == TeamRosterAssignmentPreviewState.EXACT_NOOP for row in changed)
        )
        self.assertIsNone(
            build_team_roster_confirmation_proposal(
                reviewed_person_state=fresh_person,
                assignment_preview_state=fresh_preview.signed_preview_state,
                user=self.staff,
                now=self.now,
            )
        )

    def test_update_add_remove_preserves_parent_and_retained_member_exactly(self):
        assignment, members = self.assignment(
            4, members=(self.sound_a, self.sound_b), notes="private notes"
        )
        members[0].confirmed_at = self.now
        members[0].confirmation_note = "private confirmation"
        members[0].save(update_fields=["confirmed_at", "confirmation_note"])
        assignment.refresh_from_db()
        parent_before = (
            assignment.pk,
            assignment.service_event_id,
            assignment.ministry_team_id,
            assignment.status,
            assignment.notes,
            assignment.created_by_id,
            assignment.created_at,
            assignment.updated_at,
            assignment.reviewed_worship_context_fingerprint,
        )
        retained_before = (
            members[0].pk,
            members[0].created_at,
            members[0].confirmed_at,
            members[0].confirmation_note,
        )
        person, preview, proposal = self.workflow(
            build_known_workbook(sound_overrides={4: "A / C"})
        )
        result = self.apply(person, preview, proposal)
        assignment.refresh_from_db()
        members[0].refresh_from_db()
        self.assertEqual(
            (
                assignment.pk,
                assignment.service_event_id,
                assignment.ministry_team_id,
                assignment.status,
                assignment.notes,
                assignment.created_by_id,
                assignment.created_at,
                assignment.updated_at,
                assignment.reviewed_worship_context_fingerprint,
            ),
            parent_before,
        )
        self.assertEqual(
            (
                members[0].pk,
                members[0].created_at,
                members[0].confirmed_at,
                members[0].confirmation_note,
            ),
            retained_before,
        )
        self.assertFalse(TeamAssignmentMember.objects.filter(pk=members[1].pk).exists())
        added = TeamAssignmentMember.objects.get(
            assignment=assignment, membership=self.sound_c
        )
        self.assertIsNone(added.confirmed_at)
        self.assertEqual(added.confirmation_note, "")
        self.assertEqual(result.removed_assignment_member_ids, (members[1].pk,))
        self.event_for_source_row(4).refresh_from_db()
        self.assertEqual(self.event_for_source_row(4).scheduling_revision, 1)

    def test_distinct_create_events_claim_once_with_two_creates_on_one_event(self):
        content = build_known_workbook(
            projection_overrides={4: "A / B", 6: "A"},
            sound_overrides={4: "A"},
        )
        person, preview, proposal = self.workflow(
            content, mapped={"E": self.projection, "F": self.sound}
        )
        result = self.apply(person, preview, proposal)
        first = self.event_for_source_row(4)
        second = self.event_for_source_row(6)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.scheduling_revision, second.scheduling_revision), (1, 1))
        self.assertEqual(result.claimed_event_ids, (first.pk, second.pk))
        self.assertEqual(len(result.created_assignment_ids), 3)
        projection_first = TeamAssignment.objects.get(
            service_event=first, ministry_team=self.projection
        )
        self.assertEqual(
            set(
                projection_first.assignment_members.values_list(
                    "membership_id", flat=True
                )
            ),
            {self.projection_a.pk, self.projection_b.pk},
        )

    def test_update_only_add_remove_empty_and_mixed_shapes_do_not_claim_events(self):
        add_parent, add_rows = self.assignment(4, members=(self.sound_a,))
        remove_parent, remove_rows = self.assignment(
            6, members=(self.sound_a, self.sound_b)
        )
        empty_parent, _empty_rows = self.assignment(7, members=())
        mixed_parent, mixed_rows = self.assignment(
            8, members=(self.sound_a, self.sound_b)
        )
        revisions = {
            row: ServiceEvent.objects.get(
                pk=self.event_for_source_row(row).pk
            ).scheduling_revision
            for row in (4, 6, 7, 8)
        }
        content = build_known_workbook(
            sound_overrides={
                4: "A / B",
                6: "A",
                7: "A / B",
                8: "A / C",
            }
        )
        person, preview, proposal = self.workflow(content)
        result = self.apply(person, preview, proposal)
        self.assertEqual(result.claimed_event_ids, ())
        self.assertEqual(
            set(result.updated_assignment_ids),
            {add_parent.pk, remove_parent.pk, empty_parent.pk, mixed_parent.pk},
        )
        expected = {
            add_parent.pk: {self.sound_a.pk, self.sound_b.pk},
            remove_parent.pk: {self.sound_a.pk},
            empty_parent.pk: {self.sound_a.pk, self.sound_b.pk},
            mixed_parent.pk: {self.sound_a.pk, self.sound_c.pk},
        }
        for assignment_id, membership_ids in expected.items():
            self.assertEqual(
                set(
                    TeamAssignmentMember.objects.filter(
                        assignment_id=assignment_id
                    ).values_list("membership_id", flat=True)
                ),
                membership_ids,
            )
        self.assertTrue(TeamAssignmentMember.objects.filter(pk=add_rows[0].pk).exists())
        self.assertTrue(TeamAssignmentMember.objects.filter(pk=remove_rows[0].pk).exists())
        self.assertFalse(TeamAssignmentMember.objects.filter(pk=remove_rows[1].pk).exists())
        self.assertTrue(TeamAssignmentMember.objects.filter(pk=mixed_rows[0].pk).exists())
        self.assertFalse(TeamAssignmentMember.objects.filter(pk=mixed_rows[1].pk).exists())
        for source_row, revision in revisions.items():
            self.assertEqual(
                ServiceEvent.objects.get(
                    pk=self.event_for_source_row(source_row).pk
                ).scheduling_revision,
                revision,
            )

    def test_prewrite_stale_drift_blocks_every_write(self):
        assignment, _members = self.assignment(4, members=(self.sound_a,))
        person, preview, proposal = self.workflow(
            build_known_workbook(sound_overrides={4: "A / B"})
        )
        TeamAssignment.objects.filter(pk=assignment.pk).update(notes="drift")
        before = self.snapshot()
        with self.assertRaises(TeamRosterConfirmationProposalError):
            self.apply(person, preview, proposal)
        self.assertEqual(self.snapshot(), before)

    def test_late_failure_rolls_back_create_claim_update_and_audit(self):
        self.assignment(4, members=(self.sound_a,))
        content = build_known_workbook(
            projection_overrides={4: "A"}, sound_overrides={4: "A / B"}
        )
        person, preview, proposal = self.workflow(
            content, mapped={"E": self.projection, "F": self.sound}
        )
        before = self.snapshot()
        with patch(
            "ministry.services.team_roster_assignment_confirmation.LogEntry.objects.log_action",
            side_effect=RuntimeError("forced audit failure"),
        ), self.assertRaises(TeamRosterConfirmationAuditError):
            self.apply(person, preview, proposal)
        self.assertEqual(self.snapshot(), before)

    def test_forced_postcondition_failure_rolls_back_whole_batch(self):
        self.assignment(4, members=(self.sound_a,))
        content = build_known_workbook(
            projection_overrides={4: "A"}, sound_overrides={4: "A / B"}
        )
        person, preview, proposal = self.workflow(
            content, mapped={"E": self.projection, "F": self.sound}
        )
        before = self.snapshot()
        with patch(
            "ministry.services.team_roster_assignment_confirmation._assert_domain_postconditions",
            side_effect=TeamRosterConfirmationStaleError("forced"),
        ), self.assertRaises(TeamRosterConfirmationStaleError):
            self.apply(person, preview, proposal)
        self.assertEqual(self.snapshot(), before)

    def test_audit_is_bounded_shared_and_has_no_private_text(self):
        assignment, member_rows = self.assignment(
            4, members=(self.sound_a,), notes="never audit assignment note"
        )
        person, preview, proposal = self.workflow(
            build_known_workbook(sound_overrides={4: "A / B"})
        )
        result = self.apply(person, preview, proposal)
        log = LogEntry.objects.get(object_id=str(assignment.pk))
        body = json.loads(log.change_message)
        self.assertEqual(log.action_flag, CHANGE)
        self.assertEqual(body["operation_id"], result.operation_id)
        self.assertEqual(body["preserved_membership_ids"], [self.sound_a.pk])
        serialized = log.change_message
        for private in (
            "never audit assignment note",
            "private",
            "notes_digest",
        ):
            self.assertNotIn(private, serialized)
        self.assertTrue(TeamAssignmentMember.objects.filter(pk=member_rows[0].pk).exists())

    def test_dense_52_event_seven_team_three_person_proposal_fits_fixed_bound(self):
        teams = [self.sound, self.projection]
        teams.extend(
            MinistryTeam.objects.create(
                name=f"Dense {index}",
                name_en=f"Dense {index}",
                team_key=f"test.generic.dense.{index}",
            )
            for index in range(5)
        )
        members = {}
        for team in teams:
            by_name = {
                membership.display_name: membership
                for membership in TeamMembership.objects.filter(team=team)
            }
            for name in ("A", "B", "C", "X"):
                if name not in by_name:
                    by_name[name] = TeamMembership.objects.create(
                        team=team, display_name=name
                    )
            members[team.pk] = by_name

        all_rows = [row.source_row for row in self.parsed.rows]
        content = build_known_workbook(
            header_overrides={
                "C": "Team C",
                "D": "Team D",
                "G": "Team G",
                "H": "Team H",
                "I": "Team I",
            },
            projection_overrides={row: "A / B / C" for row in all_rows},
            sound_overrides={row: "A / B / C" for row in all_rows},
        )
        content = add_inline_workbook_cells(
            content,
            {
                f"{column}{row}": "A / B / C"
                for column in "CDGHI"
                for row in all_rows
            },
        )
        mapping = dict(zip("CDEFGHI", teams, strict=True))

        assignments = []
        assignment_rosters = []
        index = 0
        for event in self.events:
            for team in teams:
                mode = index % 3
                index += 1
                if mode == 1:  # 121 creates
                    continue
                assignment = TeamAssignment(
                    service_event=event,
                    ministry_team=team,
                    status=TeamAssignment.STATUS_SCHEDULED,
                    created_by=self.staff,
                )
                assignments.append(assignment)
                assignment_rosters.append(
                    (assignment, ("A", "B", "X") if mode == 0 else ("A", "B", "C"))
                )
        TeamAssignment.objects.bulk_create(assignments)
        TeamAssignmentMember.objects.bulk_create(
            [
                TeamAssignmentMember(
                    assignment=assignment,
                    membership=members[assignment.ministry_team_id][name],
                )
                for assignment, roster in assignment_rosters
                for name in roster
            ]
        )

        person = self.reviewed_person_state(content, mapped=mapping)
        with self.assertRaises(TeamRosterAssignmentPreviewStateTooLarge) as raised:
            build_team_roster_assignment_preview(
                reviewed_person_state=person,
                user=self.staff,
                language="en",
                now=self.now,
            )
        self.assertGreater(
            raised.exception.actual_bytes,
            MAX_TEAM_ROSTER_ASSIGNMENT_PREVIEW_STATE_BYTES,
        )

        # Isolate the frozen confirmation-state sizing fixture without changing
        # GENERAL.1E's independently fixed production preview bound.
        with patch(
            "ministry.services.team_roster_assignment_preview."
            "MAX_TEAM_ROSTER_ASSIGNMENT_PREVIEW_STATE_BYTES",
            100_000,
        ):
            preview = build_team_roster_assignment_preview(
                reviewed_person_state=person,
                user=self.staff,
                language="en",
                now=self.now,
            )
            proposal = build_team_roster_confirmation_proposal(
                reviewed_person_state=person,
                assignment_preview_state=preview.signed_preview_state,
                user=self.staff,
                language="en",
                now=self.now,
            )
        self.assertEqual(preview.mapped_row_count, 52 * 7)
        self.assertEqual(proposal.create_count, 121)
        self.assertEqual(proposal.update_count, 122)
        self.assertEqual(proposal.add_member_count, 485)
        self.assertEqual(proposal.remove_member_count, 122)
        self.assertLessEqual(
            proposal.signed_state_bytes, MAX_TEAM_ROSTER_CONFIRMATION_STATE_BYTES
        )


class FileBackedSQLiteTeamRosterConfirmationTests(unittest.TestCase):
    """Target-like two-connection generic writer serialization proofs."""

    competing_alias = "generic_team_roster_competing"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        handle = tempfile.NamedTemporaryFile(
            prefix="generic-team-roster-confirmation-",
            suffix=".sqlite3",
            delete=False,
        )
        cls.database_path = handle.name
        handle.close()
        cls.original_default_config = copy.deepcopy(connections.databases["default"])
        connections["default"].close()
        if hasattr(connections._connections, "default"):
            delattr(connections._connections, "default")
        file_config = copy.deepcopy(cls.original_default_config)
        file_config["NAME"] = cls.database_path
        file_config["OPTIONS"] = {**file_config.get("OPTIONS", {}), "timeout": 0.1}
        file_config["TEST"] = {"NAME": None}
        connections.databases["default"] = file_config
        call_command("migrate", database="default", interactive=False, verbosity=0)
        competing_config = copy.deepcopy(file_config)
        competing_config["TEST"] = {"NAME": None}
        connections.databases[cls.competing_alias] = competing_config
        with connections["default"].cursor() as cursor:
            mode = cursor.execute("PRAGMA journal_mode=delete").fetchone()[0]
            cursor.execute("PRAGMA busy_timeout=100")
        with connections[cls.competing_alias].cursor() as cursor:
            cursor.execute("PRAGMA busy_timeout=100")
        if mode.lower() != "delete":
            raise AssertionError(f"Unexpected SQLite journal mode: {mode}")

    @classmethod
    def tearDownClass(cls):
        for alias in (cls.competing_alias, "default"):
            if alias in connections.databases:
                connections[alias].close()
            if hasattr(connections._connections, alias):
                delattr(connections._connections, alias)
        connections.databases.pop(cls.competing_alias, None)
        connections.databases["default"] = cls.original_default_config
        if os.path.exists(cls.database_path):
            os.remove(cls.database_path)
        super().tearDownClass()

    def setUp(self):
        self.integration_override = override_settings(
            CMS_ENABLED_INTEGRATIONS=[INTEGRATION_KEY]
        )
        self.integration_override.enable()
        call_command("flush", database="default", interactive=False, verbosity=0)
        self.parsed = parse_known_worship_workbook(build_known_workbook())
        self.profile = ServiceProfile.objects.create(
            key="bethany_0930_cm",
            name="Bethany 09:30",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        root = ChurchStructureUnit.objects.create(
            code="ROOT",
            name="Root",
            unit_type=ChurchStructureUnit.UNIT_ROOT,
        )
        self.cm = ChurchStructureUnit.objects.create(
            code="CM",
            name="CM",
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            parent=root,
        )
        self.events = []
        for index, row in enumerate(self.parsed.rows):
            event = ServiceEvent.objects.create(
                title=f"File Sunday {index}",
                service_profile=self.profile,
                event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
                start_datetime=timezone.make_aware(
                    datetime.combine(row.local_date, datetime.min.time()).replace(
                        hour=9, minute=30
                    ),
                    timezone.get_current_timezone(),
                ),
                status=ServiceEvent.STATUS_PUBLISHED,
            )
            ServiceEventAudienceScope.objects.create(service_event=event, unit=self.cm)
            self.events.append(event)
        self.sound = MinistryTeam.objects.create(
            name="Sound", team_key="test.file.sound"
        )
        self.projection = MinistryTeam.objects.create(
            name="Projection", team_key="test.file.projection"
        )
        self.sound_a = TeamMembership.objects.create(
            team=self.sound, display_name="A"
        )
        self.sound_b = TeamMembership.objects.create(
            team=self.sound, display_name="B"
        )
        self.projection_a = TeamMembership.objects.create(
            team=self.projection, display_name="A"
        )
        self.staff = User.objects.create_user("file_generic_staff", is_staff=True)
        self.now = timezone.make_aware(
            datetime(2026, 1, 1, 12), timezone.get_current_timezone()
        )

    def tearDown(self):
        self.integration_override.disable()

    def event_for_source_row(self, source_row):
        return self.events[
            next(
                index
                for index, row in enumerate(self.parsed.rows)
                if row.source_row == source_row
            )
        ]

    def assignment(self, *, event, team, membership):
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
            notes="preserve parent",
            created_by=self.staff,
        )
        member = TeamAssignmentMember.objects.create(
            assignment=assignment, membership=membership
        )
        return assignment, member

    def workflow(self, content, *, mapped):
        column_review = prepare_team_roster_column_mapping_review(
            content=content,
            filename="generic.xlsx",
            user=self.staff,
            language="en",
        )
        selected_teams = {column: None for column in "CDEFGHI"}
        selected_teams.update({column: team.pk for column, team in mapped.items()})
        reviewed_columns = finalize_team_roster_column_mapping(
            review=column_review,
            selected_team_ids=selected_teams,
            user=self.staff,
            language="en",
        )
        person_review = prepare_team_roster_person_mapping(
            content=content,
            filename="same.xlsx",
            reviewed_column_state=reviewed_columns.signed_reviewed_state,
            user=self.staff,
            language="en",
        )
        selected = {
            (group.team_id, token.token): token.prefill_membership_id
            for group in person_review.groups
            for token in group.token_reviews
        }
        if not all(selected.values()):
            raise AssertionError("File-backed fixture lacks an exact membership.")
        person = finalize_team_roster_person_mapping(
            input_state=person_review.signed_input_state,
            reviewed_column_state=reviewed_columns.signed_reviewed_state,
            selected_membership_ids=selected,
            user=self.staff,
            language="en",
        ).signed_reviewed_state
        preview = build_team_roster_assignment_preview(
            reviewed_person_state=person, user=self.staff, now=self.now
        )
        proposal = build_team_roster_confirmation_proposal(
            reviewed_person_state=person,
            assignment_preview_state=preview.signed_preview_state,
            user=self.staff,
            now=self.now,
        )
        return person, preview, proposal

    def apply(self, workflow):
        person, preview, proposal = workflow
        return apply_team_roster_confirmation(
            reviewed_person_state=person,
            assignment_preview_state=preview.signed_preview_state,
            confirmation_state=proposal.signed_confirmation_state,
            user=self.staff,
            now=self.now,
        )

    def test_concurrent_event_write_wins_first_and_generic_apply_is_stale(self):
        event = self.event_for_source_row(4)
        workflow = self.workflow(
            build_known_workbook(projection_overrides={4: "A"}),
            mapped={"E": self.projection},
        )
        ServiceEvent.objects.using(self.competing_alias).filter(pk=event.pk).update(
            scheduling_revision=F("scheduling_revision") + 1
        )
        with self.assertRaises(TeamRosterConfirmationError):
            self.apply(workflow)
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 1)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_concurrent_update_parent_write_wins_first_and_batch_is_stale(self):
        event = self.event_for_source_row(4)
        assignment, member = self.assignment(
            event=event, team=self.sound, membership=self.sound_a
        )
        workflow = self.workflow(
            build_known_workbook(sound_overrides={4: "A / B"}),
            mapped={"F": self.sound},
        )
        TeamAssignment.objects.using(self.competing_alias).filter(
            pk=assignment.pk
        ).update(notes="competing parent write")
        with self.assertRaises(TeamRosterConfirmationError):
            self.apply(workflow)
        self.assertTrue(TeamAssignmentMember.objects.filter(pk=member.pk).exists())
        self.assertEqual(TeamAssignmentMember.objects.count(), 1)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_generic_create_claim_wins_and_competing_writer_cannot_interleave(self):
        event = self.event_for_source_row(4)
        workflow = self.workflow(
            build_known_workbook(projection_overrides={4: "A"}),
            mapped={"E": self.projection},
        )
        from .services import team_roster_assignment_confirmation as service

        original = service._writer_aware_recompute
        competing_busy = []

        def recompute_after_competing_attempt(*args, **kwargs):
            try:
                ServiceEvent.objects.using(self.competing_alias).filter(
                    pk=event.pk
                ).update(status=ServiceEvent.STATUS_COMPLETED)
            except (OperationalError, SchedulingRevisionError):
                competing_busy.append(True)
            return original(*args, **kwargs)

        with patch.object(
            service,
            "_writer_aware_recompute",
            side_effect=recompute_after_competing_attempt,
        ):
            result = self.apply(workflow)
        self.assertEqual(competing_busy, [True])
        self.assertEqual(len(result.created_assignment_ids), 1)
        event.refresh_from_db()
        self.assertEqual(event.status, ServiceEvent.STATUS_PUBLISHED)
        self.assertEqual(event.scheduling_revision, 1)

        ServiceEvent.objects.using(self.competing_alias).filter(pk=event.pk).update(
            scheduling_revision=F("scheduling_revision") + 1
        )
        with self.assertRaises(TeamRosterConfirmationError):
            self.apply(workflow)
        self.assertEqual(TeamAssignment.objects.count(), 1)

    def test_file_backed_mixed_same_event_create_update_advances_once(self):
        event = self.event_for_source_row(4)
        assignment, preserved = self.assignment(
            event=event, team=self.sound, membership=self.sound_a
        )
        workflow = self.workflow(
            build_known_workbook(
                projection_overrides={4: "A"}, sound_overrides={4: "A / B"}
            ),
            mapped={"E": self.projection, "F": self.sound},
        )
        result = self.apply(workflow)
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 2)
        self.assertEqual(result.claimed_event_ids, (event.pk,))
        self.assertTrue(TeamAssignmentMember.objects.filter(pk=preserved.pk).exists())
        self.assertEqual(
            set(
                TeamAssignmentMember.objects.filter(assignment=assignment).values_list(
                    "membership_id", flat=True
                )
            ),
            {self.sound_a.pk, self.sound_b.pk},
        )
        self.assertEqual(TeamAssignment.objects.count(), 2)

    def test_file_backed_late_failure_rolls_back_create_claim_and_update_barrier(self):
        event = self.event_for_source_row(4)
        assignment, member = self.assignment(
            event=event, team=self.sound, membership=self.sound_a
        )
        revision_before = ServiceEvent.objects.get(pk=event.pk).scheduling_revision
        parent_before = TeamAssignment.objects.values_list(
            "status", "notes", "updated_at"
        ).get(pk=assignment.pk)
        workflow = self.workflow(
            build_known_workbook(
                projection_overrides={4: "A"}, sound_overrides={4: "A / B"}
            ),
            mapped={"E": self.projection, "F": self.sound},
        )
        from .services import team_roster_assignment_confirmation as service

        with patch.object(
            service,
            "_assert_domain_postconditions",
            side_effect=TeamRosterConfirmationStaleError("forced late failure"),
        ), self.assertRaises(TeamRosterConfirmationStaleError):
            self.apply(workflow)
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, revision_before)
        self.assertEqual(
            TeamAssignment.objects.values_list("status", "notes", "updated_at").get(
                pk=assignment.pk
            ),
            parent_before,
        )
        self.assertTrue(TeamAssignmentMember.objects.filter(pk=member.pk).exists())
        self.assertEqual(TeamAssignment.objects.count(), 1)
        self.assertEqual(TeamAssignmentMember.objects.count(), 1)
        self.assertEqual(LogEntry.objects.count(), 0)
