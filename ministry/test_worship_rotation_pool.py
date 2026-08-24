"""Focused MO-S.6D-1B Worship rotation-pool foundation tests."""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from events.models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventRequiredTeam,
)
from notifications.models import Notification

from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from .permissions import (
    can_manage_ministry_team,
    can_manage_team_assignment_for_team,
)
from .structure_readiness import run_audit
from .worship_rotation_pool import (
    WorshipRotationPoolStatus,
    inspect_worship_rotation_pool,
)


class WorshipRotationPoolConfigurationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="pool_user", password="pw")
        self.anchor = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="华语事工",
            name_en="Chinese Ministry",
        )
        self.pool = MinistryTeam.objects.create(
            name="敬拜事工",
            name_en="Worship Ministry",
            team_kind=MinistryTeam.KIND_MINISTRY_AREA,
            is_assignable=False,
            is_worship_rotation_pool=True,
        )

    def add_anchor(self, team=None, *, primary=True):
        return MinistryTeamParentLink.objects.create(
            child_team=team or self.pool,
            parent_church_unit=self.anchor,
            is_primary=primary,
        )

    def test_field_defaults_false_and_explicit_non_assignable_pool_is_valid(self):
        ordinary = MinistryTeam.objects.create(name="普通团队", name_en="Ordinary")
        self.assertFalse(ordinary.is_worship_rotation_pool)
        self.pool.full_clean()
        self.assertTrue(self.pool.is_worship_rotation_pool)
        self.assertFalse(self.pool.is_assignable)

    def test_pool_and_assignable_is_rejected_without_silent_toggle(self):
        malformed = MinistryTeam(
            name="Invalid",
            is_assignable=True,
            is_worship_rotation_pool=True,
        )
        with self.assertRaises(ValidationError) as raised:
            malformed.full_clean()
        self.assertEqual(
            raised.exception.error_dict["is_worship_rotation_pool"][0].code,
            MinistryTeam.WORSHIP_ROTATION_POOL_ASSIGNABLE_ERROR_CODE,
        )
        self.assertTrue(malformed.is_assignable)
        self.assertTrue(malformed.is_worship_rotation_pool)

    def test_direct_malformed_state_is_detected_fail_closed(self):
        MinistryTeam.objects.filter(pk=self.pool.pk).update(is_assignable=True)
        self.pool.refresh_from_db()
        result = inspect_worship_rotation_pool(self.pool)
        self.assertEqual(result.status, WorshipRotationPoolStatus.ASSIGNABLE_POOL)
        self.assertFalse(result.is_usable)
        audit = run_audit(team_id=self.pool.id)
        self.assertEqual(audit["stats"]["worship_rotation_pools_assignable"], 1)
        self.assertIn("worship_rotation_pools_assignable", audit["blockers"])

    def test_inactive_pool_retains_flag_and_is_non_operational_info(self):
        self.assertFalse(can_manage_ministry_team(self.user, self.pool))
        self.pool.is_active = False
        self.pool.full_clean()
        self.pool.save(update_fields=["is_active", "updated_at"])
        self.pool.refresh_from_db()
        self.assertTrue(self.pool.is_worship_rotation_pool)
        result = inspect_worship_rotation_pool(self.pool)
        self.assertEqual(result.status, WorshipRotationPoolStatus.INACTIVE_POOL)
        self.assertFalse(result.is_usable)
        self.assertFalse(can_manage_ministry_team(self.user, self.pool))
        audit = run_audit(team_id=self.pool.id)
        self.assertEqual(audit["stats"]["inactive_worship_rotation_pools"], 1)
        self.assertNotIn("inactive_worship_rotation_pools", audit["blockers"])

    def test_valid_primary_path_resolves_active_church_anchor(self):
        parent = MinistryTeam.objects.create(
            name="主日事工", name_en="Sunday Ministry", is_assignable=False
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.pool, parent_team=parent, is_primary=True
        )
        MinistryTeamParentLink.objects.create(
            child_team=parent, parent_church_unit=self.anchor, is_primary=True
        )
        result = inspect_worship_rotation_pool(self.pool)
        self.assertEqual(result.status, WorshipRotationPoolStatus.VALID)
        self.assertEqual(result.anchor, self.anchor)
        self.assertTrue(result.is_usable)

    def test_missing_or_secondary_only_anchor_fails_closed(self):
        self.assertEqual(
            inspect_worship_rotation_pool(self.pool).status,
            WorshipRotationPoolStatus.MISSING_PRIMARY_PATH,
        )
        self.add_anchor(primary=False)
        self.assertEqual(
            inspect_worship_rotation_pool(self.pool).status,
            WorshipRotationPoolStatus.MISSING_PRIMARY_PATH,
        )

    def test_inactive_anchor_fails_closed(self):
        self.add_anchor()
        self.anchor.is_active = False
        self.anchor.save(update_fields=["is_active", "updated_at"])
        result = inspect_worship_rotation_pool(self.pool)
        self.assertEqual(
            result.status, WorshipRotationPoolStatus.INACTIVE_CHURCH_ANCHOR
        )
        self.assertEqual(result.anchor, self.anchor)

    def test_inactive_primary_parent_team_fails_closed(self):
        parent = MinistryTeam.objects.create(
            name="Retired Parent", is_assignable=False
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.pool, parent_team=parent, is_primary=True
        )
        parent.is_active = False
        parent.save(update_fields=["is_active", "updated_at"])
        self.assertEqual(
            inspect_worship_rotation_pool(self.pool).status,
            WorshipRotationPoolStatus.INACTIVE_PRIMARY_TEAM,
        )

    def test_ambiguous_primary_path_corruption_fails_closed(self):
        self.add_anchor()
        other_anchor = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="EM",
            name="英语事工",
            name_en="English Ministry",
        )
        MinistryTeamParentLink.objects.bulk_create(
            [
                MinistryTeamParentLink(
                    child_team=self.pool,
                    parent_church_unit=other_anchor,
                    is_primary=True,
                )
            ]
        )
        self.assertEqual(
            inspect_worship_rotation_pool(self.pool).status,
            WorshipRotationPoolStatus.AMBIGUOUS_PRIMARY_PATH,
        )

    def test_cyclic_primary_path_corruption_fails_closed(self):
        parent = MinistryTeam.objects.create(name="Parent", is_assignable=False)
        MinistryTeamParentLink.objects.bulk_create(
            [
                MinistryTeamParentLink(
                    child_team=self.pool, parent_team=parent, is_primary=True
                ),
                MinistryTeamParentLink(
                    child_team=parent, parent_team=self.pool, is_primary=True
                ),
            ]
        )
        self.assertEqual(
            inspect_worship_rotation_pool(self.pool).status,
            WorshipRotationPoolStatus.CYCLIC_PRIMARY_PATH,
        )

    def test_valid_pool_without_canonical_leadership_is_warning(self):
        self.add_anchor()
        result = inspect_worship_rotation_pool(self.pool)
        self.assertFalse(result.has_active_leadership)
        audit = run_audit(team_id=self.pool.id)
        self.assertEqual(
            audit["stats"]["worship_rotation_pools_missing_leadership"], 1
        )
        self.assertIn(
            "worship_rotation_pools_missing_leadership", audit["warnings"]
        )

    def test_active_date_valid_lead_or_coordinator_satisfies_readiness(self):
        self.add_anchor()
        coordinator = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_COORDINATOR,
            name="协调同工",
            name_en="Coordinator",
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.pool,
            role_type=coordinator,
            user=self.user,
            start_date=timezone.localdate(),
        )
        result = inspect_worship_rotation_pool(self.pool)
        self.assertTrue(result.has_active_leadership)
        audit = run_audit(team_id=self.pool.id)
        self.assertEqual(
            audit["stats"]["worship_rotation_pools_missing_leadership"], 0
        )

    def test_inactive_role_user_does_not_satisfy_pool_leadership(self):
        self.add_anchor()
        lead = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD, name="负责人", name_en="Lead"
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.pool,
            role_type=lead,
            user=self.user,
            start_date=timezone.localdate(),
        )
        User.objects.filter(pk=self.user.pk).update(is_active=False)

        result = inspect_worship_rotation_pool(self.pool)
        self.assertFalse(result.has_active_leadership)
        audit = run_audit(team_id=self.pool.id)
        self.assertEqual(
            audit["stats"]["worship_rotation_pools_missing_leadership"], 1
        )

    def test_future_and_expired_canonical_roles_do_not_satisfy_readiness(self):
        self.add_anchor()
        lead = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD, name="负责人", name_en="Lead"
        )
        today = timezone.localdate()
        MinistryTeamRoleAssignment.objects.create(
            team=self.pool,
            role_type=lead,
            user=self.user,
            start_date=today - timezone.timedelta(days=20),
            end_date=today - timezone.timedelta(days=10),
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.pool,
            role_type=lead,
            user=self.user,
            start_date=today + timezone.timedelta(days=10),
        )
        self.assertFalse(
            inspect_worship_rotation_pool(self.pool).has_active_leadership
        )

    def test_team_membership_lead_and_can_lead_do_not_satisfy_readiness(self):
        self.add_anchor()
        TeamMembership.objects.create(
            team=self.pool,
            user=self.user,
            role=TeamMembership.ROLE_LEAD,
            can_lead=True,
        )
        self.assertFalse(
            inspect_worship_rotation_pool(self.pool).has_active_leadership
        )

    def test_flag_change_creates_no_rows_or_permissions(self):
        team = MinistryTeam.objects.create(
            name="Container", is_assignable=False
        )
        event = ServiceEvent.objects.create(
            title="Sunday",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=7),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        models = (
            MinistryTeamRoleAssignment,
            TeamMembership,
            TeamAssignment,
            TeamAssignmentMember,
            ServiceEventRequiredTeam,
            ServiceEventAudienceScope,
            ChurchStructureMembership,
            Notification,
        )
        before = {model: model.objects.count() for model in models}
        self.assertFalse(can_manage_ministry_team(self.user, team))
        self.assertFalse(event.can_be_managed_by(self.user))

        team.is_worship_rotation_pool = True
        team.full_clean()
        team.save(update_fields=["is_worship_rotation_pool", "updated_at"])

        self.assertEqual(before, {model: model.objects.count() for model in models})
        event.refresh_from_db()
        self.assertIsNone(event.rotation_anchor_team_id)
        self.assertFalse(can_manage_ministry_team(self.user, team))
        self.assertFalse(event.can_be_managed_by(self.user))

    def test_assignable_child_remains_schedulable_and_pool_role_is_exact_team(self):
        self.add_anchor()
        child = MinistryTeam.objects.create(name="C1", is_assignable=True)
        MinistryTeamParentLink.objects.create(
            child_team=child, parent_team=self.pool, is_primary=True
        )
        lead = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD, name="负责人", name_en="Lead"
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.pool, role_type=lead, user=self.user
        )
        event = ServiceEvent.objects.create(
            title="Sunday",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=7),
            status=ServiceEvent.STATUS_PUBLISHED,
            rotation_anchor_team=child,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=event, unit=self.anchor
        )
        assignment = TeamAssignment.objects.create(
            service_event=event, ministry_team=child
        )
        self.assertEqual(assignment.ministry_team, child)
        self.assertTrue(can_manage_ministry_team(self.user, self.pool))
        self.assertFalse(can_manage_ministry_team(self.user, child))
        self.assertFalse(can_manage_team_assignment_for_team(self.user, child))


