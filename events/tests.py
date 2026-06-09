from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
    District,
    MinistryContext,
    SmallGroup,
)
from ministry.models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)

from .forms import RecurringServiceEventForm, ServiceEventForm
from .models import ServiceEvent, ServiceEventAudienceScope, ServiceEventRequiredTeam


class ServiceEventFoundationTests(TestCase):
    def setUp(self):
        self.north = District.objects.create(name="North")
        self.south = District.objects.create(name="South")
        self.cm = MinistryContext.objects.create(
            code="CM",
            name="Chinese Ministry",
            name_en="Chinese Ministry",
        )
        self.em = MinistryContext.objects.create(
            code="EM",
            name="English Ministry",
            name_en="English Ministry",
        )
        self.group = SmallGroup.objects.create(name="Rainbow 4", district=self.north)
        self.same_district_group = SmallGroup.objects.create(
            name="Rainbow 4B",
            district=self.north,
        )
        self.other_group = SmallGroup.objects.create(
            name="Rainbow 5",
            district=self.south,
        )
        self.required_team = MinistryTeam.objects.create(
            name="灯光团队",
            name_en="Lighting Team",
        )
        self.other_required_team = MinistryTeam.objects.create(
            name="音响团队",
            name_en="Sound Team",
        )
        self.inactive_required_team = MinistryTeam.objects.create(
            name="停用团队",
            name_en="Inactive Team",
            is_active=False,
        )

        self.user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="testpass123",
        )
        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.same_district_user = User.objects.create_user(
            username="same_district",
            email="same@example.com",
            password="testpass123",
        )
        self.same_district_user.profile.small_group = self.same_district_group
        self.same_district_user.profile.save()

        self.other_user = User.objects.create_user(
            username="other_group",
            email="other@example.com",
            password="testpass123",
        )
        self.other_user.profile.small_group = self.other_group
        self.other_user.profile.save()

        self.staff = User.objects.create_user(
            username="event_staff",
            email="staff@example.com",
            password="testpass123",
            is_staff=True,
        )

        self.manager = User.objects.create_user(
            username="pastor_event",
            email="pastor@example.com",
            password="testpass123",
        )
        ChurchRoleAssignment.objects.create(
            user=self.manager,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        self.future_time = timezone.now() + timezone.timedelta(days=3)
        self.end_time = self.future_time + timezone.timedelta(hours=2)

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def create_event(self, **overrides):
        data = {
            "title": "主日崇拜",
            "title_en": "Sunday Service",
            "description": "一起敬拜。",
            "description_en": "Worship together.",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": self.future_time,
            "end_datetime": self.end_time,
            "location": "Sanctuary",
            "scope_type": ServiceEvent.SCOPE_GLOBAL,
            "status": ServiceEvent.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return ServiceEvent.objects.create(**data)

    def create_structure_unit(self, code, name, parent=None, is_active=True):
        return ChurchStructureUnit.objects.create(
            parent=parent,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code=code,
            name=name,
            is_active=is_active,
        )

    def event_post_data(self, **overrides):
        data = {
            "title": "特别聚会",
            "title_en": "Special Meeting",
            "description": "中文说明",
            "description_en": "English description",
            "event_type": ServiceEvent.EVENT_SPECIAL_MEETING,
            "start_datetime": self.future_time.strftime("%Y-%m-%dT%H:%M"),
            "end_datetime": self.end_time.strftime("%Y-%m-%dT%H:%M"),
            "location": "Fellowship Hall",
            "meeting_link": "https://example.com/event",
            "ministry_context": "",
            "rotation_anchor_team": "",
            "required_teams": [],
            "scope_type": ServiceEvent.SCOPE_GLOBAL,
            "status": ServiceEvent.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return data

    def create_team_assignment(self, event, status=TeamAssignment.STATUS_SCHEDULED):
        return TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.required_team,
            status=status,
        )

    def create_team_assignment_member(self, assignment):
        membership = TeamMembership.objects.create(
            team=assignment.ministry_team,
            display_name="Levin",
        )
        return TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=membership,
        )

    def next_sunday(self):
        today = timezone.localdate()
        days_until_sunday = (6 - today.weekday()) % 7
        if days_until_sunday == 0:
            days_until_sunday = 7
        return today + timezone.timedelta(days=days_until_sunday)

    def matching_recurring_start_datetime(self, event_date=None):
        event_date = event_date or self.next_sunday()
        return timezone.make_aware(
            timezone.datetime.combine(
                event_date,
                timezone.datetime.strptime("10:00", "%H:%M").time(),
            ),
            timezone.get_current_timezone(),
        )

    def recurring_post_data(self, **overrides):
        start_date = self.next_sunday()
        end_date = start_date + timezone.timedelta(days=14)
        data = {
            "title": "主日崇拜",
            "title_en": "Sunday Service",
            "description": "主日聚会",
            "description_en": "Sunday gathering",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "weekday": "6",
            "start_time": "10:00",
            "end_time": "11:30",
            "location": "Sanctuary",
            "meeting_link": "",
            "rotation_anchor_team": "",
            "required_teams": [],
            "scope_type": ServiceEvent.SCOPE_GLOBAL,
            "district": "",
            "small_group": "",
            "status": ServiceEvent.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return data

    def test_event_list_requires_login(self):
        response = self.client.get(reverse("service_event_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_published_global_event_visible_to_regular_user(self):
        self.set_language("en")
        event = self.create_event()

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("service_event_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, event.title_en)

    def test_draft_event_hidden_from_regular_user(self):
        self.set_language("en")
        self.create_event(title_en="Draft Event", status=ServiceEvent.STATUS_DRAFT)

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("service_event_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Draft Event")

    def test_cancelled_event_hidden_from_regular_user(self):
        self.set_language("en")
        event = self.create_event(
            title_en="Cancelled Event",
            status=ServiceEvent.STATUS_CANCELLED,
        )

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("service_event_list"))

    def test_draft_event_visible_to_staff(self):
        self.set_language("en")
        self.create_event(title_en="Draft Event", status=ServiceEvent.STATUS_DRAFT)

        self.client.login(username="event_staff", password="testpass123")
        response = self.client.get(reverse("service_event_list"), {"tab": "drafts"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Draft Event")

    def test_district_scoped_event_visible_to_matching_district_user(self):
        self.set_language("en")
        event = self.create_event(
            title_en="North Event",
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=self.north,
        )

        self.client.login(username="same_district", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "North Event")

    def test_district_scoped_event_hidden_from_outside_district_user(self):
        self.set_language("en")
        event = self.create_event(
            title_en="North Event",
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=self.north,
        )

        self.client.login(username="other_group", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("service_event_list"))

    def test_small_group_scoped_event_visible_to_same_group_user(self):
        self.set_language("en")
        event = self.create_event(
            title_en="Group Event",
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Group Event")

    def test_small_group_scoped_event_hidden_from_different_group_user(self):
        self.set_language("en")
        event = self.create_event(
            title_en="Group Event",
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )

        self.client.login(username="other_group", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("service_event_list"))

    def test_user_without_capability_cannot_access_create_page(self):
        self.set_language("en")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("create_service_event"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("service_event_list"))

    def test_user_with_pastor_role_can_access_create_page(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.get(reverse("create_service_event"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New Service Event")

    def test_manager_can_create_published_event(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(),
        )

        self.assertEqual(response.status_code, 302)
        event = ServiceEvent.objects.get(title="特别聚会")
        self.assertEqual(event.created_by, self.manager)
        self.assertEqual(event.status, ServiceEvent.STATUS_PUBLISHED)
        self.assertIsNotNone(event.published_at)

    def test_manager_can_create_draft_event(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(status=ServiceEvent.STATUS_DRAFT),
        )

        self.assertEqual(response.status_code, 302)
        event = ServiceEvent.objects.get(title="特别聚会")
        self.assertEqual(event.status, ServiceEvent.STATUS_DRAFT)
        self.assertIsNone(event.published_at)

    def test_existing_event_can_have_no_required_teams(self):
        event = self.create_event()

        self.assertEqual(event.required_teams.count(), 0)
        event.full_clean()

    def test_service_event_can_have_blank_rotation_anchor(self):
        event = self.create_event()

        self.assertIsNone(event.rotation_anchor_team)
        event.full_clean()

    def test_service_event_can_save_rotation_anchor_team_without_side_effects(self):
        event = self.create_event(rotation_anchor_team=self.required_team)

        self.assertEqual(event.rotation_anchor_team, self.required_team)
        self.assertEqual(event.required_teams.count(), 0)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)

    def test_rotation_anchor_team_protects_referenced_team_from_delete(self):
        self.create_event(rotation_anchor_team=self.required_team)

        with self.assertRaises(ProtectedError):
            self.required_team.delete()

    def test_required_team_relationship_rejects_duplicate_team_for_event(self):
        event = self.create_event()
        ServiceEventRequiredTeam.objects.create(
            service_event=event,
            ministry_team=self.required_team,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ServiceEventRequiredTeam.objects.create(
                    service_event=event,
                    ministry_team=self.required_team,
                )

    def test_required_team_protects_referenced_team_from_delete(self):
        event = self.create_event()
        event.required_teams.add(self.required_team)

        with self.assertRaises(ProtectedError):
            self.required_team.delete()

    def test_deleting_event_removes_required_team_links(self):
        event = self.create_event()
        event.required_teams.add(self.required_team)

        event.delete()

        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)
        self.assertTrue(MinistryTeam.objects.filter(id=self.required_team.id).exists())

    def test_service_event_audience_scope_can_store_selected_unit(self):
        event = self.create_event()
        unit = self.create_structure_unit("CM", "Chinese Ministry")

        scope = ServiceEventAudienceScope.objects.create(
            service_event=event,
            unit=unit,
        )

        self.assertEqual(scope.service_event, event)
        self.assertEqual(scope.unit, unit)
        self.assertEqual(list(event.get_audience_scope_units()), [unit])

    def test_service_event_audience_scope_rejects_duplicate_unit(self):
        event = self.create_event()
        unit = self.create_structure_unit("CM", "Chinese Ministry")
        ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)

        with self.assertRaises(ValidationError):
            ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)

    def test_deleting_event_removes_audience_scope_rows(self):
        event = self.create_event()
        unit = self.create_structure_unit("CM", "Chinese Ministry")
        ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)

        event.delete()

        self.assertEqual(ServiceEventAudienceScope.objects.count(), 0)
        self.assertTrue(ChurchStructureUnit.objects.filter(id=unit.id).exists())

    def test_audience_scope_protects_referenced_unit_from_delete(self):
        event = self.create_event()
        unit = self.create_structure_unit("CM", "Chinese Ministry")
        ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)

        with self.assertRaises(ProtectedError):
            unit.delete()

    def test_existing_event_can_have_no_audience_scope(self):
        event = self.create_event()

        self.assertEqual(event.audience_scope_links.count(), 0)
        self.assertEqual(list(event.get_audience_scope_units()), [])
        event.full_clean()

    def test_audience_scope_rejects_inactive_unit(self):
        event = self.create_event()
        inactive_unit = self.create_structure_unit(
            "INACTIVE",
            "Inactive Unit",
            is_active=False,
        )

        with self.assertRaises(ValidationError):
            ServiceEventAudienceScope.objects.create(
                service_event=event,
                unit=inactive_unit,
            )

    def test_audience_scope_rows_do_not_change_legacy_visibility(self):
        event = self.create_event(
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=self.north,
        )
        unit = self.create_structure_unit("CM", "Chinese Ministry")
        ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)

        self.assertTrue(event.can_be_seen_by(self.same_district_user))
        self.assertFalse(event.can_be_seen_by(self.other_user))

    def test_requested_membership_does_not_grant_event_visibility(self):
        event = self.create_event(
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=self.north,
        )
        unit = self.create_structure_unit("CM", "Chinese Ministry")
        ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)
        ChurchStructureMembership.objects.create(
            user=self.other_user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=True,
        )

        self.assertFalse(event.can_be_seen_by(self.other_user))

    def test_audience_scope_rows_do_not_change_ministry_scheduling_data(self):
        event = self.create_event(rotation_anchor_team=self.required_team)
        event.required_teams.add(self.required_team)
        unit = self.create_structure_unit("CM", "Chinese Ministry")

        ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)
        event.refresh_from_db()

        self.assertEqual(event.rotation_anchor_team, self.required_team)
        self.assertEqual(list(event.required_teams.all()), [self.required_team])
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)

    def test_audience_scope_rejects_parent_then_descendant_selection(self):
        event = self.create_event()
        parent = self.create_structure_unit("CM", "Chinese Ministry")
        child = self.create_structure_unit("CM-D1", "District 1", parent=parent)
        ServiceEventAudienceScope.objects.create(service_event=event, unit=parent)

        with self.assertRaises(ValidationError):
            ServiceEventAudienceScope.objects.create(service_event=event, unit=child)

    def test_audience_scope_rejects_descendant_then_parent_selection(self):
        event = self.create_event()
        parent = self.create_structure_unit("CM", "Chinese Ministry")
        child = self.create_structure_unit("CM-D1", "District 1", parent=parent)
        ServiceEventAudienceScope.objects.create(service_event=event, unit=child)

        with self.assertRaises(ValidationError):
            ServiceEventAudienceScope.objects.create(service_event=event, unit=parent)

    def test_audience_scope_allows_sibling_units(self):
        event = self.create_event()
        parent = self.create_structure_unit("CM", "Chinese Ministry")
        first_child = self.create_structure_unit("CM-D1", "District 1", parent=parent)
        second_child = self.create_structure_unit("CM-D2", "District 2", parent=parent)

        ServiceEventAudienceScope.objects.create(service_event=event, unit=first_child)
        ServiceEventAudienceScope.objects.create(service_event=event, unit=second_child)

        self.assertEqual(
            set(event.get_audience_scope_units()),
            {first_child, second_child},
        )

    def test_service_event_form_shows_active_teams_only_for_new_event(self):
        form = ServiceEventForm(language="en")
        team_ids = set(form.fields["required_teams"].queryset.values_list("id", flat=True))

        self.assertIn(self.required_team.id, team_ids)
        self.assertIn(self.other_required_team.id, team_ids)
        self.assertNotIn(self.inactive_required_team.id, team_ids)

    def test_service_event_edit_form_keeps_selected_inactive_team_visible(self):
        event = self.create_event()
        event.required_teams.add(self.inactive_required_team)

        form = ServiceEventForm(instance=event, language="en")
        team_ids = set(form.fields["required_teams"].queryset.values_list("id", flat=True))

        self.assertIn(self.inactive_required_team.id, team_ids)

    def test_service_event_form_shows_active_rotation_anchors_only_for_new_event(self):
        form = ServiceEventForm(language="en")
        team_ids = set(
            form.fields["rotation_anchor_team"].queryset.values_list("id", flat=True)
        )

        self.assertIn(self.required_team.id, team_ids)
        self.assertIn(self.other_required_team.id, team_ids)
        self.assertNotIn(self.inactive_required_team.id, team_ids)

    def test_service_event_edit_form_keeps_selected_inactive_rotation_anchor_visible(self):
        event = self.create_event(rotation_anchor_team=self.inactive_required_team)

        form = ServiceEventForm(instance=event, language="en")
        team_ids = set(
            form.fields["rotation_anchor_team"].queryset.values_list("id", flat=True)
        )

        self.assertIn(self.inactive_required_team.id, team_ids)

    def test_service_event_form_hides_cancelled_status_for_active_event(self):
        event = self.create_event(status=ServiceEvent.STATUS_PUBLISHED)

        form = ServiceEventForm(instance=event, language="en")

        status_values = [value for value, _label in form.fields["status"].choices]
        self.assertNotIn(ServiceEvent.STATUS_CANCELLED, status_values)

    def test_service_event_form_shows_only_cancelled_status_for_cancelled_event(self):
        event = self.create_event(status=ServiceEvent.STATUS_CANCELLED)

        form = ServiceEventForm(instance=event, language="en")

        status_values = [value for value, _label in form.fields["status"].choices]
        self.assertEqual(status_values, [ServiceEvent.STATUS_CANCELLED])

    def test_manager_can_create_event_with_required_teams_without_assignments(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(
                required_teams=[
                    self.required_team.id,
                    self.other_required_team.id,
                ],
            ),
        )

        self.assertEqual(response.status_code, 302)
        event = ServiceEvent.objects.get(title="特别聚会")
        self.assertEqual(
            set(event.required_teams.values_list("id", flat=True)),
            {self.required_team.id, self.other_required_team.id},
        )
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)

    def test_manager_can_create_event_with_rotation_anchor_without_assignments(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(rotation_anchor_team=self.required_team.id),
        )

        self.assertEqual(response.status_code, 302)
        event = ServiceEvent.objects.get(title="特别聚会")
        self.assertEqual(event.rotation_anchor_team, self.required_team)
        self.assertEqual(event.required_teams.count(), 0)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)

    def test_manager_can_edit_event(self):
        self.set_language("en")
        event = self.create_event(status=ServiceEvent.STATUS_DRAFT)
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("edit_service_event", args=[event.id]),
            self.event_post_data(
                title="更新后的聚会",
                title_en="Updated Event",
                status=ServiceEvent.STATUS_PUBLISHED,
            ),
        )

        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.title, "更新后的聚会")
        self.assertEqual(event.title_en, "Updated Event")
        self.assertIsNotNone(event.published_at)

    def test_manager_edit_replaces_required_teams(self):
        self.set_language("en")
        event = self.create_event(status=ServiceEvent.STATUS_DRAFT)
        event.required_teams.add(self.required_team)
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("edit_service_event", args=[event.id]),
            self.event_post_data(
                title="更新后的聚会",
                title_en="Updated Event",
                required_teams=[self.other_required_team.id],
            ),
        )

        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(
            set(event.required_teams.values_list("id", flat=True)),
            {self.other_required_team.id},
        )
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)

    def test_manager_cannot_cancel_event_through_edit_form_post(self):
        self.set_language("en")
        event = self.create_event(status=ServiceEvent.STATUS_PUBLISHED)
        assignment = self.create_team_assignment(
            event,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("edit_service_event", args=[event.id]),
            self.event_post_data(status=ServiceEvent.STATUS_CANCELLED),
        )

        self.assertEqual(response.status_code, 200)
        event.refresh_from_db()
        assignment.refresh_from_db()
        self.assertEqual(event.status, ServiceEvent.STATUS_PUBLISHED)
        self.assertEqual(assignment.status, TeamAssignment.STATUS_SCHEDULED)

    def test_manager_cannot_reactivate_cancelled_event_through_edit_form_post(self):
        self.set_language("en")
        for status in [
            ServiceEvent.STATUS_DRAFT,
            ServiceEvent.STATUS_PUBLISHED,
            ServiceEvent.STATUS_COMPLETED,
        ]:
            with self.subTest(status=status):
                event = self.create_event(
                    title=f"Cancelled {status}",
                    title_en=f"Cancelled {status}",
                    status=ServiceEvent.STATUS_CANCELLED,
                )
                assignment = self.create_team_assignment(
                    event,
                    status=TeamAssignment.STATUS_CANCELLED,
                )
                self.client.login(username="pastor_event", password="testpass123")

                response = self.client.post(
                    reverse("edit_service_event", args=[event.id]),
                    self.event_post_data(status=status),
                )

                self.assertEqual(response.status_code, 200)
                event.refresh_from_db()
                assignment.refresh_from_db()
                self.assertEqual(event.status, ServiceEvent.STATUS_CANCELLED)
                self.assertEqual(assignment.status, TeamAssignment.STATUS_CANCELLED)

    def test_manager_edit_replaces_and_clears_rotation_anchor(self):
        self.set_language("en")
        event = self.create_event(
            status=ServiceEvent.STATUS_DRAFT,
            rotation_anchor_team=self.required_team,
        )
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("edit_service_event", args=[event.id]),
            self.event_post_data(
                title="更新后的聚会",
                title_en="Updated Event",
                rotation_anchor_team=self.other_required_team.id,
            ),
        )

        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.rotation_anchor_team, self.other_required_team)

        response = self.client.post(
            reverse("edit_service_event", args=[event.id]),
            self.event_post_data(
                title="再次更新",
                title_en="Updated Again",
                rotation_anchor_team="",
            ),
        )

        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertIsNone(event.rotation_anchor_team)

    def test_manager_can_remove_selected_inactive_required_team_on_edit(self):
        self.set_language("en")
        event = self.create_event(status=ServiceEvent.STATUS_DRAFT)
        event.required_teams.add(self.inactive_required_team)
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("edit_service_event", args=[event.id]),
            self.event_post_data(
                title="更新后的聚会",
                title_en="Updated Event",
                required_teams=[],
            ),
        )

        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.required_teams.count(), 0)

    def test_manager_can_cancel_event(self):
        self.set_language("en")
        event = self.create_event(title_en="Cancel Me")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(reverse("cancel_service_event", args=[event.id]))

        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.status, ServiceEvent.STATUS_CANCELLED)

    def test_cancel_event_cancels_scheduled_team_assignment(self):
        self.set_language("en")
        event = self.create_event(title_en="Cancel Assignment")
        assignment = self.create_team_assignment(
            event,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.client.login(username="pastor_event", password="testpass123")

        self.client.post(reverse("cancel_service_event", args=[event.id]))

        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CANCELLED)

    def test_cancel_event_cancels_prepared_team_assignment(self):
        self.set_language("en")
        event = self.create_event(title_en="Cancel Assignment")
        assignment = self.create_team_assignment(
            event,
            status=TeamAssignment.STATUS_PREPARED,
        )
        self.client.login(username="pastor_event", password="testpass123")

        self.client.post(reverse("cancel_service_event", args=[event.id]))

        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CANCELLED)

    def test_cancel_event_cancels_confirmed_team_assignment(self):
        self.set_language("en")
        event = self.create_event(title_en="Cancel Assignment")
        assignment = self.create_team_assignment(
            event,
            status=TeamAssignment.STATUS_CONFIRMED,
        )
        self.client.login(username="pastor_event", password="testpass123")

        self.client.post(reverse("cancel_service_event", args=[event.id]))

        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CANCELLED)

    def test_cancel_event_leaves_completed_team_assignment_unchanged(self):
        self.set_language("en")
        event = self.create_event(title_en="Cancel Assignment")
        assignment = self.create_team_assignment(
            event,
            status=TeamAssignment.STATUS_COMPLETED,
        )
        self.client.login(username="pastor_event", password="testpass123")

        self.client.post(reverse("cancel_service_event", args=[event.id]))

        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_COMPLETED)

    def test_cancel_event_leaves_already_cancelled_team_assignment_unchanged(self):
        self.set_language("en")
        event = self.create_event(title_en="Cancel Assignment")
        assignment = self.create_team_assignment(
            event,
            status=TeamAssignment.STATUS_CANCELLED,
        )
        self.client.login(username="pastor_event", password="testpass123")

        self.client.post(reverse("cancel_service_event", args=[event.id]))

        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CANCELLED)

    def test_cancel_event_keeps_assignment_members_attached(self):
        self.set_language("en")
        event = self.create_event(title_en="Cancel Assignment")
        assignment = self.create_team_assignment(event)
        assignment_member = self.create_team_assignment_member(assignment)
        self.client.login(username="pastor_event", password="testpass123")

        self.client.post(reverse("cancel_service_event", args=[event.id]))

        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CANCELLED)
        self.assertTrue(
            TeamAssignmentMember.objects.filter(id=assignment_member.id).exists()
        )
        self.assertEqual(assignment.assignment_members.count(), 1)

    def test_cancel_event_rolls_back_status_when_assignment_cancellation_fails(self):
        self.set_language("en")
        event = self.create_event(title_en="Cancel Assignment")
        original_status = event.status
        self.create_team_assignment(event)
        self.client.login(username="pastor_event", password="testpass123")

        with patch(
            "events.views.cancel_non_final_assignments_for_event",
            side_effect=RuntimeError("assignment cancellation failed"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("cancel_service_event", args=[event.id]))

        event.refresh_from_db()
        self.assertEqual(event.status, original_status)

    def test_cancelled_event_hidden_from_regular_users_after_cancellation(self):
        self.set_language("en")
        event = self.create_event(title_en="Cancel Me")
        self.client.login(username="pastor_event", password="testpass123")
        self.client.post(reverse("cancel_service_event", args=[event.id]))
        self.client.logout()

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("service_event_list"))

    def test_scope_validation(self):
        global_event = ServiceEvent(
            title="Invalid Global",
            event_type=ServiceEvent.EVENT_OTHER,
            start_datetime=self.future_time,
            scope_type=ServiceEvent.SCOPE_GLOBAL,
            district=self.north,
        )
        district_event = ServiceEvent(
            title="Invalid District",
            event_type=ServiceEvent.EVENT_OTHER,
            start_datetime=self.future_time,
            scope_type=ServiceEvent.SCOPE_DISTRICT,
        )
        group_event = ServiceEvent(
            title="Invalid Group",
            event_type=ServiceEvent.EVENT_OTHER,
            start_datetime=self.future_time,
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
        )

        with self.assertRaises(ValidationError):
            global_event.full_clean()
        with self.assertRaises(ValidationError):
            district_event.full_clean()
        with self.assertRaises(ValidationError):
            group_event.full_clean()

    def test_end_datetime_before_start_datetime_is_invalid(self):
        event = ServiceEvent(
            title="Invalid Time",
            event_type=ServiceEvent.EVENT_OTHER,
            start_datetime=self.future_time,
            end_datetime=self.future_time - timezone.timedelta(hours=1),
            scope_type=ServiceEvent.SCOPE_GLOBAL,
        )

        with self.assertRaises(ValidationError):
            event.full_clean()

    def test_ministry_context_label_is_optional(self):
        event = self.create_event()

        self.assertIsNone(event.ministry_context)

    def test_service_event_form_clarifies_ministry_context_is_label_only(self):
        english_form = ServiceEventForm(language="en")
        chinese_form = ServiceEventForm(language="zh")

        self.assertEqual(
            english_form.fields["ministry_context"].label,
            "Host / Language Label",
        )
        self.assertIn(
            "label-only",
            english_form.fields["ministry_context"].help_text,
        )
        self.assertIn(
            "does not control visibility, serving assignment, or permissions",
            english_form.fields["ministry_context"].help_text,
        )
        self.assertEqual(
            chinese_form.fields["ministry_context"].label,
            "主办/语言标签（可选）",
        )
        self.assertNotEqual(
            chinese_form.fields["ministry_context"].label,
            "事工范围",
        )
        self.assertIn(
            "不会控制可见范围、服事分配或用户权限",
            chinese_form.fields["ministry_context"].help_text,
        )

    def test_service_event_form_clarifies_rotation_anchor_is_scheduling_hint_only(self):
        english_form = ServiceEventForm(language="en")
        chinese_form = ServiceEventForm(language="zh")

        self.assertEqual(
            english_form.fields["rotation_anchor_team"].label,
            "Rotation Anchor Team",
        )
        self.assertIn(
            "future copy-forward suggestions",
            english_form.fields["rotation_anchor_team"].help_text,
        )
        self.assertIn(
            "does not make the team required",
            english_form.fields["rotation_anchor_team"].help_text,
        )
        self.assertIn(
            "does not control coverage, audience, visibility, or permissions",
            english_form.fields["rotation_anchor_team"].help_text,
        )
        self.assertEqual(
            chinese_form.fields["rotation_anchor_team"].label,
            "配搭参考团队",
        )
        self.assertIn(
            "不会控制服事覆盖、覆盖对象、可见范围或用户权限",
            chinese_form.fields["rotation_anchor_team"].help_text,
        )

    def test_service_event_scope_form_labels_are_audience_specific(self):
        english_form = ServiceEventForm(language="en")
        chinese_form = ServiceEventForm(language="zh")

        self.assertEqual(english_form.fields["scope_type"].label, "Audience Scope")
        self.assertEqual(chinese_form.fields["scope_type"].label, "覆盖对象")
        self.assertEqual(chinese_form.fields["district"].label, "适用区")
        self.assertEqual(chinese_form.fields["small_group"].label, "适用小组")
        self.assertIn(
            "does not expand into child small-group selection",
            english_form.fields["scope_type"].help_text,
        )
        self.assertIn(
            "Multi-level and multi-select audience selection belongs to future",
            english_form.fields["scope_type"].help_text,
        )
        self.assertIn(
            "不会继续展开下属小组",
            chinese_form.fields["scope_type"].help_text,
        )

    def test_ministry_context_label_can_be_saved_without_changing_visibility(self):
        self.set_language("en")
        event = self.create_event(
            title_en="CM Sunday Service",
            ministry_context=self.cm,
        )

        self.client.login(username="other_group", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CM - Chinese Ministry")

    def test_manager_can_create_event_with_ministry_context_label(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(ministry_context=self.em.id),
        )

        self.assertEqual(response.status_code, 302)
        event = ServiceEvent.objects.get(title_en="Special Meeting")
        self.assertEqual(event.ministry_context, self.em)

    def test_manager_can_create_event_with_existing_district_scope(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(
                scope_type=ServiceEvent.SCOPE_DISTRICT,
                district=self.north.id,
                small_group="",
            ),
        )

        self.assertEqual(response.status_code, 302)
        event = ServiceEvent.objects.get(title_en="Special Meeting")
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_DISTRICT)
        self.assertEqual(event.district, self.north)

    def test_manager_can_create_event_with_existing_small_group_scope(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(
                scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
                district="",
                small_group=self.group.id,
            ),
        )

        self.assertEqual(response.status_code, 302)
        event = ServiceEvent.objects.get(title_en="Special Meeting")
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_SMALL_GROUP)
        self.assertEqual(event.small_group, self.group)

    def test_chinese_list_and_detail_pages_show_chinese_labels(self):
        self.set_language("zh")
        event = self.create_event()

        self.client.login(username="regular", password="testpass123")
        list_response = self.client.get(reverse("service_event_list"))
        detail_response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertContains(list_response, "聚会事件")
        self.assertContains(list_response, "聚会类型")
        self.assertContains(detail_response, "开始时间")
        self.assertContains(detail_response, "范围")

    def test_english_list_and_detail_pages_show_english_labels(self):
        self.set_language("en")
        event = self.create_event()

        self.client.login(username="regular", password="testpass123")
        list_response = self.client.get(reverse("service_event_list"))
        detail_response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertContains(list_response, "Service Events")
        self.assertContains(list_response, "Event Type")
        self.assertContains(detail_response, "Start Time")
        self.assertContains(detail_response, "Scope")

    def test_detail_page_shows_required_teams_as_plain_metadata_only(self):
        self.set_language("en")
        event = self.create_event()
        event.required_teams.add(self.required_team)

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Required Ministry Teams")
        self.assertContains(response, "Lighting Team")
        self.assertNotContains(response, "Missing")
        self.assertNotContains(response, "Unassigned")
        self.assertNotContains(response, "Coverage")

    def test_ordinary_event_viewer_does_not_see_rotation_anchor_metadata(self):
        self.set_language("en")
        event = self.create_event(rotation_anchor_team=self.required_team)

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Rotation Anchor Team")
        self.assertNotContains(response, "Lighting Team")
        self.assertNotContains(response, "Missing")
        self.assertNotContains(response, "Unassigned")
        self.assertNotContains(response, "Coverage")

    def test_staff_event_viewer_sees_rotation_anchor_metadata(self):
        self.set_language("en")
        event = self.create_event(rotation_anchor_team=self.required_team)

        self.client.login(username="event_staff", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rotation Anchor Team")
        self.assertContains(response, "Lighting Team")

    def test_team_assignment_manager_sees_rotation_anchor_metadata(self):
        self.set_language("en")
        event = self.create_event(rotation_anchor_team=self.required_team)
        ChurchRoleAssignment.objects.create(
            user=self.other_user,
            role=ChurchRoleAssignment.ROLE_COWORKER,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        self.client.login(username="other_group", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rotation Anchor Team")
        self.assertContains(response, "Lighting Team")

    def test_regular_event_viewer_does_not_see_coworker_coverage(self):
        self.set_language("en")
        event = self.create_event()
        event.required_teams.add(self.required_team)
        membership = TeamMembership.objects.create(
            team=self.required_team,
            display_name="Levin",
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.required_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=membership,
        )

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Required Ministry Teams")
        self.assertNotContains(response, "Assignment Coverage")
        self.assertNotContains(response, "Assigned 1 person")
        self.assertNotContains(response, "Levin")

    def test_staff_event_viewer_sees_full_assignment_coverage(self):
        self.set_language("en")
        event = self.create_event()
        event.required_teams.add(self.required_team, self.other_required_team)
        membership = TeamMembership.objects.create(
            team=self.required_team,
            display_name="Levin",
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.required_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=membership,
        )

        self.client.login(username="event_staff", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assignment Coverage")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Assigned 1 person")
        self.assertContains(response, "Levin")
        self.assertContains(response, "Sound Team")
        self.assertContains(response, "Unassigned")

    def test_manager_can_open_recurring_event_creator(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.get(reverse("create_recurring_service_events"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Recurring Events")

    def test_recurring_sunday_service_defaults_to_bilingual_titles(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.get(reverse("create_recurring_service_events"))

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.fields["title"].initial, "主日崇拜")
        self.assertEqual(form.fields["title_en"].initial, "Sunday Service")
        self.assertEqual(
            form.fields["event_type"].initial,
            ServiceEvent.EVENT_SUNDAY_SERVICE,
        )

    def test_regular_user_cannot_open_recurring_event_creator(self):
        self.set_language("en")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("create_recurring_service_events"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("service_event_list"))

    def test_regular_user_cannot_create_event_with_required_teams(self):
        self.set_language("en")
        self.client.login(username="regular", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(required_teams=[self.required_team.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ServiceEvent.objects.filter(title="特别聚会").exists())
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)

    def test_recurring_preview_creates_no_service_event(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                preview="1",
                required_teams=[self.required_team.id],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Events to Create")
        self.assertEqual(ServiceEvent.objects.count(), 0)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)

    def test_recurring_create_creates_weekly_sunday_events_in_range(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(create="1"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ServiceEvent.objects.filter(title_en="Sunday Service").count(), 3)

    def test_recurring_create_applies_same_required_teams_to_each_event(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                create="1",
                required_teams=[
                    self.required_team.id,
                    self.other_required_team.id,
                ],
            ),
        )

        self.assertEqual(response.status_code, 200)
        events = ServiceEvent.objects.filter(title_en="Sunday Service")
        self.assertEqual(events.count(), 3)
        for event in events:
            self.assertEqual(
                set(event.required_teams.values_list("id", flat=True)),
                {self.required_team.id, self.other_required_team.id},
            )
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)

    def test_recurring_create_applies_same_rotation_anchor_to_each_event(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                create="1",
                rotation_anchor_team=self.required_team.id,
            ),
        )

        self.assertEqual(response.status_code, 200)
        events = ServiceEvent.objects.filter(title_en="Sunday Service")
        self.assertEqual(events.count(), 3)
        for event in events:
            self.assertEqual(event.rotation_anchor_team, self.required_team)
            self.assertEqual(event.required_teams.count(), 0)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)

    def test_recurring_create_skips_existing_events(self):
        self.set_language("en")
        start_date = self.next_sunday()
        start_datetime = self.matching_recurring_start_datetime(start_date)
        existing_event = self.create_event(
            title="主日崇拜",
            title_en="Sunday Service",
            start_datetime=start_datetime,
            end_datetime=start_datetime + timezone.timedelta(hours=1, minutes=30),
        )
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                create="1",
                required_teams=[self.required_team.id],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ServiceEvent.objects.filter(title_en="Sunday Service").count(), 3)
        self.assertContains(response, "skipped: 1")
        self.assertEqual(existing_event.required_teams.count(), 0)
        existing_event.refresh_from_db()
        self.assertIsNone(existing_event.rotation_anchor_team)

    def test_recurring_create_ignores_matching_cancelled_event(self):
        self.set_language("en")
        start_date = self.next_sunday()
        start_datetime = self.matching_recurring_start_datetime(start_date)
        cancelled_event = self.create_event(
            title="主日崇拜",
            title_en="Sunday Service",
            start_datetime=start_datetime,
            end_datetime=start_datetime + timezone.timedelta(hours=1, minutes=30),
            status=ServiceEvent.STATUS_CANCELLED,
        )
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                create="1",
                required_teams=[self.required_team.id],
                rotation_anchor_team=self.other_required_team.id,
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "skipped: 0")
        self.assertEqual(ServiceEvent.objects.filter(title_en="Sunday Service").count(), 4)
        replacement_event = (
            ServiceEvent.objects.filter(start_datetime=start_datetime)
            .exclude(id=cancelled_event.id)
            .get()
        )
        self.assertEqual(replacement_event.status, ServiceEvent.STATUS_PUBLISHED)
        self.assertEqual(replacement_event.rotation_anchor_team, self.other_required_team)
        self.assertEqual(
            set(replacement_event.required_teams.values_list("id", flat=True)),
            {self.required_team.id},
        )
        cancelled_event.refresh_from_db()
        self.assertEqual(cancelled_event.status, ServiceEvent.STATUS_CANCELLED)
        self.assertEqual(cancelled_event.required_teams.count(), 0)
        self.assertIsNone(cancelled_event.rotation_anchor_team)

    def test_recurring_create_skips_draft_published_and_completed_events(self):
        self.set_language("en")
        start_date = self.next_sunday()
        existing_events = []
        for offset_weeks, status in enumerate(
            [
                ServiceEvent.STATUS_DRAFT,
                ServiceEvent.STATUS_PUBLISHED,
                ServiceEvent.STATUS_COMPLETED,
            ]
        ):
            event_date = start_date + timezone.timedelta(days=7 * offset_weeks)
            start_datetime = self.matching_recurring_start_datetime(event_date)
            existing_events.append(
                self.create_event(
                    title="主日崇拜",
                    title_en="Sunday Service",
                    start_datetime=start_datetime,
                    end_datetime=start_datetime
                    + timezone.timedelta(hours=1, minutes=30),
                    status=status,
                )
            )
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                create="1",
                required_teams=[self.required_team.id],
                rotation_anchor_team=self.other_required_team.id,
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "skipped: 3")
        self.assertEqual(ServiceEvent.objects.filter(title_en="Sunday Service").count(), 3)
        for existing_event in existing_events:
            existing_event.refresh_from_db()
            self.assertEqual(existing_event.required_teams.count(), 0)
            self.assertIsNone(existing_event.rotation_anchor_team)

    def test_recurring_range_longer_than_eighteen_months_rejected(self):
        self.set_language("en")
        start_date = self.next_sunday()
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                start_date=start_date.isoformat(),
                end_date=(start_date + timezone.timedelta(days=549)).isoformat(),
                preview="1",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Date range cannot be longer than 18 months.")
        self.assertEqual(ServiceEvent.objects.count(), 0)

    def test_chinese_recurring_event_page_shows_chinese_labels(self):
        self.set_language("zh")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.get(reverse("create_recurring_service_events"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "批量创建固定聚会")
        self.assertContains(response, "预览")
        self.assertContains(response, "创建聚会事件")

    def test_english_recurring_event_page_shows_english_labels(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.get(reverse("create_recurring_service_events"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Recurring Events")
        self.assertContains(response, "Preview")
        self.assertContains(response, "Create Events")

    def test_recurring_form_includes_optional_ministry_context_label(self):
        english_form = RecurringServiceEventForm(language="en")
        chinese_form = RecurringServiceEventForm(language="zh")

        self.assertIn("ministry_context", english_form.fields)
        self.assertFalse(english_form.fields["ministry_context"].required)
        self.assertEqual(
            english_form.fields["ministry_context"].label,
            "Host / Language Label",
        )
        self.assertFalse(chinese_form.fields["ministry_context"].required)
        self.assertEqual(
            chinese_form.fields["ministry_context"].label,
            "主办/语言标签（可选）",
        )

    def test_recurring_create_applies_same_ministry_context_to_each_event(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                create="1",
                ministry_context=self.em.id,
            ),
        )

        self.assertEqual(response.status_code, 200)
        events = ServiceEvent.objects.filter(title_en="Sunday Service")
        self.assertEqual(events.count(), 3)
        for event in events:
            self.assertEqual(event.ministry_context, self.em)

    def test_recurring_create_with_blank_ministry_context_keeps_events_blank(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(create="1", ministry_context=""),
        )

        self.assertEqual(response.status_code, 200)
        events = ServiceEvent.objects.filter(title_en="Sunday Service")
        self.assertEqual(events.count(), 3)
        for event in events:
            self.assertIsNone(event.ministry_context)

    def test_recurring_create_required_teams_unchanged_with_ministry_context(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                create="1",
                ministry_context=self.em.id,
                required_teams=[
                    self.required_team.id,
                    self.other_required_team.id,
                ],
            ),
        )

        self.assertEqual(response.status_code, 200)
        events = ServiceEvent.objects.filter(title_en="Sunday Service")
        self.assertEqual(events.count(), 3)
        for event in events:
            self.assertEqual(event.ministry_context, self.em)
            self.assertEqual(
                set(event.required_teams.values_list("id", flat=True)),
                {self.required_team.id, self.other_required_team.id},
            )
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
