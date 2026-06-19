import re
from datetime import datetime, timezone as datetime_timezone
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
from reading.templatetags.datetime_extras import member_datetime

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
        # Structure units used by the normal ServiceEvent audience picker.
        self.root_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        self.north_unit = ChurchStructureUnit.objects.create(
            parent=self.root_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="NORTH",
            name="North District",
        )
        self.south_unit = ChurchStructureUnit.objects.create(
            parent=self.root_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="SOUTH",
            name="South District",
        )
        self.north.church_structure_unit = self.north_unit
        self.north.save(update_fields=["church_structure_unit"])
        self.south.church_structure_unit = self.south_unit
        self.south.save(update_fields=["church_structure_unit"])

        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4",
            name="Rainbow 4",
        )
        self.group_b_unit = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4B",
            name="Rainbow 4B",
        )
        self.other_group_unit = ChurchStructureUnit.objects.create(
            parent=self.south_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R5",
            name="Rainbow 5",
        )
        self.group = SmallGroup.objects.create(
            name="Rainbow 4",
            district=self.north,
            church_structure_unit=self.group_unit,
        )
        self.same_district_group = SmallGroup.objects.create(
            name="Rainbow 4B",
            district=self.north,
            church_structure_unit=self.group_b_unit,
        )
        self.other_group = SmallGroup.objects.create(
            name="Rainbow 5",
            district=self.south,
            church_structure_unit=self.other_group_unit,
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

    def add_audience(self, event, *units):
        for unit in units:
            ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)

    def create_visible_event(self, **overrides):
        """Create an event ordinary members can see after SE-RETIRE.1B.

        The zero-audience-row legacy runtime fallback is retired, so ordinary
        users no longer see zero-row events. Rendering/display tests that only
        need an ordinary-visible event attach a root audience row, which matches
        every authenticated user via membership-core, replacing the old
        zero-row global default these tests used to rely on.
        """
        event = self.create_event(**overrides)
        self.add_audience(event, self.root_unit)
        return event

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
            "audience_units": [self.root_unit.id],
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
            "audience_units": [self.root_unit.id],
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

    def test_zero_row_global_event_hidden_from_regular_user(self):
        # SE-RETIRE.1B: the zero-audience-row legacy fallback is retired. A
        # published global event with no ServiceEventAudienceScope rows is an
        # invalid/safety state and ordinary users fail closed, even though the
        # legacy scope_type is global.
        self.set_language("en")
        event = self.create_event()

        self.client.login(username="regular", password="testpass123")
        list_response = self.client.get(reverse("service_event_list"))
        detail_response = self.client.get(
            reverse("service_event_detail", args=[event.id])
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertNotContains(list_response, event.title_en)
        self.assertEqual(detail_response.status_code, 302)
        self.assertEqual(detail_response.url, reverse("service_event_list"))
        self.assertFalse(event.can_be_seen_by(self.user))

    def test_root_audience_global_event_visible_to_regular_user(self):
        # SE-RETIRE.1B: ordinary visibility now requires audience rows. A root
        # audience row matches every authenticated user (membership-core),
        # which is how a whole-church gathering is now expressed.
        self.set_language("en")
        event = self.create_visible_event()

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("service_event_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, event.title_en)
        self.assertTrue(event.can_be_seen_by(self.user))

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

    def test_zero_row_district_event_hidden_even_when_profile_group_matches(self):
        # SE-RETIRE.1B: a zero-row district event no longer consults the legacy
        # district scope or Profile.small_group, so even a user whose profile
        # small group is in the matching district fails closed.
        self.set_language("en")
        event = self.create_event(
            title_en="North Event",
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=self.north,
        )

        self.client.login(username="same_district", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("service_event_list"))
        self.assertFalse(event.can_be_seen_by(self.same_district_user))

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

    def test_zero_row_small_group_event_hidden_even_when_profile_group_matches(self):
        # SE-RETIRE.1B: a zero-row small-group event no longer consults the
        # legacy small_group scope or Profile.small_group, so even the matching
        # small-group member fails closed.
        self.set_language("en")
        event = self.create_event(
            title_en="Group Event",
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("service_event_list"))
        self.assertFalse(event.can_be_seen_by(self.user))

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

    def test_audience_scope_rows_govern_visibility_over_legacy_fields(self):
        # SE-AS.4: audience rows, when present, replace the legacy scope as
        # the ordinary-user audience source. This unmapped custom unit
        # matches no ordinary users, so the legacy district match no longer
        # applies; managers keep access.
        event = self.create_event(
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=self.north,
        )
        unit = self.create_structure_unit("CM", "Chinese Ministry")
        ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)

        self.assertFalse(event.can_be_seen_by(self.same_district_user))
        self.assertFalse(event.can_be_seen_by(self.other_user))
        self.assertTrue(event.can_be_seen_by(self.staff))

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

    def test_service_event_form_requires_audience_units(self):
        english_form = ServiceEventForm(language="en")
        chinese_form = ServiceEventForm(language="zh")

        self.assertIn("audience_units", english_form.fields)
        self.assertTrue(english_form.fields["audience_units"].required)
        self.assertEqual(english_form.fields["audience_units"].label, "Audience Scope")
        self.assertIn(
            "Selected units control which ordinary users can see this gathering.",
            english_form.fields["audience_units"].help_text,
        )
        self.assertIn(
            "Select one or more units before saving",
            english_form.fields["audience_units"].help_text,
        )
        self.assertNotIn("scope_type", english_form.fields)
        self.assertNotIn("district", english_form.fields)
        self.assertNotIn("small_group", english_form.fields)
        self.assertIn("audience_units", chinese_form.fields)
        self.assertEqual(chinese_form.fields["audience_units"].label, "适用范围")
        self.assertIn(
            "选择的教会结构单元会决定普通用户能否看到这个聚会。",
            chinese_form.fields["audience_units"].help_text,
        )
        self.assertIn(
            "保存前请至少选择一个单元",
            chinese_form.fields["audience_units"].help_text,
        )
        self.assertNotIn("scope_type", chinese_form.fields)
        self.assertNotIn("district", chinese_form.fields)
        self.assertNotIn("small_group", chinese_form.fields)

    def test_service_event_create_form_keeps_audience_picker_section_visible(self):
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        ChurchStructureUnit.objects.create(
            parent=root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="中文部",
            name_en="Chinese Ministry",
        )
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.get(reverse("create_service_event"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("audience-picker-shell", content)
        self.assertContains(response, '<label class="form-label">Audience Scope</label>')
        self.assertContains(response, "data-audience-picker")
        self.assertContains(response, "Whole Church")
        self.assertContains(response, "data-audience-toggle")
        self.assertContains(response, 'aria-expanded="false"')
        self.assertContains(response, 'data-depth="1"')
        self.assertContains(response, "function updateVisibility()")

    def test_recurring_create_form_keeps_audience_picker_section_visible(self):
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        ChurchStructureUnit.objects.create(
            parent=root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="中文部",
            name_en="Chinese Ministry",
        )
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.get(reverse("create_recurring_service_events"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("audience-picker-shell", content)
        self.assertContains(response, '<label class="form-label">Audience Scope</label>')
        self.assertContains(response, "data-audience-picker")
        self.assertContains(response, "Whole Church")
        self.assertContains(response, "data-audience-toggle")
        self.assertContains(response, 'aria-expanded="false"')

    def test_service_event_edit_form_preselects_existing_audience_rows(self):
        event = self.create_event()
        unit = self.create_structure_unit("YOUTH", "Youth Fellowship")
        ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)

        form = ServiceEventForm(instance=event, language="en")

        self.assertEqual(form.audience_selected_ids(), {unit.id})

    def test_service_event_edit_form_expands_selected_descendant_path(self):
        self.set_language("en")
        event = self.create_event()
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        parent = ChurchStructureUnit.objects.create(
            parent=root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="中文部",
            name_en="Chinese Ministry",
        )
        selected = ChurchStructureUnit.objects.create(
            parent=parent,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4",
            name="Rainbow 4",
        )
        ServiceEventAudienceScope.objects.create(service_event=event, unit=selected)
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.get(reverse("edit_service_event", args=[event.id]))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rainbow 4")
        self.assertIn(f'data-ancestors="{root.id} {parent.id}"', content)
        self.assertIn(f'value="{selected.id}"', content)
        self.assertIn("checked", content)
        self.assertContains(response, "expandAncestors(optionEl(checkbox))")

    def test_service_event_form_omits_legacy_scope_controls_in_both_languages(self):
        self.client.login(username="pastor_event", password="testpass123")
        self.set_language("en")

        english_response = self.client.get(reverse("create_service_event"))

        self.assertContains(english_response, "Audience Scope")
        self.assertNotContains(
            english_response,
            "Converted when no structure audience is selected",
        )
        self.assertNotContains(english_response, 'name="scope_type"')
        self.assertNotContains(english_response, 'name="district"')
        self.assertNotContains(english_response, 'name="small_group"')
        self.set_language("zh")

        chinese_response = self.client.get(reverse("create_service_event"))

        self.assertContains(chinese_response, "适用范围")
        self.assertNotContains(chinese_response, "未选择上方范围时用于转换")
        self.assertNotContains(chinese_response, 'name="scope_type"')
        self.assertNotContains(chinese_response, 'name="district"')
        self.assertNotContains(chinese_response, 'name="small_group"')

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

    def test_manager_create_with_audience_units_does_not_write_legacy_scope_fields(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(
                scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
                district="",
                small_group=self.group.id,
                audience_units=[self.group_unit.id],
            ),
        )

        self.assertEqual(response.status_code, 302)
        event = ServiceEvent.objects.get(title_en="Special Meeting")
        self.assertEqual(list(event.get_audience_scope_units()), [self.group_unit])
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_GLOBAL)
        self.assertIsNone(event.district)
        self.assertIsNone(event.small_group)

    def test_manager_create_without_audience_is_rejected_without_legacy_write(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(
                scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
                district="",
                small_group=self.group.id,
                audience_units=[],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ServiceEvent.objects.filter(title_en="Special Meeting").exists())
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 0)

    def test_manager_create_ignores_unmapped_legacy_scope_post_keys(self):
        self.set_language("en")
        unmapped = District.objects.create(name="Unmapped District")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(
                scope_type=ServiceEvent.SCOPE_DISTRICT,
                district=unmapped.id,
                small_group="",
                audience_units=[self.root_unit.id],
            ),
        )

        self.assertEqual(response.status_code, 302)
        event = ServiceEvent.objects.get(title_en="Special Meeting")
        self.assertEqual(list(event.get_audience_scope_units()), [self.root_unit])
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_GLOBAL)
        self.assertIsNone(event.district)
        self.assertIsNone(event.small_group)

    def test_manager_create_with_audience_units_saves_rows_and_controls_visibility(self):
        self.set_language("en")
        unit = self.create_structure_unit("R4", "Rainbow 4")
        self.group.church_structure_unit = unit
        self.group.save(update_fields=["church_structure_unit"])
        # CS-CORE.2B-A: audience-row matching is membership-core.
        ChurchStructureMembership.objects.create(
            user=self.user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate() - timezone.timedelta(days=1),
        )
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(audience_units=[unit.id]),
        )

        self.assertEqual(response.status_code, 302)
        event = ServiceEvent.objects.get(title_en="Special Meeting")
        self.assertEqual(list(event.get_audience_scope_units()), [unit])
        self.assertTrue(event.can_be_seen_by(self.user))
        self.assertFalse(event.can_be_seen_by(self.same_district_user))
        self.assertFalse(event.can_be_seen_by(self.other_user))

    def test_manager_create_with_audience_preserves_scheduling_fields_only(self):
        self.set_language("en")
        unit = self.create_structure_unit("R4", "Rainbow 4")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(
                audience_units=[unit.id],
                required_teams=[self.required_team.id],
                rotation_anchor_team=self.other_required_team.id,
            ),
        )

        self.assertEqual(response.status_code, 302)
        event = ServiceEvent.objects.get(title_en="Special Meeting")
        self.assertEqual(list(event.get_audience_scope_units()), [unit])
        self.assertEqual(
            set(event.required_teams.values_list("id", flat=True)),
            {self.required_team.id},
        )
        self.assertEqual(event.rotation_anchor_team, self.other_required_team)
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

    def test_manager_edit_replaces_audience_rows(self):
        self.set_language("en")
        event = self.create_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )
        first_unit = self.create_structure_unit("R4", "Rainbow 4")
        second_unit = self.create_structure_unit("R5", "Rainbow 5")
        ServiceEventAudienceScope.objects.create(service_event=event, unit=first_unit)
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("edit_service_event", args=[event.id]),
            self.event_post_data(
                title="更新后的聚会",
                title_en="Updated Event",
                audience_units=[second_unit.id],
            ),
        )

        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(list(event.get_audience_scope_units()), [second_unit])
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_SMALL_GROUP)
        self.assertEqual(event.small_group, self.group)
        self.assertIsNone(event.district)

    def test_manager_edit_ignores_legacy_scope_post_keys(self):
        self.set_language("en")
        event = self.create_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )
        existing_unit = self.create_structure_unit("KEEP", "Keep Audience Unit")
        replacement_unit = self.create_structure_unit("NEW", "New Audience Unit")
        ServiceEventAudienceScope.objects.create(service_event=event, unit=existing_unit)
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("edit_service_event", args=[event.id]),
            self.event_post_data(
                title="更新后的聚会",
                title_en="Updated Event",
                scope_type=ServiceEvent.SCOPE_DISTRICT,
                district=self.south.id,
                small_group="",
                audience_units=[replacement_unit.id],
            ),
        )

        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(list(event.get_audience_scope_units()), [replacement_unit])
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_SMALL_GROUP)
        self.assertEqual(event.small_group, self.group)
        self.assertIsNone(event.district)

    def test_manager_edit_clearing_audience_preserves_existing_legacy_fields(self):
        self.set_language("en")
        event = self.create_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )
        existing_unit = self.create_structure_unit("KEEP", "Keep Audience Unit")
        ServiceEventAudienceScope.objects.create(service_event=event, unit=existing_unit)
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("edit_service_event", args=[event.id]),
            self.event_post_data(
                title_en="Updated Event",
                audience_units=[],
            ),
        )

        self.assertEqual(response.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(list(event.get_audience_scope_units()), [existing_unit])
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_SMALL_GROUP)
        self.assertEqual(event.small_group, self.group)
        self.assertIsNone(event.district)

    def test_ancestor_descendant_audience_selection_is_rejected_without_partial_save(self):
        self.set_language("en")
        parent = self.create_structure_unit("CM", "Chinese Ministry")
        child = self.create_structure_unit("CM-R4", "Rainbow 4", parent=parent)
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(audience_units=[parent.id, child.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Do not select both a unit and one of its parent or child units.",
        )
        self.assertNotContains(response, "audience-picker-shell")
        content = response.content.decode()
        self.assertIn(f'value="{parent.id}"', content)
        self.assertIn(f'value="{child.id}"', content)
        self.assertFalse(ServiceEvent.objects.filter(title_en="Special Meeting").exists())
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 0)

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

    def test_service_event_form_excludes_legacy_scope_fields(self):
        english_form = ServiceEventForm(language="en")
        chinese_form = ServiceEventForm(language="zh")

        for form in (english_form, chinese_form):
            self.assertNotIn("scope_type", form.fields)
            self.assertNotIn("district", form.fields)
            self.assertNotIn("small_group", form.fields)

    def test_ministry_context_label_can_be_saved_without_changing_visibility(self):
        self.set_language("en")
        event = self.create_visible_event(
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

    def test_manager_create_does_not_accept_legacy_district_scope(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(
                scope_type=ServiceEvent.SCOPE_DISTRICT,
                district=self.north.id,
                small_group="",
                audience_units=[self.north_unit.id],
            ),
        )

        self.assertEqual(response.status_code, 302)
        event = ServiceEvent.objects.get(title_en="Special Meeting")
        self.assertEqual(list(event.get_audience_scope_units()), [self.north_unit])
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_GLOBAL)
        self.assertIsNone(event.district)
        self.assertIsNone(event.small_group)

    def test_manager_create_does_not_accept_legacy_small_group_scope(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_service_event"),
            self.event_post_data(
                scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
                district="",
                small_group=self.group.id,
                audience_units=[self.group_unit.id],
            ),
        )

        self.assertEqual(response.status_code, 302)
        event = ServiceEvent.objects.get(title_en="Special Meeting")
        self.assertEqual(list(event.get_audience_scope_units()), [self.group_unit])
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_GLOBAL)
        self.assertIsNone(event.district)
        self.assertIsNone(event.small_group)

    def test_chinese_list_and_detail_pages_show_chinese_labels(self):
        self.set_language("zh")
        event = self.create_visible_event()

        self.client.login(username="regular", password="testpass123")
        list_response = self.client.get(reverse("service_event_list"))
        detail_response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertContains(list_response, "教会聚会")
        self.assertContains(list_response, "聚会类型")
        self.assertContains(detail_response, "开始时间")
        self.assertNotContains(detail_response, "范围")

    def test_english_list_and_detail_pages_show_english_labels(self):
        self.set_language("en")
        event = self.create_visible_event()

        self.client.login(username="regular", password="testpass123")
        list_response = self.client.get(reverse("service_event_list"))
        detail_response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertContains(list_response, "Church Gatherings")
        self.assertContains(list_response, "Event Type")
        self.assertContains(detail_response, "Start Time")
        self.assertNotContains(detail_response, "Scope")

    def test_regular_viewer_does_not_see_required_teams_metadata(self):
        self.set_language("en")
        event = self.create_visible_event()
        event.required_teams.add(self.required_team)

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Management details")
        self.assertNotContains(response, "Required Ministry Teams")
        self.assertNotContains(response, "Lighting Team")
        self.assertNotContains(response, "Missing")
        self.assertNotContains(response, "Unassigned")
        self.assertNotContains(response, "Coverage")

    def test_staff_viewer_sees_required_teams_metadata(self):
        self.set_language("en")
        event = self.create_event()
        event.required_teams.add(self.required_team)

        self.client.login(username="event_staff", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Management details")
        self.assertContains(response, "Required Ministry Teams")
        self.assertContains(response, "Lighting Team")

    def test_ordinary_event_viewer_does_not_see_rotation_anchor_metadata(self):
        self.set_language("en")
        event = self.create_visible_event(rotation_anchor_team=self.required_team)

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

    def test_staff_detail_shows_structure_audience_source_and_unit_labels(self):
        self.set_language("en")
        event = self.create_event()
        unit = self.create_structure_unit("YF", "Youth Fellowship")
        ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)

        self.client.login(username="event_staff", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visibility source: Structure audience")
        self.assertContains(response, "Youth Fellowship")
        self.assertContains(
            response,
            "Structure audience is selected; fallback settings are not an extra filter.",
        )
        self.assertContains(
            response,
            "This selection currently matches no ordinary users because it is not mapped to active legacy groups.",
        )
        self.assertNotContains(response, "YF")
        self.assertNotContains(response, "ServiceEventAudienceScope")

    def test_staff_detail_shows_legacy_fallback_source_and_readable_label(self):
        self.set_language("en")
        event = self.create_event(
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=self.north,
        )

        self.client.login(username="event_staff", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visibility source: Legacy fallback audience")
        self.assertContains(response, "District: North")
        self.assertContains(
            response,
            "No structure audience is selected; this gathering uses fallback audience settings.",
        )

    def test_ordinary_detail_does_not_expose_audience_architecture_terms(self):
        self.set_language("en")
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )
        event = self.create_event()
        ServiceEventAudienceScope.objects.create(service_event=event, unit=root)

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("service_event_detail", args=[event.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Visibility source")
        self.assertNotContains(response, "Structure audience")
        self.assertNotContains(response, "Legacy fallback")
        self.assertNotContains(response, "ServiceEventAudienceScope")
        self.assertNotContains(response, "CHURCH")

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
        event = self.create_visible_event()
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
        self.assertNotContains(response, "Required Ministry Teams")
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
        unit = self.create_structure_unit("R4", "Rainbow 4")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                preview="1",
                required_teams=[self.required_team.id],
                audience_units=[unit.id],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Events to Create")
        self.assertEqual(ServiceEvent.objects.count(), 0)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 0)

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

    def test_recurring_create_applies_same_audience_units_to_each_event(self):
        self.set_language("en")
        unit = self.create_structure_unit("R4", "Rainbow 4")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(create="1", audience_units=[unit.id]),
        )

        self.assertEqual(response.status_code, 200)
        events = ServiceEvent.objects.filter(title_en="Sunday Service")
        self.assertEqual(events.count(), 3)
        for event in events:
            self.assertEqual(list(event.get_audience_scope_units()), [unit])
            self.assertEqual(event.scope_type, ServiceEvent.SCOPE_GLOBAL)
            self.assertIsNone(event.district)
            self.assertIsNone(event.small_group)

    def test_recurring_create_ignores_legacy_scope_post_keys_for_all_events(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                create="1",
                scope_type=ServiceEvent.SCOPE_DISTRICT,
                district=self.north.id,
                small_group="",
                audience_units=[self.north_unit.id],
            ),
        )

        self.assertEqual(response.status_code, 200)
        events = ServiceEvent.objects.filter(title_en="Sunday Service")
        self.assertEqual(events.count(), 3)
        for event in events:
            self.assertEqual(list(event.get_audience_scope_units()), [self.north_unit])
            self.assertEqual(event.scope_type, ServiceEvent.SCOPE_GLOBAL)
            self.assertIsNone(event.district)
            self.assertIsNone(event.small_group)

    def test_recurring_create_empty_audience_is_rejected_without_legacy_write(self):
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                create="1",
                scope_type=ServiceEvent.SCOPE_GLOBAL,
                audience_units=[],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ServiceEvent.objects.filter(title_en="Sunday Service").count(), 0)
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 0)

    def test_recurring_create_ignores_unmapped_legacy_scope_post_keys(self):
        self.set_language("en")
        unmapped = District.objects.create(name="Unmapped Recurring District")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                create="1",
                scope_type=ServiceEvent.SCOPE_DISTRICT,
                district=unmapped.id,
                small_group="",
                audience_units=[self.root_unit.id],
            ),
        )

        self.assertEqual(response.status_code, 200)
        events = ServiceEvent.objects.filter(title_en="Sunday Service")
        self.assertEqual(events.count(), 3)
        for event in events:
            self.assertEqual(list(event.get_audience_scope_units()), [self.root_unit])
            self.assertEqual(event.scope_type, ServiceEvent.SCOPE_GLOBAL)
            self.assertIsNone(event.district)
            self.assertIsNone(event.small_group)

    def test_recurring_preview_empty_audience_creates_no_rows(self):
        # Preview never writes events or audience rows.
        self.set_language("en")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                preview="1",
                scope_type=ServiceEvent.SCOPE_DISTRICT,
                district=self.north.id,
                small_group="",
                audience_units=[],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Events to Create")
        self.assertEqual(ServiceEvent.objects.count(), 0)
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 0)

    def test_manually_created_zero_row_event_fails_closed_for_ordinary_users(self):
        # SE-RETIRE.1B: the runtime zero-row legacy fallback is retired. A
        # ServiceEvent created directly (not via the guarded form) with zero
        # audience rows is now an invalid/safety state for ordinary visibility:
        # ordinary users fail closed regardless of legacy fields or
        # Profile.small_group, while managers/staff keep their override.
        event = self.create_event(
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=self.north,
        )

        self.assertEqual(event.audience_scope_links.count(), 0)
        self.assertFalse(event.can_be_seen_by(self.user))
        self.assertFalse(event.can_be_seen_by(self.same_district_user))
        self.assertFalse(event.can_be_seen_by(self.other_user))
        self.assertTrue(event.can_be_seen_by(self.staff))

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

    def test_recurring_create_does_not_backfill_skipped_duplicate_audience(self):
        self.set_language("en")
        start_date = self.next_sunday()
        start_datetime = self.matching_recurring_start_datetime(start_date)
        existing_event = self.create_event(
            title="主日崇拜",
            title_en="Sunday Service",
            start_datetime=start_datetime,
            end_datetime=start_datetime + timezone.timedelta(hours=1, minutes=30),
        )
        unit = self.create_structure_unit("R4", "Rainbow 4")
        self.client.login(username="pastor_event", password="testpass123")

        response = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(create="1", audience_units=[unit.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "skipped: 1")
        existing_event.refresh_from_db()
        self.assertEqual(existing_event.audience_scope_links.count(), 0)
        new_events = ServiceEvent.objects.filter(title_en="Sunday Service").exclude(
            id=existing_event.id,
        )
        self.assertEqual(new_events.count(), 2)
        for event in new_events:
            self.assertEqual(list(event.get_audience_scope_units()), [unit])

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

    # --- UI-H.3A member-facing event discovery polish ---

    def assert_single_active_nav(self, response, url_name):
        content = response.content.decode()
        expected_href = reverse(url_name)
        self.assertEqual(content.count('class="nav-link active"'), 1)
        self.assertRegex(
            content,
            r'class="nav-link active"\s+href="%s"' % re.escape(expected_href),
        )

    def test_member_list_shows_member_subtitle_english(self):
        self.set_language("en")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("service_event_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Upcoming worship services, church meetings, and gatherings you can view.",
        )

    def test_member_list_shows_member_subtitle_chinese(self):
        self.set_language("zh")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("service_event_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "查看你可以看到的近期主日崇拜、教会聚会和相关安排。")

    def test_member_list_empty_state_english(self):
        self.set_language("en")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("service_event_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "There are no upcoming events to show right now.",
        )

    def test_member_list_empty_state_chinese(self):
        self.set_language("zh")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("service_event_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "目前没有可显示的近期活动。")

    def test_member_list_shows_visible_event_with_type_time_and_detail_link(self):
        self.set_language("en")
        # Use a future start so the event stays under the default "upcoming"
        # tab; a hardcoded past date silently drops out of the list once that
        # date passes. Fix the time-of-day so the rendered label is stable.
        start = (timezone.now() + timezone.timedelta(days=3)).replace(
            hour=19, minute=30, second=0, microsecond=0
        )
        event = self.create_visible_event(
            start_datetime=start,
            end_datetime=start + timezone.timedelta(hours=2),
        )
        expected_label = member_datetime(start, "en")

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("service_event_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, "Event Type")
        self.assertContains(response, expected_label)
        # The member format is used, not the long "June 12, 2026" style.
        self.assertNotContains(response, "%s %d, %d" % (start.strftime("%B"), start.day, start.year))
        self.assertContains(response, "View details")
        detail_url = reverse("service_event_detail", args=[event.id])
        self.assertContains(response, 'href="%s"' % detail_url)

    def test_member_list_hides_management_actions_from_regular_user(self):
        self.set_language("en")
        self.create_event()

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("service_event_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "New Service Event")
        self.assertNotContains(response, "Create Recurring Events")

    def test_member_list_keeps_management_actions_for_manager(self):
        self.set_language("en")
        self.create_event()

        self.client.login(username="pastor_event", password="testpass123")
        response = self.client.get(reverse("service_event_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New Service Event")
        self.assertContains(response, "Create Recurring Events")

    def test_member_list_hides_zero_row_district_event_from_all_ordinary_users(self):
        # SE-RETIRE.1B: a zero-row district event fails closed for every
        # ordinary user, including the one whose Profile.small_group would have
        # matched the retired legacy district rule.
        self.set_language("en")
        self.create_event(
            title_en="North District Event",
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=self.north,
        )

        self.client.login(username="same_district", password="testpass123")
        same_district = self.client.get(reverse("service_event_list"))
        self.assertNotContains(same_district, "North District Event")

        self.client.login(username="other_group", password="testpass123")
        other = self.client.get(reverse("service_event_list"))
        self.assertNotContains(other, "North District Event")

    def test_member_detail_shows_details_and_back_link(self):
        self.set_language("en")
        event = self.create_visible_event(
            start_datetime=datetime(2026, 6, 12, 19, 30, tzinfo=datetime_timezone.utc),
            end_datetime=datetime(2026, 6, 12, 21, 0, tzinfo=datetime_timezone.utc),
        )

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(
            reverse("service_event_detail", args=[event.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, "Start Time")
        self.assertContains(response, "Fri, Jun 12, 7:30 PM")
        self.assertContains(response, "Fri, Jun 12, 9:00 PM")
        self.assertNotContains(response, "June 12, 2026")
        self.assertContains(response, "Worship together.")
        self.assertContains(response, "Back to Church Gatherings")
        list_url = reverse("service_event_list")
        self.assertContains(response, 'href="%s"' % list_url)

    def test_member_detail_back_link_chinese(self):
        self.set_language("zh")
        event = self.create_visible_event()

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(
            reverse("service_event_detail", args=[event.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "返回教会聚会")

    def test_member_event_list_marks_events_nav_active(self):
        self.set_language("en")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("service_event_list"))

        self.assertEqual(response.status_code, 200)
        self.assert_single_active_nav(response, "service_event_list")

    def test_member_event_detail_marks_events_nav_active(self):
        self.set_language("en")
        event = self.create_visible_event()

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(
            reverse("service_event_detail", args=[event.id])
        )

        self.assertEqual(response.status_code, 200)
        # The active member nav link always points at the events list.
        self.assert_single_active_nav(response, "service_event_list")

    def test_staff_event_management_page_marks_staff_nav_active(self):
        self.set_language("en")
        self.client.login(username="event_staff", password="testpass123")

        response = self.client.get(reverse("create_service_event"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        # Management routes stay under the staff nav, not the member events nav.
        self.assertEqual(content.count('class="nav-link active"'), 1)
        self.assertIn('<summary class="nav-link active">', content)

    def test_member_nav_addition_does_not_broaden_event_management(self):
        self.set_language("en")
        event = self.create_event()

        self.client.login(username="regular", password="testpass123")
        edit_response = self.client.get(
            reverse("edit_service_event", args=[event.id])
        )

        self.assertEqual(edit_response.status_code, 302)
        self.assertEqual(edit_response.url, reverse("service_event_list"))

    def test_member_detail_hides_management_metadata(self):
        self.set_language("en")
        event = self.create_visible_event(rotation_anchor_team=self.required_team)
        event.required_teams.add(self.required_team)

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(
            reverse("service_event_detail", args=[event.id])
        )

        self.assertEqual(response.status_code, 200)
        # Attendee-relevant information stays visible.
        self.assertContains(response, "Event Type")
        self.assertContains(response, "Start Time")
        # Management / scheduling metadata is hidden from ordinary members.
        self.assertNotContains(response, "Management details")
        # The management audience-source wording (SE-AS.5) stays staff-only.
        self.assertNotContains(response, "Visibility source")
        self.assertNotContains(response, "Structure audience")
        self.assertNotContains(response, "Legacy fallback")
        self.assertNotContains(response, "Status")
        self.assertNotContains(response, "Required Ministry Teams")
        self.assertNotContains(response, "Rotation Anchor Team")
        self.assertNotContains(response, "Assignment Coverage")
        self.assertNotContains(response, "Missing")
        self.assertNotContains(response, "Unassigned")

    def test_member_detail_hides_management_metadata_chinese(self):
        self.set_language("zh")
        event = self.create_visible_event(rotation_anchor_team=self.required_team)
        event.required_teams.add(self.required_team)

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(
            reverse("service_event_detail", args=[event.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "管理信息")
        # The management audience-source wording (SE-AS.5) stays staff-only.
        self.assertNotContains(response, "可见范围来源")
        self.assertNotContains(response, "教会结构适用范围")
        self.assertNotContains(response, "备用适用范围")
        self.assertNotContains(response, "状态")
        self.assertNotContains(response, "需要的事工团队")
        self.assertNotContains(response, "配搭参考团队")
        self.assertNotContains(response, "服事覆盖")

    def test_manager_detail_shows_management_metadata(self):
        self.set_language("en")
        event = self.create_event(rotation_anchor_team=self.required_team)
        event.required_teams.add(self.required_team)

        self.client.login(username="pastor_event", password="testpass123")
        response = self.client.get(
            reverse("service_event_detail", args=[event.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Management details")
        self.assertContains(response, "Status")
        # SE-AS.5 replaced the old "Scope" label with the effective
        # audience "Visibility source" line in the management card.
        self.assertContains(response, "Visibility source")
        self.assertContains(response, "Required Ministry Teams")
        self.assertContains(response, "Rotation Anchor Team")

    def test_coverage_viewer_detail_shows_management_metadata(self):
        self.set_language("en")
        event = self.create_event(rotation_anchor_team=self.required_team)
        event.required_teams.add(self.required_team)
        ChurchRoleAssignment.objects.create(
            user=self.other_user,
            role=ChurchRoleAssignment.ROLE_COWORKER,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        self.client.login(username="other_group", password="testpass123")
        response = self.client.get(
            reverse("service_event_detail", args=[event.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Management details")
        self.assertContains(response, "Required Ministry Teams")
        self.assertContains(response, "Rotation Anchor Team")


class ServiceEventAudienceRuntimeVisibilityTests(TestCase):
    """SE-AS.4 / CS-CORE.2B-A runtime visibility rules.

    Events with ServiceEventAudienceScope rows use those rows as the
    ordinary-user audience source, matched by active primary
    ChurchStructureMembership (membership-core); Profile.small_group alone
    grants nothing there. Events with no rows fail closed for ordinary users;
    legacy scope_type / district / small_group fields are not consulted.
    """

    def setUp(self):
        # Structure tree mirroring the seeded layout:
        # CHURCH root -> CM/EM contexts -> districts -> small groups.
        self.root_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )
        self.cm_unit = ChurchStructureUnit.objects.create(
            parent=self.root_unit,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="Chinese Ministry",
        )
        self.em_unit = ChurchStructureUnit.objects.create(
            parent=self.root_unit,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="EM",
            name="English Ministry",
        )
        self.north_unit = ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="NORTH",
            name="North District",
        )
        self.south_unit = ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="SOUTH",
            name="South District",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4",
            name="Rainbow 4",
        )
        self.group_b_unit = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4B",
            name="Rainbow 4B",
        )
        self.other_group_unit = ChurchStructureUnit.objects.create(
            parent=self.south_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R5",
            name="Rainbow 5",
        )
        self.em_group_unit = ChurchStructureUnit.objects.create(
            parent=self.em_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="EA1",
            name="English Adult 1",
        )
        self.unmapped_unit = ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="NEWMIN",
            name="New Ministry Unit",
        )

        self.cm = MinistryContext.objects.create(
            code="CM",
            name="Chinese Ministry",
            church_structure_unit=self.cm_unit,
        )
        self.em = MinistryContext.objects.create(
            code="EM",
            name="English Ministry",
            church_structure_unit=self.em_unit,
        )
        self.north = District.objects.create(
            name="North",
            ministry_context=self.cm,
            church_structure_unit=self.north_unit,
        )
        self.south = District.objects.create(
            name="South",
            ministry_context=self.cm,
            church_structure_unit=self.south_unit,
        )
        # EM district stays unmapped on purpose; its group maps directly.
        self.em_district = District.objects.create(
            name="EM Adults",
            ministry_context=self.em,
        )
        self.group = SmallGroup.objects.create(
            name="Rainbow 4",
            district=self.north,
            church_structure_unit=self.group_unit,
        )
        self.group_b = SmallGroup.objects.create(
            name="Rainbow 4B",
            district=self.north,
            church_structure_unit=self.group_b_unit,
        )
        self.other_group = SmallGroup.objects.create(
            name="Rainbow 5",
            district=self.south,
            church_structure_unit=self.other_group_unit,
        )
        self.em_group = SmallGroup.objects.create(
            name="English Adult 1",
            district=self.em_district,
            church_structure_unit=self.em_group_unit,
        )

        self.group_user = self.create_member("audience_r4", self.group)
        self.group_b_user = self.create_member("audience_r4b", self.group_b)
        self.other_user = self.create_member("audience_r5", self.other_group)
        self.em_user = self.create_member("audience_em", self.em_group)
        self.no_group_user = self.create_member("audience_nogroup", None)
        self.staff = User.objects.create_user(
            username="audience_staff",
            password="testpass123",
            is_staff=True,
        )

        self.future_time = timezone.now() + timezone.timedelta(days=3)

    def create_member(self, username, small_group):
        """Create an in-sync member: legacy group plus matching membership."""
        user = User.objects.create_user(username=username, password="testpass123")
        if small_group is not None:
            user.profile.small_group = small_group
            user.profile.save()
            self.create_membership(user, small_group.church_structure_unit)
        return user

    def create_membership(self, user, unit, **overrides):
        data = {
            "user": user,
            "unit": unit,
            "status": ChurchStructureMembership.STATUS_ACTIVE,
            "is_primary": True,
            "start_date": timezone.localdate() - timezone.timedelta(days=1),
        }
        data.update(overrides)
        return ChurchStructureMembership.objects.create(**data)

    def create_event(self, **overrides):
        data = {
            "title": "聚会",
            "title_en": "Audience Event",
            "event_type": ServiceEvent.EVENT_SPECIAL_MEETING,
            "start_datetime": self.future_time,
            "scope_type": ServiceEvent.SCOPE_GLOBAL,
            "status": ServiceEvent.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return ServiceEvent.objects.create(**data)

    def add_audience(self, event, *units):
        for unit in units:
            ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def test_no_audience_rows_fail_closed_for_ordinary_users(self):
        # SE-RETIRE.1B: this previously asserted zero-row legacy-fallback
        # parity. The zero-row runtime fallback is now retired, so zero-row
        # events fail closed for every ordinary user regardless of legacy
        # scope_type / district / small_group or Profile.small_group, while
        # managers/staff keep their override.
        global_event = self.create_event()
        self.assertFalse(global_event.can_be_seen_by(self.group_user))
        self.assertFalse(global_event.can_be_seen_by(self.no_group_user))
        self.assertTrue(global_event.can_be_seen_by(self.staff))

        district_event = self.create_event(
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=self.north,
        )
        self.assertFalse(district_event.can_be_seen_by(self.group_user))
        self.assertFalse(district_event.can_be_seen_by(self.group_b_user))
        self.assertFalse(district_event.can_be_seen_by(self.other_user))
        self.assertFalse(district_event.can_be_seen_by(self.no_group_user))
        self.assertTrue(district_event.can_be_seen_by(self.staff))

        group_event = self.create_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )
        self.assertFalse(group_event.can_be_seen_by(self.group_user))
        self.assertFalse(group_event.can_be_seen_by(self.group_b_user))
        self.assertFalse(group_event.can_be_seen_by(self.no_group_user))
        self.assertTrue(group_event.can_be_seen_by(self.staff))

    def test_audience_rows_override_legacy_scope_fields(self):
        # Legacy says global, audience rows narrow it to one group.
        narrowed = self.create_event()
        self.add_audience(narrowed, self.group_unit)
        self.assertTrue(narrowed.can_be_seen_by(self.group_user))
        self.assertFalse(narrowed.can_be_seen_by(self.group_b_user))
        self.assertFalse(narrowed.can_be_seen_by(self.other_user))

        # Legacy says one small group, audience rows widen to whole church.
        widened = self.create_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
            small_group=self.other_group,
        )
        self.add_audience(widened, self.root_unit)
        self.assertTrue(widened.can_be_seen_by(self.group_user))
        self.assertTrue(widened.can_be_seen_by(self.em_user))

    def test_small_group_unit_audience_matches_only_that_groups_members(self):
        event = self.create_event()
        self.add_audience(event, self.group_unit)

        self.assertTrue(event.can_be_seen_by(self.group_user))
        self.assertFalse(event.can_be_seen_by(self.group_b_user))
        self.assertFalse(event.can_be_seen_by(self.other_user))
        self.assertFalse(event.can_be_seen_by(self.em_user))

    def test_district_unit_audience_matches_descendant_group_members(self):
        event = self.create_event()
        self.add_audience(event, self.north_unit)

        self.assertTrue(event.can_be_seen_by(self.group_user))
        self.assertTrue(event.can_be_seen_by(self.group_b_user))
        self.assertFalse(event.can_be_seen_by(self.other_user))
        self.assertFalse(event.can_be_seen_by(self.em_user))
        self.assertFalse(event.can_be_seen_by(self.no_group_user))

    def test_ministry_context_unit_audience_matches_context_groups(self):
        event = self.create_event()
        self.add_audience(event, self.cm_unit)

        self.assertTrue(event.can_be_seen_by(self.group_user))
        self.assertTrue(event.can_be_seen_by(self.other_user))
        self.assertFalse(event.can_be_seen_by(self.em_user))

    def test_multi_unit_selection_is_a_union(self):
        event = self.create_event()
        self.add_audience(event, self.group_b_unit, self.em_unit)

        self.assertTrue(event.can_be_seen_by(self.group_b_user))
        self.assertTrue(event.can_be_seen_by(self.em_user))
        self.assertFalse(event.can_be_seen_by(self.group_user))
        self.assertFalse(event.can_be_seen_by(self.other_user))

    def test_root_unit_audience_behaves_like_whole_church(self):
        event = self.create_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )
        self.add_audience(event, self.root_unit)

        self.assertTrue(event.can_be_seen_by(self.group_user))
        self.assertTrue(event.can_be_seen_by(self.em_user))
        self.assertTrue(event.can_be_seen_by(self.no_group_user))

    def test_unmapped_unit_audience_matches_no_ordinary_users(self):
        event = self.create_event()
        self.add_audience(event, self.unmapped_unit)

        self.assertFalse(event.can_be_seen_by(self.group_user))
        self.assertFalse(event.can_be_seen_by(self.other_user))
        self.assertFalse(event.can_be_seen_by(self.em_user))
        self.assertFalse(event.can_be_seen_by(self.no_group_user))
        self.assertTrue(event.can_be_seen_by(self.staff))

    def test_user_without_small_group_matches_only_root_audience(self):
        group_event = self.create_event()
        self.add_audience(group_event, self.group_unit)
        self.assertFalse(group_event.can_be_seen_by(self.no_group_user))

        root_event = self.create_event()
        self.add_audience(root_event, self.root_unit)
        self.assertTrue(root_event.can_be_seen_by(self.no_group_user))

    def test_active_primary_membership_grants_audience_visibility(self):
        event = self.create_event()
        self.add_audience(event, self.group_unit)

        # CS-CORE.2B-A: active primary membership in the selected unit grants
        # visibility even when Profile.small_group is missing entirely.
        self.create_membership(self.no_group_user, self.group_unit)
        self.assertTrue(event.can_be_seen_by(self.no_group_user))

        district_event = self.create_event()
        self.add_audience(district_event, self.north_unit)
        self.assertTrue(district_event.can_be_seen_by(self.no_group_user))

    def test_profile_small_group_alone_no_longer_grants_audience_visibility(self):
        profile_only = User.objects.create_user(
            username="audience_profile_only",
            password="testpass123",
        )
        profile_only.profile.small_group = self.group
        profile_only.profile.save()

        event = self.create_event()
        self.add_audience(event, self.group_unit)
        self.assertFalse(event.can_be_seen_by(profile_only))

        # Root audience rows still match any authenticated user.
        root_event = self.create_event()
        self.add_audience(root_event, self.root_unit)
        self.assertTrue(root_event.can_be_seen_by(profile_only))

        # SE-RETIRE.1B: zero-row events no longer consult Profile.small_group,
        # so a profile-only user (no membership) fails closed on a zero-row
        # small-group event too, not just on audience-row events.
        zero_row_event = self.create_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )
        self.assertFalse(zero_row_event.can_be_seen_by(profile_only))

    def test_requested_membership_does_not_grant_audience_visibility(self):
        event = self.create_event()
        self.add_audience(event, self.group_unit)

        self.create_membership(
            self.no_group_user,
            self.group_unit,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=False,
            start_date=None,
        )
        self.assertFalse(event.can_be_seen_by(self.no_group_user))

    def test_inactive_lifecycle_memberships_do_not_grant_audience_visibility(self):
        event = self.create_event()
        self.add_audience(event, self.group_unit)
        today = timezone.localdate()

        ended = self.create_member("audience_m_ended", None)
        future = self.create_member("audience_m_future", None)
        rejected = self.create_member("audience_m_rejected", None)
        cancelled = self.create_member("audience_m_cancelled", None)
        expired = self.create_member("audience_m_expired", None)

        self.create_membership(
            ended,
            self.group_unit,
            status=ChurchStructureMembership.STATUS_ENDED,
            start_date=today - timezone.timedelta(days=10),
            end_date=today - timezone.timedelta(days=1),
        )
        self.create_membership(
            future,
            self.group_unit,
            start_date=today + timezone.timedelta(days=1),
        )
        # Rejected/cancelled primary and active-expired rows fail model
        # validation by design, so insert them directly like drifted data.
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=rejected,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_REJECTED,
                    is_primary=True,
                    start_date=today - timezone.timedelta(days=10),
                ),
                ChurchStructureMembership(
                    user=cancelled,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_CANCELLED,
                    is_primary=True,
                    start_date=today - timezone.timedelta(days=10),
                ),
                ChurchStructureMembership(
                    user=expired,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today - timezone.timedelta(days=10),
                    end_date=today - timezone.timedelta(days=1),
                ),
            ]
        )

        for user in (ended, future, rejected, cancelled, expired):
            self.assertFalse(
                event.can_be_seen_by(user),
                msg=f"{user.username} must not see the audience-scoped event",
            )

    def test_multiple_active_primary_memberships_fail_closed(self):
        user = self.create_member("audience_multi_primary", None)
        today = timezone.localdate()
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=user,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
                ChurchStructureMembership(
                    user=user,
                    unit=self.group_b_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
            ]
        )

        # Both units sit under north, so either row alone would match; the
        # ambiguous pair must still fail closed for non-root audiences.
        event = self.create_event()
        self.add_audience(event, self.north_unit)
        self.assertFalse(event.can_be_seen_by(user))

        root_event = self.create_event()
        self.add_audience(root_event, self.root_unit)
        self.assertTrue(root_event.can_be_seen_by(user))

    def test_zero_row_events_fail_closed_regardless_of_membership(self):
        # SE-RETIRE.1B: this previously asserted that zero-row legacy-fallback
        # events read Profile.small_group only and that a zero-row global event
        # stayed visible. With the zero-row runtime fallback retired, zero-row
        # events fail closed for ordinary users whether or not they have a
        # ChurchStructureMembership; neither legacy fields nor membership rows
        # are consulted when an event has no audience rows.
        membership_only = User.objects.create_user(
            username="audience_membership_only",
            password="testpass123",
        )
        self.create_membership(membership_only, self.group_unit)

        district_event = self.create_event(
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=self.north,
        )
        self.assertFalse(district_event.can_be_seen_by(membership_only))

        group_event = self.create_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )
        self.assertFalse(group_event.can_be_seen_by(membership_only))

        global_event = self.create_event()
        self.assertFalse(global_event.can_be_seen_by(membership_only))
        # Managers/staff still see zero-row events via the unchanged override.
        self.assertTrue(global_event.can_be_seen_by(self.staff))

    def test_status_and_staff_behavior_preserved_with_audience_rows(self):
        draft = self.create_event(status=ServiceEvent.STATUS_DRAFT)
        self.add_audience(draft, self.root_unit)
        self.assertFalse(draft.can_be_seen_by(self.group_user))
        self.assertTrue(draft.can_be_seen_by(self.staff))

        cancelled = self.create_event(status=ServiceEvent.STATUS_CANCELLED)
        self.add_audience(cancelled, self.root_unit)
        self.assertFalse(cancelled.can_be_seen_by(self.group_user))
        self.assertTrue(cancelled.can_be_seen_by(self.staff))

    def test_audience_row_on_later_inactivated_unit_keeps_matching(self):
        # Parity decision per the SE-AS runtime migration plan: stored
        # selections keep matching when the unit is later deactivated, just
        # as legacy district/small-group checks never test is_active.
        event = self.create_event()
        self.add_audience(event, self.group_unit)

        self.group_unit.is_active = False
        self.group_unit.save()

        self.assertTrue(event.can_be_seen_by(self.group_user))
        self.assertFalse(event.can_be_seen_by(self.group_b_user))

    def test_event_list_and_detail_agree_with_audience_visibility(self):
        self.set_language("en")
        event = self.create_event(title_en="Audience Scoped Gathering")
        self.add_audience(event, self.group_unit)
        detail_url = reverse("service_event_detail", args=[event.id])

        self.client.login(username="audience_r4", password="testpass123")
        visible_list = self.client.get(reverse("service_event_list"))
        self.assertContains(visible_list, "Audience Scoped Gathering")
        visible_detail = self.client.get(detail_url)
        self.assertEqual(visible_detail.status_code, 200)

        self.client.login(username="audience_r5", password="testpass123")
        hidden_list = self.client.get(reverse("service_event_list"))
        self.assertNotContains(hidden_list, "Audience Scoped Gathering")
        hidden_detail = self.client.get(detail_url)
        self.assertEqual(hidden_detail.status_code, 302)
        self.assertEqual(hidden_detail.url, reverse("service_event_list"))

    def test_audience_selector_ui_is_available_after_runtime_migration(self):
        form = ServiceEventForm(language="en")
        self.assertIn("audience_units", form.fields)
        self.assertTrue(form.fields["audience_units"].required)

        self.set_language("en")
        self.client.login(username="audience_staff", password="testpass123")
        response = self.client.get(reverse("create_service_event"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-audience-picker")
        self.assertNotContains(response, "Converted when no structure audience is selected")
        self.assertNotContains(response, 'name="scope_type"')
        self.assertNotContains(response, 'name="district"')
        self.assertNotContains(response, 'name="small_group"')
