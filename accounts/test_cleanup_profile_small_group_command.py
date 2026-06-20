from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.management.commands.audit_legacy_structure_retirement_readiness import (
    run_audit as run_legacy_retirement_audit,
)
from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
    District,
    MinistryContext,
    Profile,
    SmallGroup,
)
from comments.models import ReflectionComment
from events.models import ServiceEvent
from ministry.models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from prayers.models import PrayerRequest
from reading.models import ReadingGuidePost, ReadingPlan, ReadingPlanDay
from studies.models import BibleStudySeries, BibleStudySession


User = get_user_model()


class CleanupProfileSmallGroupCommandTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.now = timezone.now()
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )
        self.ministry_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="Chinese Ministry",
        )
        self.district_unit = ChurchStructureUnit.objects.create(
            parent=self.ministry_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="NORTH",
            name="North",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.district_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4",
            name="Rainbow 4",
        )
        self.other_group_unit = ChurchStructureUnit.objects.create(
            parent=self.district_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R5",
            name="Rainbow 5",
        )
        self.inactive_group_unit = ChurchStructureUnit.objects.create(
            parent=self.district_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="OLD",
            name="Old Group",
            is_active=False,
        )
        self.ministry_context = MinistryContext.objects.create(
            code="CM",
            name="Chinese Ministry",
            church_structure_unit=self.ministry_unit,
        )
        self.district = District.objects.create(
            name="North",
            ministry_context=self.ministry_context,
            church_structure_unit=self.district_unit,
        )
        self.group = SmallGroup.objects.create(
            name="Rainbow 4",
            district=self.district,
            church_structure_unit=self.group_unit,
        )
        self.other_group = SmallGroup.objects.create(
            name="Rainbow 5",
            district=self.district,
            church_structure_unit=self.other_group_unit,
        )
        self.unmapped_group = SmallGroup.objects.create(name="Unmapped Group")
        self.inactive_unit_group = SmallGroup.objects.create(
            name="Inactive Unit Group",
            church_structure_unit=self.inactive_group_unit,
        )
        self.wrong_type_group = SmallGroup.objects.create(
            name="Wrong Type Group",
            church_structure_unit=self.district_unit,
        )

    def run_command(self, *args):
        out = StringIO()
        call_command("cleanup_profile_small_group", *args, stdout=out)
        return out.getvalue()

    def make_user(self, username, *, small_group=None):
        user = User.objects.create_user(username=username, password="pw123456")
        if small_group is not None:
            user.profile.small_group = small_group
            user.profile.save(update_fields=["small_group"])
        return user

    def add_active_primary(self, user, unit):
        return ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today - timezone.timedelta(days=1),
        )

    def bulk_active_primary(self, user, unit):
        membership = ChurchStructureMembership(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today - timezone.timedelta(days=1),
        )
        ChurchStructureMembership.objects.bulk_create([membership])
        return ChurchStructureMembership.objects.get(user=user, unit=unit)

    def test_dry_run_reports_eligible_row_and_does_not_mutate_profile_small_group(self):
        user = self.make_user("eligible", small_group=self.group)
        self.add_active_primary(user, self.group_unit)

        output = self.run_command("--verbose")

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group_id, self.group.id)
        self.assertIn("mode: dry-run", output)
        self.assertIn("candidates_with_small_group: 1", output)
        self.assertIn("eligible_to_clear: 1", output)
        self.assertIn("would_clear_count: 1", output)
        self.assertIn("remaining_blockers_after_operation: 1", output)
        self.assertIn("data_mutated: false", output)
        self.assertIn("runtime_mutated: false", output)
        self.assertIn("schema_mutated: false", output)
        self.assertIn("decision=would_clear", output)

    def test_apply_without_confirmation_refuses_to_mutate(self):
        user = self.make_user("needs_confirm", small_group=self.group)
        self.add_active_primary(user, self.group_unit)

        with self.assertRaises(CommandError):
            self.run_command("--apply")

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group_id, self.group.id)

    def test_confirmation_without_apply_remains_dry_run_and_does_not_mutate(self):
        user = self.make_user("confirm_only", small_group=self.group)
        self.add_active_primary(user, self.group_unit)

        output = self.run_command("--confirm-profile-small-group-cleanup")

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group_id, self.group.id)
        self.assertIn("mode: dry-run", output)
        self.assertIn("apply_option_present: false", output)
        self.assertIn("confirmation_option_present: true", output)
        self.assertIn("would_clear_count: 1", output)
        self.assertIn("data_mutated: false", output)

    def test_apply_with_confirmation_clears_only_safe_matching_profile_rows(self):
        safe = self.make_user("safe", small_group=self.group)
        self.add_active_primary(safe, self.group_unit)
        mismatch = self.make_user("mismatch", small_group=self.group)
        self.add_active_primary(mismatch, self.other_group_unit)
        no_group = self.make_user("no_group")
        self.add_active_primary(no_group, self.group_unit)

        output = self.run_command(
            "--apply",
            "--confirm-profile-small-group-cleanup",
        )

        safe.profile.refresh_from_db()
        mismatch.profile.refresh_from_db()
        no_group.profile.refresh_from_db()
        self.assertIsNone(safe.profile.small_group_id)
        self.assertEqual(mismatch.profile.small_group_id, self.group.id)
        self.assertIsNone(no_group.profile.small_group_id)
        self.assertIn("mode: apply", output)
        self.assertIn("candidates_with_small_group: 2", output)
        self.assertIn("eligible_to_clear: 1", output)
        self.assertIn("cleared_count: 1", output)
        self.assertIn("skipped_membership_mismatch: 1", output)
        self.assertIn("remaining_blockers_after_operation: 1", output)
        self.assertIn("data_mutated: true", output)

    def test_no_active_primary_membership_is_skipped(self):
        user = self.make_user("no_active", small_group=self.group)
        ChurchStructureMembership.objects.create(
            user=user,
            unit=self.group_unit,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=True,
        )

        output = self.run_command("--verbose")

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group_id, self.group.id)
        self.assertIn("skipped_no_active_primary_membership: 1", output)
        self.assertIn("decision=blocked", output)

    def test_multiple_active_primary_memberships_are_skipped(self):
        user = self.make_user("multiple", small_group=self.group)
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=user,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=self.today - timezone.timedelta(days=1),
                ),
                ChurchStructureMembership(
                    user=user,
                    unit=self.other_group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=self.today - timezone.timedelta(days=1),
                ),
            ]
        )

        output = self.run_command("--verbose")

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group_id, self.group.id)
        self.assertIn("skipped_multiple_active_primary_memberships: 1", output)
        self.assertIn("would_clear_count: 0", output)

    def test_unmapped_small_group_is_skipped(self):
        user = self.make_user("unmapped", small_group=self.unmapped_group)
        self.add_active_primary(user, self.group_unit)

        output = self.run_command("--verbose")

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group_id, self.unmapped_group.id)
        self.assertIn("skipped_unmapped_small_group: 1", output)

    def test_inactive_mapped_unit_is_skipped(self):
        user = self.make_user("inactive", small_group=self.inactive_unit_group)
        self.bulk_active_primary(user, self.inactive_group_unit)

        output = self.run_command("--verbose")

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group_id, self.inactive_unit_group.id)
        self.assertIn("skipped_inactive_unit: 1", output)

    def test_wrong_unit_type_is_skipped(self):
        user = self.make_user("wrong_type", small_group=self.wrong_type_group)
        self.bulk_active_primary(user, self.district_unit)

        output = self.run_command("--verbose")

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group_id, self.wrong_type_group.id)
        self.assertIn("skipped_wrong_unit_type: 1", output)

    def test_membership_mismatch_is_skipped(self):
        user = self.make_user("wrong_membership", small_group=self.group)
        self.add_active_primary(user, self.other_group_unit)

        output = self.run_command("--verbose")

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group_id, self.group.id)
        self.assertIn("skipped_membership_mismatch: 1", output)

    def test_apply_preserves_membership_structure_roles_permissions_and_app_data(self):
        user = self.make_user("preserved", small_group=self.group)
        membership = self.add_active_primary(user, self.group_unit)
        permission = Permission.objects.get(codename="change_profile")
        user.user_permissions.add(permission)
        role = ChurchRoleAssignment.objects.create(
            user=user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )
        event = ServiceEvent.objects.create(
            title="Preserved Event",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.now + timezone.timedelta(days=7),
            ministry_context=self.ministry_context,
            status=ServiceEvent.STATUS_PUBLISHED,
            created_by=user,
        )
        series = BibleStudySeries.objects.create(
            title="Preserved Series",
            scope_type=BibleStudySeries.SCOPE_SMALL_GROUP,
            small_group=self.group,
            status=BibleStudySeries.STATUS_PUBLISHED,
        )
        session = BibleStudySession.objects.create(
            series=series,
            title="Preserved Session",
            study_datetime=self.now + timezone.timedelta(days=3),
            scope_type=BibleStudySession.SCOPE_SMALL_GROUP,
            small_group=self.group,
            status=BibleStudySession.STATUS_PUBLISHED,
        )
        prayer = PrayerRequest.objects.create(
            user=user,
            title="Preserved Prayer",
            body="Please pray",
            visibility=PrayerRequest.VISIBILITY_GROUP,
            structure_unit_at_post=self.group_unit,
        )
        plan = ReadingPlan.objects.create(name="Preserved Plan")
        day = ReadingPlanDay.objects.create(
            plan=plan,
            day_number=1,
            reading_text="John 1",
        )
        guide = ReadingGuidePost.objects.create(
            active_plan=plan.active_runs.create(
                start_date=self.today,
                title="Active Plan",
            ),
            author=user,
            title="Preserved Guide",
            body="Read",
        )
        reflection = ReflectionComment.objects.create(
            plan_day=day,
            user=user,
            visibility=ReflectionComment.VISIBILITY_GROUP,
            structure_unit_at_post=self.group_unit,
            body="Reflection",
        )
        team = MinistryTeam.objects.create(name="Preserved Team")
        team_membership = TeamMembership.objects.create(team=team, user=user)
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            created_by=user,
        )
        assignment_member = TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=team_membership,
        )
        before_counts = {
            "users": User.objects.count(),
            "profiles": Profile.objects.count(),
            "memberships": ChurchStructureMembership.objects.count(),
            "units": ChurchStructureUnit.objects.count(),
            "small_groups": SmallGroup.objects.count(),
            "districts": District.objects.count(),
            "ministry_contexts": MinistryContext.objects.count(),
            "roles": ChurchRoleAssignment.objects.count(),
            "events": ServiceEvent.objects.count(),
            "series": BibleStudySeries.objects.count(),
            "sessions": BibleStudySession.objects.count(),
            "prayers": PrayerRequest.objects.count(),
            "reading_guides": ReadingGuidePost.objects.count(),
            "reflections": ReflectionComment.objects.count(),
            "teams": MinistryTeam.objects.count(),
            "team_assignments": TeamAssignment.objects.count(),
            "team_assignment_members": TeamAssignmentMember.objects.count(),
        }

        self.run_command("--apply", "--confirm-profile-small-group-cleanup")

        user.refresh_from_db()
        user.profile.refresh_from_db()
        membership.refresh_from_db()
        role.refresh_from_db()
        event.refresh_from_db()
        series.refresh_from_db()
        session.refresh_from_db()
        prayer.refresh_from_db()
        guide.refresh_from_db()
        reflection.refresh_from_db()
        team.refresh_from_db()
        team_membership.refresh_from_db()
        assignment.refresh_from_db()
        assignment_member.refresh_from_db()

        self.assertIsNone(user.profile.small_group_id)
        self.assertEqual(
            {key: model_count for key, model_count in before_counts.items()},
            {
                "users": User.objects.count(),
                "profiles": Profile.objects.count(),
                "memberships": ChurchStructureMembership.objects.count(),
                "units": ChurchStructureUnit.objects.count(),
                "small_groups": SmallGroup.objects.count(),
                "districts": District.objects.count(),
                "ministry_contexts": MinistryContext.objects.count(),
                "roles": ChurchRoleAssignment.objects.count(),
                "events": ServiceEvent.objects.count(),
                "series": BibleStudySeries.objects.count(),
                "sessions": BibleStudySession.objects.count(),
                "prayers": PrayerRequest.objects.count(),
                "reading_guides": ReadingGuidePost.objects.count(),
                "reflections": ReflectionComment.objects.count(),
                "teams": MinistryTeam.objects.count(),
                "team_assignments": TeamAssignment.objects.count(),
                "team_assignment_members": TeamAssignmentMember.objects.count(),
            },
        )
        self.assertEqual(membership.unit_id, self.group_unit.id)
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_ACTIVE)
        self.assertEqual(role.structure_unit_id, self.group_unit.id)
        self.assertTrue(user.user_permissions.filter(id=permission.id).exists())
        self.assertEqual(event.ministry_context_id, self.ministry_context.id)
        self.assertEqual(series.small_group_id, self.group.id)
        self.assertEqual(session.small_group_id, self.group.id)
        self.assertEqual(prayer.structure_unit_at_post_id, self.group_unit.id)
        self.assertEqual(guide.author_id, user.id)
        self.assertEqual(reflection.structure_unit_at_post_id, self.group_unit.id)
        self.assertEqual(team_membership.user_id, user.id)
        self.assertEqual(assignment.service_event_id, event.id)
        self.assertEqual(assignment_member.membership_id, team_membership.id)

    def test_idempotency_after_apply_reports_zero_would_clear_rows(self):
        user = self.make_user("idempotent", small_group=self.group)
        self.add_active_primary(user, self.group_unit)
        self.run_command("--apply", "--confirm-profile-small-group-cleanup")

        output = self.run_command("--verbose")

        user.profile.refresh_from_db()
        self.assertIsNone(user.profile.small_group_id)
        self.assertIn("profiles_without_small_group: 1", output)
        self.assertIn("candidates_with_small_group: 0", output)
        self.assertIn("would_clear_count: 0", output)
        self.assertIn("remaining_blockers_after_operation: 0", output)
        self.assertIn("decision=already_clear", output)

    def test_legacy_retirement_audit_reports_profile_blockers_clean_after_apply(self):
        user = self.make_user("audit_clean", small_group=self.group)
        self.add_active_primary(user, self.group_unit)

        self.run_command("--apply", "--confirm-profile-small-group-cleanup")
        audit = run_legacy_retirement_audit(
            target_date=self.today,
            now=self.now,
        )
        stats = audit["stats"]

        self.assertEqual(stats["profiles_with_small_group"], 0)
        self.assertEqual(stats["profile_small_group_removal_blockers"], 0)
        self.assertEqual(stats["profile_small_group_references"], 0)
