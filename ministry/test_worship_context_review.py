import copy
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.db import OperationalError, connections, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from events.models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventRequiredTeam,
)

from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from .services.worship_context import (
    CanonicalWorshipContext,
    CanonicalWorshipRosterIdentity,
    CanonicalWorshipSemanticState,
    OWNERSHIP_TO_CANONICAL_STATE,
    build_canonical_worship_contexts,
    build_worship_contexts,
)
from .services.worship_context_review import (
    REVIEW_STATE_SIGNING_SALT,
    WorshipContextReviewState,
    WorshipReviewStateError,
    classify_downstream_worship_review,
    decode_rendered_worship_review_state,
    digest_unlinked_display_identity,
    fingerprint_canonical_worship_context,
    mint_rendered_worship_review_state,
    signature_from_canonical_context,
    RenderedWorshipReviewState,
    establish_worship_review_writer_barrier,
)
from .services.worship_governance import WorshipOwnershipConsistencyState


User = get_user_model()


class WorshipContextFingerprintContractTests(TestCase):
    def test_fixed_vectors_and_order_independence(self):
        no_selection = CanonicalWorshipContext(
            selected_team=None,
            state=CanonicalWorshipSemanticState.NO_SELECTION,
        )
        self.assertEqual(
            fingerprint_canonical_worship_context(no_selection),
            "3646f382bf75962e2fe412adb390bf2965ad633ffb27033714c300c5cba2c933",
        )
        identities = (
            CanonicalWorshipRosterIdentity(9, 101),
            CanonicalWorshipRosterIdentity(
                4, None, digest_unlinked_display_identity(" Alice ")
            ),
        )
        semantic = CanonicalWorshipContext(
            selected_team=SimpleNamespace(pk=17),
            state=CanonicalWorshipSemanticState.CONSISTENT_ROSTER,
            assignment_id=23,
            assigned_team_id=17,
            roster_identities=identities,
        )
        self.assertEqual(
            digest_unlinked_display_identity(" Alice "),
            "fa5df746f48ff156112b938298871eaefcc70949e21e1223bc57e8d9829d5d4f",
        )
        expected = (
            "ea87a3faae059fa3fc14012c3a6133b811daa2750640331ab917b0490085d489"
        )
        self.assertEqual(fingerprint_canonical_worship_context(semantic), expected)
        self.assertEqual(
            fingerprint_canonical_worship_context(
                CanonicalWorshipContext(
                    selected_team=semantic.selected_team,
                    state=semantic.state,
                    assignment_id=semantic.assignment_id,
                    assigned_team_id=semantic.assigned_team_id,
                    roster_identities=tuple(reversed(identities)),
                )
            ),
            expected,
        )

    def test_unlinked_normalization_contract(self):
        self.assertEqual(
            digest_unlinked_display_identity(" Alice "),
            digest_unlinked_display_identity("Alice"),
        )
        self.assertEqual(
            digest_unlinked_display_identity("Cafe\u0301"),
            digest_unlinked_display_identity("Café"),
        )
        self.assertNotEqual(
            digest_unlinked_display_identity("Alice"),
            digest_unlinked_display_identity("alice"),
        )
        self.assertNotEqual(
            digest_unlinked_display_identity("Alice"),
            digest_unlinked_display_identity("Alice."),
        )
        self.assertIsNone(digest_unlinked_display_identity("  "))
        self.assertIsNone(digest_unlinked_display_identity(None))

    def test_every_governance_state_has_an_explicit_semantic_mapping(self):
        mapped = set(OWNERSHIP_TO_CANONICAL_STATE)
        self.assertEqual(
            mapped,
            set(WorshipOwnershipConsistencyState)
            - {WorshipOwnershipConsistencyState.CONSISTENT},
        )


class WorshipContextReviewRuntimeTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="review_staff", password="pw", is_staff=True
        )
        self.staff.profile.preferred_language = "en"
        self.staff.profile.save(update_fields=["preferred_language"])
        self.ordinary = User.objects.create_user(
            username="ordinary", password="pw"
        )
        self.cm = ChurchStructureUnit.objects.create(
            code="CM-REVIEW",
            name="Chinese Ministry",
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
        )
        self.pool = MinistryTeam.objects.create(
            name="Worship Pool",
            is_assignable=False,
            is_worship_rotation_pool=True,
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.pool,
            parent_church_unit=self.cm,
            is_primary=True,
        )
        self.worship = MinistryTeam.objects.create(name="Worship A")
        MinistryTeamParentLink.objects.create(
            child_team=self.worship,
            parent_team=self.pool,
            is_primary=True,
        )
        self.downstream = MinistryTeam.objects.create(name="Sound")
        self.event = ServiceEvent.objects.create(
            title="Sunday",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=3),
            status=ServiceEvent.STATUS_PUBLISHED,
            rotation_anchor_team=self.worship,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=self.event, unit=self.cm
        )
        ServiceEventRequiredTeam.objects.create(
            service_event=self.event, ministry_team=self.downstream
        )
        self.worship_assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.worship,
            status=TeamAssignment.STATUS_SCHEDULED,
            notes="private",
        )
        self.worship_member = TeamMembership.objects.create(
            team=self.worship, display_name="Alice"
        )
        TeamAssignmentMember.objects.create(
            assignment=self.worship_assignment,
            membership=self.worship_member,
        )

    def signature(self):
        self.event.refresh_from_db()
        semantic = build_canonical_worship_contexts([self.event])[self.event.pk]
        return signature_from_canonical_context(semantic)

    def create_downstream(self, **kwargs):
        return TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.downstream,
            status=TeamAssignment.STATUS_SCHEDULED,
            **kwargs,
        )

    def schedule_get(self, assignment=None):
        self.client.force_login(self.staff)
        params = (
            {"assignment": assignment.pk}
            if assignment is not None
            else {"event": self.event.pk}
        )
        return self.client.get(
            reverse("team_schedule", args=[self.downstream.pk]), params
        )

    def row(self, response):
        return next(
            row
            for row in response.context["schedule_rows"]
            if row["event"].pk == self.event.pk
        )

    def test_display_and_fingerprint_share_same_typed_context(self):
        canonical = build_canonical_worship_contexts([self.event])
        display = build_worship_contexts(
            [self.event], canonical_contexts=canonical
        )[self.event.pk]
        self.assertEqual(
            canonical[self.event.pk].state,
            CanonicalWorshipSemanticState.CONSISTENT_ROSTER,
        )
        self.assertEqual(display["state"], "scheduled")
        self.assertEqual(display["member_names"], ["Alice"])
        self.assertTrue(
            signature_from_canonical_context(canonical[self.event.pk]).available
        )

    def test_roster_identity_materiality_and_nonsemantic_fields(self):
        original = self.signature().fingerprint
        self.worship_assignment.notes = "changed private note"
        self.worship_assignment.save()
        self.assertEqual(self.signature().fingerprint, original)
        TeamAssignmentMember.objects.filter(
            assignment=self.worship_assignment
        ).update(confirmation_note="changed")
        self.assertEqual(self.signature().fingerprint, original)
        self.worship_assignment.status = TeamAssignment.STATUS_CONFIRMED
        self.worship_assignment.save()
        self.assertEqual(self.signature().fingerprint, original)

        self.worship_member.display_name = "Bob"
        self.worship_member.save()
        changed = self.signature().fingerprint
        self.assertNotEqual(changed, original)
        self.worship_member.display_name = " Bob "
        self.worship_member.save()
        self.assertEqual(self.signature().fingerprint, changed)

        linked = User.objects.create_user(username="linked")
        self.worship_member.user = linked
        self.worship_member.save()
        linked_fingerprint = self.signature().fingerprint
        self.worship_member.display_name = "Label only"
        self.worship_member.save()
        linked.username = "renamed"
        linked.save()
        self.assertEqual(self.signature().fingerprint, linked_fingerprint)

    def test_member_add_remove_deactivate_and_current_set_exit_are_material(self):
        original = self.signature().fingerprint
        second = TeamMembership.objects.create(
            team=self.worship, display_name="Second"
        )
        member = TeamAssignmentMember.objects.create(
            assignment=self.worship_assignment, membership=second
        )
        added = self.signature().fingerprint
        self.assertNotEqual(added, original)
        second.is_active = False
        second.save()
        self.assertEqual(self.signature().fingerprint, original)
        second.is_active = True
        second.save()
        self.assertEqual(self.signature().fingerprint, added)
        member.delete()
        self.assertEqual(self.signature().fingerprint, original)
        self.worship_assignment.status = TeamAssignment.STATUS_COMPLETED
        self.worship_assignment.save()
        self.assertNotEqual(self.signature().fingerprint, original)

    def test_membership_delete_last_member_and_assignment_delete_are_material(self):
        roster = self.signature().fingerprint
        TeamMembership.objects.filter(pk=self.worship_member.pk).delete()
        empty = self.signature().fingerprint
        self.assertNotEqual(empty, roster)
        self.assertEqual(
            self.signature().semantic.state,
            CanonicalWorshipSemanticState.CONSISTENT_EMPTY,
        )
        self.worship_assignment.delete()
        self.assertNotEqual(self.signature().fingerprint, empty)
        self.assertEqual(
            self.signature().semantic.state,
            CanonicalWorshipSemanticState.SELECTED_UNSCHEDULED,
        )

    def test_linked_user_replacement_and_linked_unlinked_transitions_are_material(self):
        user_a = User.objects.create_user(username="linked_a")
        user_b = User.objects.create_user(username="linked_b")
        self.worship_member.user = user_a
        self.worship_member.save()
        linked_a = self.signature().fingerprint
        self.worship_member.user = user_b
        self.worship_member.save()
        linked_b = self.signature().fingerprint
        self.assertNotEqual(linked_a, linked_b)
        self.worship_member.user = None
        self.worship_member.display_name = "Alice"
        self.worship_member.save()
        unlinked = self.signature().fingerprint
        self.assertNotEqual(linked_b, unlinked)
        self.worship_member.user = user_b
        self.worship_member.save()
        self.assertEqual(self.signature().fingerprint, linked_b)

    def test_blank_unlinked_identity_is_unavailable_and_review_unknown(self):
        TeamMembership.objects.filter(pk=self.worship_member.pk).update(
            display_name=""
        )
        signature = self.signature()
        self.assertFalse(signature.available)
        downstream = self.create_downstream(
            reviewed_worship_context_fingerprint="0" * 64
        )
        self.assertEqual(
            classify_downstream_worship_review(downstream, signature),
            WorshipContextReviewState.UNKNOWN,
        )

    def test_tri_state_and_exact_return_to_reviewed_semantic(self):
        downstream = self.create_downstream()
        signature = self.signature()
        self.assertEqual(
            classify_downstream_worship_review(downstream, signature),
            WorshipContextReviewState.UNKNOWN,
        )
        downstream.reviewed_worship_context_fingerprint = signature.fingerprint
        downstream.save()
        self.assertEqual(
            classify_downstream_worship_review(downstream, self.signature()),
            WorshipContextReviewState.CURRENT,
        )
        self.worship_member.display_name = "Bob"
        self.worship_member.save()
        self.assertEqual(
            classify_downstream_worship_review(downstream, self.signature()),
            WorshipContextReviewState.REVIEW_RECOMMENDED,
        )
        self.worship_member.display_name = "Alice"
        self.worship_member.save()
        self.assertEqual(
            classify_downstream_worship_review(downstream, self.signature()),
            WorshipContextReviewState.CURRENT,
        )

    def test_no_assignment_and_worship_pool_children_have_no_review_state(self):
        signature = self.signature()
        self.assertIsNone(
            classify_downstream_worship_review(None, signature)
        )
        other_worship = MinistryTeam.objects.create(name="Worship B")
        MinistryTeamParentLink.objects.create(
            child_team=other_worship,
            parent_team=self.pool,
            is_primary=True,
        )
        worship_assignment = TeamAssignment(
            service_event=self.event,
            ministry_team=other_worship,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignment.objects.bulk_create([worship_assignment])
        worship_assignment = TeamAssignment.objects.get(pk=worship_assignment.pk)
        self.assertIsNone(
            classify_downstream_worship_review(worship_assignment, signature)
        )

    def test_protected_state_rejects_tamper_wrong_user_expiry_and_shape(self):
        downstream = self.create_downstream()
        signature = self.signature()
        token = mint_rendered_worship_review_state(
            user=self.staff,
            event=self.event,
            team=self.downstream,
            assignment=downstream,
            signature=signature,
        )
        decoded = decode_rendered_worship_review_state(
            token,
            user=self.staff,
            event_id=self.event.pk,
            team_id=self.downstream.pk,
            assignment_id=downstream.pk,
        )
        self.assertEqual(decoded.expected_fingerprint, signature.fingerprint)
        for kwargs in (
            {"token": token + "x"},
            {"token": token, "user": self.ordinary},
            {"token": token, "event_id": self.event.pk + 1},
        ):
            values = {
                "token": token,
                "user": self.staff,
                "event_id": self.event.pk,
                "team_id": self.downstream.pk,
                "assignment_id": downstream.pk,
            }
            values.update(kwargs)
            with self.assertRaises(WorshipReviewStateError):
                decode_rendered_worship_review_state(**values)
        with self.assertRaises(WorshipReviewStateError):
            decode_rendered_worship_review_state(
                token,
                user=self.staff,
                event_id=self.event.pk,
                team_id=self.downstream.pk,
                assignment_id=downstream.pk,
                max_age=-1,
            )
        payload = signing.loads(token, salt=REVIEW_STATE_SIGNING_SALT)
        payload["expected_fingerprint"] = "BAD"
        malformed = signing.dumps(payload, salt=REVIEW_STATE_SIGNING_SALT)
        with self.assertRaises(WorshipReviewStateError):
            decode_rendered_worship_review_state(
                malformed,
                user=self.staff,
                event_id=self.event.pk,
                team_id=self.downstream.pk,
                assignment_id=downstream.pk,
            )

    def test_mark_reviewed_success_replay_stale_and_zero_side_effects(self):
        downstream = self.create_downstream(notes="keep")
        response = self.schedule_get(downstream)
        row = self.row(response)
        token = row["worship_review_token"]
        before_revision = ServiceEvent.objects.get(pk=self.event.pk).scheduling_revision
        before_members = TeamAssignmentMember.objects.filter(
            assignment=downstream
        ).count()
        with patch("ministry.views.emit_assignment_notifications") as emit:
            result = self.client.post(
                reverse("mark_worship_context_reviewed", args=[downstream.pk]),
                {"worship_review_state": token},
            )
        self.assertEqual(result.status_code, 302)
        emit.assert_not_called()
        downstream.refresh_from_db()
        self.assertEqual(
            downstream.reviewed_worship_context_fingerprint,
            self.signature().fingerprint,
        )
        self.assertEqual(downstream.notes, "keep")
        self.assertEqual(
            TeamAssignmentMember.objects.filter(assignment=downstream).count(),
            before_members,
        )
        self.assertEqual(
            ServiceEvent.objects.get(pk=self.event.pk).scheduling_revision,
            before_revision,
        )
        first_updated = downstream.updated_at
        self.client.post(
            reverse("mark_worship_context_reviewed", args=[downstream.pk]),
            {"worship_review_state": token},
        )
        downstream.refresh_from_db()
        self.assertEqual(downstream.updated_at, first_updated)

    def test_mark_reviewed_rejects_context_changed_after_render(self):
        downstream = self.create_downstream()
        token = self.row(self.schedule_get(downstream))["worship_review_token"]
        second = TeamMembership.objects.create(
            team=self.worship, display_name="Second"
        )
        TeamAssignmentMember.objects.create(
            assignment=self.worship_assignment, membership=second
        )
        self.client.post(
            reverse("mark_worship_context_reviewed", args=[downstream.pk]),
            {"worship_review_state": token},
        )
        downstream.refresh_from_db()
        self.assertIsNone(downstream.reviewed_worship_context_fingerprint)

    def test_mark_reviewed_denies_ordinary_but_allows_exact_team_lead(self):
        downstream = self.create_downstream()
        token = self.row(self.schedule_get(downstream))["worship_review_token"]
        self.client.force_login(self.ordinary)
        denied = self.client.post(
            reverse("mark_worship_context_reviewed", args=[downstream.pk]),
            {"worship_review_state": token},
        )
        self.assertEqual(denied.status_code, 302)
        downstream.refresh_from_db()
        self.assertIsNone(downstream.reviewed_worship_context_fingerprint)

        lead = User.objects.create_user(username="sound_lead", password="pw")
        role = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="Lead",
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.downstream, role_type=role, user=lead
        )
        self.client.force_login(lead)
        get_response = self.client.get(
            reverse("team_schedule", args=[self.downstream.pk]),
            {"assignment": downstream.pk},
        )
        lead_token = self.row(get_response)["worship_review_token"]
        allowed = self.client.post(
            reverse("mark_worship_context_reviewed", args=[downstream.pk]),
            {"worship_review_state": lead_token},
        )
        self.assertEqual(allowed.status_code, 302)
        downstream.refresh_from_db()
        self.assertIsNotNone(downstream.reviewed_worship_context_fingerprint)

    def test_team_schedule_create_acknowledges_exact_rendered_context(self):
        response = self.schedule_get()
        row = self.row(response)
        token = row["worship_review_token"]
        result = self.client.post(
            f"{reverse('team_schedule', args=[self.downstream.pk])}"
            f"?event={self.event.pk}",
            {
                "assigned_members": [],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "created",
                "worship_review_state": token,
            },
        )
        self.assertEqual(result.status_code, 302)
        downstream = TeamAssignment.objects.get(
            service_event=self.event, ministry_team=self.downstream
        )
        self.assertEqual(
            downstream.reviewed_worship_context_fingerprint,
            self.signature().fingerprint,
        )

    def test_team_schedule_edit_rolls_back_all_fields_when_context_stale(self):
        downstream_member = TeamMembership.objects.create(
            team=self.downstream, display_name="Sound Person"
        )
        downstream = self.create_downstream(notes="before")
        token = self.row(self.schedule_get(downstream))["worship_review_token"]
        second = TeamMembership.objects.create(
            team=self.worship, display_name="Second"
        )
        TeamAssignmentMember.objects.create(
            assignment=self.worship_assignment, membership=second
        )
        result = self.client.post(
            f"{reverse('team_schedule', args=[self.downstream.pk])}"
            f"?assignment={downstream.pk}",
            {
                "assigned_members": [downstream_member.pk],
                "status": TeamAssignment.STATUS_CONFIRMED,
                "notes": "after",
                "worship_review_state": token,
            },
        )
        self.assertEqual(result.status_code, 200)
        self.assertContains(
            result,
            "Worship scheduling changed while you were reviewing.",
        )
        downstream.refresh_from_db()
        self.assertEqual(downstream.notes, "before")
        self.assertEqual(downstream.status, TeamAssignment.STATUS_SCHEDULED)
        self.assertIsNone(downstream.reviewed_worship_context_fingerprint)
        self.assertFalse(
            TeamAssignmentMember.objects.filter(assignment=downstream).exists()
        )

    def test_board_projects_compact_review_state_without_token(self):
        downstream = self.create_downstream()
        self.client.force_login(self.staff)
        response = self.client.get(reverse("sunday_schedule_board"))
        self.assertContains(response, "Worship review status unavailable")
        self.assertNotContains(
            response, self.signature().fingerprint
        )
        self.assertNotContains(response, "worship_review_state")

    def test_generic_direct_save_retains_review_without_claiming_fresh_review(self):
        downstream = self.create_downstream(
            reviewed_worship_context_fingerprint="1" * 64
        )
        downstream.notes = "generic edit"
        downstream.save()
        downstream.refresh_from_db()
        self.assertEqual(
            downstream.reviewed_worship_context_fingerprint, "1" * 64
        )
        new_assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=MinistryTeam.objects.create(name="Projection"),
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.assertIsNone(
            new_assignment.reviewed_worship_context_fingerprint
        )