class WorshipRotationPoolSetupUITests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="pool_staff", password="pw", is_staff=True
        )
        self.team = MinistryTeam.objects.create(
            name="敬拜事工", name_en="Worship Ministry", is_assignable=False
        )
        self.client.login(username="pool_staff", password="pw")

    @property
    def url(self):
        return reverse("manage_ministry_team_structure", args=[self.team.id])

    def set_language(self, language):
        session = self.client.session
        session["language"] = language
        session.save()

    def test_english_setup_exposes_pool_label_and_non_authority_help(self):
        self.set_language("en")
        response = self.client.get(self.url)
        self.assertContains(response, "Worship Rotation Pool")
        self.assertContains(response, "non-assignable ministry container")
        self.assertContains(response, "does not schedule anyone or grant permission")

    def test_chinese_setup_exposes_pool_label_and_non_authority_help(self):
        self.set_language("zh")
        response = self.client.get(self.url)
        self.assertContains(response, "敬拜轮值团队组")
        self.assertContains(response, "不可排班的事工容器")
        self.assertContains(response, "不会安排任何人，也不会授予权限")

    def test_english_role_copy_explains_exact_team_authority_and_boundaries(self):
        self.set_language("en")
        response = self.client.get(self.url)
        self.assertContains(
            response,
            "grants management authority for this exact team",
        )
        self.assertContains(response, "other long-term roles grant no automatic permission")
        self.assertContains(response, "do not create My Serving items")
        self.assertContains(
            response,
            "grant authority over parent/child teams, events, or Sunday Worship",
        )
        self.assertNotContains(response, "do not currently grant permissions")

    def test_chinese_role_copy_explains_exact_team_authority_and_boundaries(self):
        self.set_language("zh")
        response = self.client.get(self.url)
        self.assertContains(response, "会授予此团队的管理权限")
        self.assertContains(response, "其他长期角色不会自动授予权限")
        self.assertContains(response, "不会自动创建“我的服事”事项")
        self.assertContains(response, "不会授予上级或下级团队、聚会或主日敬拜的权限")
        self.assertNotContains(response, "目前不会自动授予权限")

    def test_staff_can_mark_valid_non_assignable_pool(self):
        response = self.client.post(
            self.url,
            {
                "action": "metadata",
                "team_kind": MinistryTeam.KIND_MINISTRY_AREA,
                "is_worship_rotation_pool": "on",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.team.refresh_from_db()
        self.assertTrue(self.team.is_worship_rotation_pool)
        self.assertFalse(self.team.is_assignable)

    def test_assignable_pool_submission_is_visible_and_preserves_values(self):
        self.set_language("zh")
        response = self.client.post(
            self.url,
            {
                "action": "metadata",
                "team_kind": MinistryTeam.KIND_MINISTRY_AREA,
                "is_assignable": "on",
                "is_worship_rotation_pool": "on",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "敬拜轮值团队组必须设为不可排班")
        self.assertNotContains(response, "A Worship rotation pool must be non-assignable")
        form = response.context["metadata_form"]
        self.assertEqual(form["is_assignable"].value(), True)
        self.assertEqual(form["is_worship_rotation_pool"].value(), True)
        self.team.refresh_from_db()
        self.assertFalse(self.team.is_assignable)
        self.assertFalse(self.team.is_worship_rotation_pool)

    def test_english_assignable_pool_error_is_localized_and_preserves_values(self):
        self.set_language("en")
        response = self.client.post(
            self.url,
            {
                "action": "metadata",
                "team_kind": MinistryTeam.KIND_MINISTRY_AREA,
                "is_assignable": "on",
                "is_worship_rotation_pool": "on",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A Worship rotation pool must be non-assignable")
        self.assertNotContains(response, "敬拜轮值团队组必须设为不可排班")
        form = response.context["metadata_form"]
        self.assertEqual(form["is_assignable"].value(), True)
        self.assertEqual(form["is_worship_rotation_pool"].value(), True)
        self.team.refresh_from_db()
        self.assertFalse(self.team.is_assignable)
        self.assertFalse(self.team.is_worship_rotation_pool)

    def test_existing_assignable_team_gets_one_localized_error_in_each_language(self):
        self.team.is_assignable = True
        self.team.save(update_fields=["is_assignable", "updated_at"])
        self.team.refresh_from_db()
        stored_snapshot = (
            self.team.team_kind,
            self.team.is_assignable,
            self.team.is_worship_rotation_pool,
            self.team.role_profile_id,
            self.team.is_active,
            self.team.updated_at,
        )

        cases = (
            (
                "en",
                "A Worship rotation pool must be non-assignable.",
                "敬拜轮值团队组必须设为不可排班。",
            ),
            (
                "zh",
                "敬拜轮值团队组必须设为不可排班。",
                "A Worship rotation pool must be non-assignable.",
            ),
        )
        for language, expected_error, excluded_error in cases:
            with self.subTest(language=language):
                self.set_language(language)
                response = self.client.post(
                    self.url,
                    {
                        "action": "metadata",
                        "team_kind": MinistryTeam.KIND_MINISTRY_AREA,
                        "is_assignable": "on",
                        "is_worship_rotation_pool": "on",
                        "is_active": "on",
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected_error, count=1)
                self.assertNotContains(response, excluded_error)
                form = response.context["metadata_form"]
                self.assertEqual(form["is_assignable"].value(), True)
                self.assertEqual(form["is_worship_rotation_pool"].value(), True)
                self.team.refresh_from_db()
                self.assertEqual(
                    (
                        self.team.team_kind,
                        self.team.is_assignable,
                        self.team.is_worship_rotation_pool,
                        self.team.role_profile_id,
                        self.team.is_active,
                        self.team.updated_at,
                    ),
                    stored_snapshot,
                )