class FileBackedSQLiteWorshipReviewConcurrencyTests(unittest.TestCase):
    """Two real connections prove the SQLite first-write/current-truth barrier."""

    alias_a = "worship_review_file_a"
    alias_b = "worship_review_file_b"

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(
            prefix="worship-review-", suffix=".sqlite3", delete=False
        )
        self.database_path = handle.name
        handle.close()
        for alias in (self.alias_a, self.alias_b):
            config = copy.deepcopy(connections.databases["default"])
            config["NAME"] = self.database_path
            config["OPTIONS"] = {**config.get("OPTIONS", {}), "timeout": 0.1}
            config["TEST"] = {"NAME": None}
            connections.databases[alias] = config
        self.connection_a = connections[self.alias_a]
        self.connection_b = connections[self.alias_b]
        with self.connection_a.cursor() as cursor:
            mode = cursor.execute("PRAGMA journal_mode=delete").fetchone()[0]
            cursor.execute("PRAGMA busy_timeout=100")
        with self.connection_b.cursor() as cursor:
            cursor.execute("PRAGMA busy_timeout=100")
        self.assertEqual(mode.lower(), "delete")
        with self.connection_a.schema_editor() as editor:
            editor.create_model(ServiceEvent)
            editor.create_model(MinistryTeam)
            editor.create_model(TeamMembership)
            editor.create_model(TeamAssignment)
            editor.create_model(TeamAssignmentMember)
        for connection in (self.connection_a, self.connection_b):
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA foreign_keys=OFF")

        MinistryTeam.objects.using(self.alias_a).bulk_create(
            [
                MinistryTeam(id=1, name="Worship"),
                MinistryTeam(id=2, name="Sound"),
            ]
        )
        ServiceEvent.objects.using(self.alias_a).bulk_create(
            [
                ServiceEvent(
                    id=1,
                    title="Sunday",
                    event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
                    start_datetime=timezone.now() + timezone.timedelta(days=1),
                    status=ServiceEvent.STATUS_PUBLISHED,
                    rotation_anchor_team_id=1,
                )
            ]
        )
        TeamAssignment.objects.using(self.alias_a).bulk_create(
            [
                TeamAssignment(
                    id=1,
                    service_event_id=1,
                    ministry_team_id=1,
                    status=TeamAssignment.STATUS_SCHEDULED,
                ),
                TeamAssignment(
                    id=2,
                    service_event_id=1,
                    ministry_team_id=2,
                    status=TeamAssignment.STATUS_SCHEDULED,
                    notes="before",
                ),
            ]
        )
        TeamMembership.objects.using(self.alias_a).bulk_create(
            [
                TeamMembership(id=1, team_id=1, display_name="Alice"),
                TeamMembership(id=2, team_id=1, display_name="Bob"),
            ]
        )
        TeamAssignmentMember.objects.using(self.alias_a).bulk_create(
            [TeamAssignmentMember(assignment_id=1, membership_id=1)]
        )

    def tearDown(self):
        for alias in (self.alias_a, self.alias_b):
            wrapper = connections[alias]
            wrapper.close()
            connections.databases.pop(alias, None)
            if hasattr(connections._connections, alias):
                delattr(connections._connections, alias)
        if os.path.exists(self.database_path):
            os.remove(self.database_path)

    def fingerprint(self, *, alias):
        membership_ids = tuple(
            TeamAssignmentMember.objects.using(alias)
            .filter(assignment_id=1, membership__is_active=True)
            .order_by("membership_id")
            .values_list("membership_id", flat=True)
        )
        semantic = CanonicalWorshipContext(
            selected_team=SimpleNamespace(pk=1),
            state=CanonicalWorshipSemanticState.CONSISTENT_ROSTER,
            assignment_id=1,
            assigned_team_id=1,
            roster_identities=tuple(
                CanonicalWorshipRosterIdentity(
                    membership_id=membership_id,
                    user_id=None,
                    display_identity_digest=digest_unlinked_display_identity(
                        TeamMembership.objects.using(alias)
                        .get(pk=membership_id)
                        .display_name
                    ),
                )
                for membership_id in membership_ids
            ),
        )
        return fingerprint_canonical_worship_context(semantic)

    def state(self, expected):
        assignment = TeamAssignment.objects.using(self.alias_a).get(pk=2)
        return RenderedWorshipReviewState(
            user_id=1,
            event_id=1,
            team_id=2,
            assignment_id=2,
            expected_fingerprint=expected,
            prior_reviewed_fingerprint=None,
            assignment_updated_at=assignment.updated_at,
            assignment_state="existing",
        )

    def add_bob(self, *, alias):
        TeamAssignmentMember.objects.using(alias).bulk_create(
            [TeamAssignmentMember(assignment_id=1, membership_id=2)]
        )

    def test_upstream_roster_write_wins_then_review_fails_stale(self):
        expected_a = self.fingerprint(alias=self.alias_a)
        state = self.state(expected_a)
        self.add_bob(alias=self.alias_b)
        with transaction.atomic(using=self.alias_a):
            establish_worship_review_writer_barrier(
                state, using=self.alias_a
            )
            current_b = self.fingerprint(alias=self.alias_a)
            self.assertNotEqual(current_b, expected_a)
        downstream = TeamAssignment.objects.using(self.alias_a).get(pk=2)
        self.assertIsNone(downstream.reviewed_worship_context_fingerprint)

    def test_review_barrier_wins_then_later_roster_write_warns(self):
        expected_a = self.fingerprint(alias=self.alias_a)
        state = self.state(expected_a)
        with transaction.atomic(using=self.alias_a):
            establish_worship_review_writer_barrier(
                state, using=self.alias_a
            )
            with self.assertRaises(OperationalError):
                self.add_bob(alias=self.alias_b)
            TeamAssignment.objects.using(self.alias_a).filter(pk=2).update(
                reviewed_worship_context_fingerprint=expected_a
            )
        self.add_bob(alias=self.alias_b)
        downstream = TeamAssignment.objects.using(self.alias_a).get(pk=2)
        self.assertEqual(
            downstream.reviewed_worship_context_fingerprint, expected_a
        )
        self.assertNotEqual(self.fingerprint(alias=self.alias_a), expected_a)

    def test_schedule_write_is_atomic_and_later_roster_write_warns(self):
        expected_a = self.fingerprint(alias=self.alias_a)
        state = self.state(expected_a)
        with transaction.atomic(using=self.alias_a):
            establish_worship_review_writer_barrier(
                state, using=self.alias_a
            )
            with self.assertRaises(OperationalError):
                self.add_bob(alias=self.alias_b)
            TeamAssignment.objects.using(self.alias_a).filter(pk=2).update(
                notes="after",
                status=TeamAssignment.STATUS_CONFIRMED,
                reviewed_worship_context_fingerprint=expected_a,
            )
        self.add_bob(alias=self.alias_b)
        downstream = TeamAssignment.objects.using(self.alias_a).get(pk=2)
        self.assertEqual(downstream.notes, "after")
        self.assertEqual(downstream.status, TeamAssignment.STATUS_CONFIRMED)
        self.assertEqual(
            downstream.reviewed_worship_context_fingerprint, expected_a
        )
        self.assertNotEqual(self.fingerprint(alias=self.alias_a), expected_a)
