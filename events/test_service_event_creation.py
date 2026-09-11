import copy
from datetime import date, time
import os
import tempfile
import unittest
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.management import call_command
from django.db import OperationalError, connections
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from ministry.models import (
    MinistryTeam,
    ServiceProfileMinistryRequirement,
    TeamAssignment,
    TeamAssignmentMember,
)
from notifications.models import Notification

from .forms import RecurringServiceEventForm, ServiceEventForm
from .models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventRequiredTeam,
    ServiceProfile,
)
from .service_event_creation import (
    CreationReviewFailure,
    ServiceEventCreationError,
    build_creation_review,
    create_recurring_service_events,
    create_single_service_event,
)
from .service_profile_identity import build_pre_drop_legacy_key_inventory


User = get_user_model()


class ServiceEventCreationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="event_creator",
            password="testpass123",
            is_staff=True,
        )
        self.other_user = User.objects.create_user(
            username="other_creator",
            password="testpass123",
            is_staff=True,
        )
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="ROOT",
            name="教会",
            name_en="Church",
        )
        self.audience = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="GENERAL",
            name="一般事工",
            name_en="General Ministry",
        )
        self.team_a = MinistryTeam.objects.create(
            name="接待团队",
            name_en="Welcome Team",
            team_key="welcome",
            is_active=True,
            is_assignable=True,
        )
        self.team_b = MinistryTeam.objects.create(
            name="关怀团队",
            name_en="Care Team",
            team_key="care",
            is_active=True,
            is_assignable=True,
        )
        self.container = MinistryTeam.objects.create(
            name="事工部门",
            name_en="Ministry Department",
            team_key="ministry_department",
            is_active=True,
            is_assignable=False,
        )
        self.inactive_team = MinistryTeam.objects.create(
            name="历史团队",
            name_en="Historical Team",
            team_key="historical",
            is_active=False,
            is_assignable=False,
        )
        self.profile = ServiceProfile.objects.create(
            key="general_sunday",
            name="一般主日聚会",
            name_en="General Sunday Gathering",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            is_active=True,
        )
        self.requirement_a = ServiceProfileMinistryRequirement.objects.create(
            service_profile=self.profile,
            ministry_team=self.team_a,
            is_active=True,
            sort_order=20,
        )
        session = self.client.session
        session["language"] = "en"
        session.save()

    def single_data(self, **overrides):
        values = {
            "title": "一般主日聚会",
            "title_en": "General Sunday Gathering",
            "description": "",
            "description_en": "",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": timezone.make_aware(
                timezone.datetime(2030, 1, 6, 10, 0)
            ),
            "end_datetime": timezone.make_aware(
                timezone.datetime(2030, 1, 6, 11, 30)
            ),
            "location": "Main Hall",
            "meeting_link": "",
            "status": ServiceEvent.STATUS_PUBLISHED,
        }
        values.update(overrides)
        return values

    def recurring_data(self, **overrides):
        values = {
            "title": "一般主日聚会",
            "title_en": "General Sunday Gathering",
            "description": "",
            "description_en": "",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_date": date(2030, 1, 6),
            "end_date": date(2030, 1, 20),
            "weekday": "6",
            "start_time": time(10, 0),
            "end_time": time(11, 30),
            "location": "Main Hall",
            "meeting_link": "",
            "status": ServiceEvent.STATUS_PUBLISHED,
        }
        values.update(overrides)
        return values

    def single_post_data(self, **overrides):
        values = {
            "title": "一般主日聚会",
            "title_en": "General Sunday Gathering",
            "description": "",
            "description_en": "",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": "2030-01-06T10:00",
            "end_datetime": "2030-01-06T11:30",
            "location": "Main Hall",
            "meeting_link": "",
            "status": ServiceEvent.STATUS_PUBLISHED,
            "audience_units": [str(self.audience.pk)],
            "required_teams": [str(self.team_b.pk)],
            "service_profile": str(self.profile.pk),
        }
        values.update(overrides)
        return values

    def recurring_post_data(self, **overrides):
        values = {
            "title": "一般主日聚会",
            "title_en": "General Sunday Gathering",
            "description": "",
            "description_en": "",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_date": "2030-01-06",
            "end_date": "2030-01-20",
            "weekday": "6",
            "start_time": "10:00",
            "end_time": "11:30",
            "location": "Main Hall",
            "meeting_link": "",
            "status": ServiceEvent.STATUS_PUBLISHED,
            "audience_units": [str(self.audience.pk)],
            "required_teams": [str(self.team_b.pk)],
            "service_profile": str(self.profile.pk),
        }
        values.update(overrides)
        return values

    def review(self, *, mode="single", profile=None, recurring_data=None, user=None):
        selected = self.profile if profile is None else profile
        return build_creation_review(
            mode=mode,
            user=user or self.user,
            profile_id=selected.pk if selected else None,
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            audience_ids=[self.audience.pk],
            recurring_data=recurring_data,
        )

    def create_single(self, *, token, profile=None, team_ids=None, user=None):
        selected = self.profile if profile is None else profile
        return create_single_service_event(
            cleaned_data=self.single_data(),
            user=user or self.user,
            profile_id=selected.pk if selected else None,
            review_token=token,
            team_ids=team_ids if team_ids is not None else [self.team_a.pk],
            audience_ids=[self.audience.pk],
        )

    def test_create_only_profile_selector_and_compatibility_key_boundary(self):
        create_form = ServiceEventForm(
            language="en", include_profile_selection=True
        )
        ordinary_form = ServiceEventForm(language="en")
        event = ServiceEvent(**self.single_data())
        edit_form = ServiceEventForm(instance=event, language="en")
        self.assertIn("service_profile", create_form.fields)
        self.assertNotIn("service_profile", ordinary_form.fields)
        self.assertNotIn("service_profile", edit_form.fields)
        for form in (create_form, ordinary_form, edit_form):
            self.assertNotIn("service_profile_key", form.fields)

    def test_profile_selector_is_localized_and_active_only(self):
        inactive = ServiceProfile.objects.create(
            key="inactive_profile",
            name="停用配置",
            name_en="Inactive Profile",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            is_active=False,
        )
        form = ServiceEventForm(language="en", include_profile_selection=True)
        choices = list(form.fields["service_profile"].queryset)
        self.assertEqual(choices, [self.profile])
        self.assertEqual(
            form.fields["service_profile"].label_from_instance(self.profile),
            "General Sunday Gathering",
        )
        self.assertNotIn(inactive, choices)

    def test_new_and_recurring_team_choices_are_active_assignable(self):
        single = ServiceEventForm(language="en")
        recurring = RecurringServiceEventForm(language="en")
        expected = {self.team_a.pk, self.team_b.pk}
        self.assertEqual(
            set(single.fields["required_teams"].queryset.values_list("pk", flat=True)),
            expected,
        )
        self.assertEqual(
            set(recurring.fields["required_teams"].queryset.values_list("pk", flat=True)),
            expected,
        )

    def test_edit_choices_union_every_exact_stored_legacy_row(self):
        event = ServiceEvent.objects.create(**self.single_data(), created_by=self.user)
        ServiceEventRequiredTeam.objects.create(
            service_event=event, ministry_team=self.inactive_team
        )
        ServiceEventRequiredTeam.objects.create(
            service_event=event, ministry_team=self.container
        )
        form = ServiceEventForm(instance=event, language="en")
        ids = set(form.fields["required_teams"].queryset.values_list("pk", flat=True))
        self.assertEqual(
            ids,
            {self.team_a.pk, self.team_b.pk, self.container.pk, self.inactive_team.pk},
        )

    def test_compatible_review_orders_defaults_and_preserves_history_as_evidence(self):
        requirement_b = ServiceProfileMinistryRequirement.objects.create(
            service_profile=self.profile,
            ministry_team=self.team_b,
            is_active=True,
            sort_order=10,
        )
        ServiceProfileMinistryRequirement.objects.filter(pk=self.requirement_a.pk).update(
            is_active=False
        )
        review = self.review()
        self.assertEqual(review.default_teams, (self.team_b,))
        self.assertEqual(review.inactive_requirement_count, 1)
        self.assertTrue(review.signed_payload)
        self.assertEqual(requirement_b.sort_order, 10)

    def test_zero_default_profile_review_succeeds(self):
        ServiceProfileMinistryRequirement.objects.filter(
            service_profile=self.profile
        ).update(is_active=False)
        review = self.review()
        self.assertEqual(review.default_teams, ())

    def test_invalid_active_profile_requirement_blocks_review(self):
        MinistryTeam.objects.filter(pk=self.team_a.pk).update(is_active=False)
        with self.assertRaises(ServiceEventCreationError) as caught:
            self.review()
        self.assertEqual(
            caught.exception.failure,
            CreationReviewFailure.INVALID_PROFILE_DEFAULTS,
        )

    def test_inactive_and_type_mismatched_profiles_reject_review(self):
        ServiceProfile.objects.filter(pk=self.profile.pk).update(is_active=False)
        with self.assertRaises(ServiceEventCreationError) as inactive:
            self.review()
        self.assertEqual(
            inactive.exception.failure, CreationReviewFailure.PROFILE_UNAVAILABLE
        )
        ServiceProfile.objects.filter(pk=self.profile.pk).update(
            is_active=True, event_type=ServiceEvent.EVENT_OTHER
        )
        with self.assertRaises(ServiceEventCreationError) as mismatch:
            self.review()
        self.assertEqual(
            mismatch.exception.failure,
            CreationReviewFailure.PROFILE_TYPE_MISMATCH,
        )

    def test_profileless_creation_needs_no_review_and_keeps_blank_identity(self):
        result = self.create_single(token="", profile=False, team_ids=[self.team_b.pk])
        event = result.events[0]
        self.assertIsNone(event.service_profile_id)
        self.assertEqual(event.service_profile_key, "")
        self.assertEqual(event.scheduling_revision, 0)

    def test_selected_profile_final_create_requires_review(self):
        with self.assertRaises(ServiceEventCreationError) as caught:
            self.create_single(token="")
        self.assertEqual(caught.exception.failure, CreationReviewFailure.REVIEW_REQUIRED)
        self.assertEqual(ServiceEvent.objects.count(), 0)

    def test_review_wrong_user_profile_or_mode_rejects(self):
        token = self.review().signed_payload
        with self.assertRaises(ServiceEventCreationError):
            self.create_single(token=token, user=self.other_user)

        other_profile = ServiceProfile.objects.create(
            key="other_sunday",
            name="其他主日配置",
            name_en="Other Sunday Profile",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        with self.assertRaises(ServiceEventCreationError):
            self.create_single(token=token, profile=other_profile)

        recurring_token = self.review(
            mode="recurring", recurring_data=self.recurring_data()
        ).signed_payload
        with self.assertRaises(ServiceEventCreationError):
            self.create_single(token=recurring_token)
        self.assertEqual(ServiceEvent.objects.count(), 0)

    def test_tampered_and_expired_review_reject(self):
        token = self.review().signed_payload
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        with self.assertRaises(ServiceEventCreationError):
            self.create_single(token=tampered)
        with mock.patch(
            "events.service_event_creation.REVIEW_MAX_AGE_SECONDS", -1
        ):
            with self.assertRaises(ServiceEventCreationError):
                self.create_single(token=token)

    def test_profile_and_default_drift_reject_with_zero_write(self):
        token = self.review().signed_payload
        ServiceProfile.objects.filter(pk=self.profile.pk).update(is_active=False)
        with self.assertRaises(ServiceEventCreationError):
            self.create_single(token=token)
        ServiceProfile.objects.filter(pk=self.profile.pk).update(is_active=True)
        self.profile.refresh_from_db()
        token = self.review().signed_payload
        ServiceProfileMinistryRequirement.objects.create(
            service_profile=self.profile,
            ministry_team=self.team_b,
            sort_order=30,
        )
        with self.assertRaises(ServiceEventCreationError):
            self.create_single(token=token)
        self.assertEqual(ServiceEvent.objects.count(), 0)

    def test_team_and_audience_drift_reject_with_zero_write(self):
        token = self.review().signed_payload
        MinistryTeam.objects.filter(pk=self.team_b.pk).update(is_assignable=False)
        with self.assertRaises(ServiceEventCreationError):
            self.create_single(token=token)
        MinistryTeam.objects.filter(pk=self.team_b.pk).update(is_assignable=True)
        token = self.review().signed_payload
        ChurchStructureUnit.objects.filter(pk=self.audience.pk).update(is_active=False)
        with self.assertRaises(ServiceEventCreationError):
            self.create_single(token=token)
        self.assertEqual(ServiceEvent.objects.count(), 0)

    def test_final_explicit_set_may_remove_defaults_or_add_valid_team(self):
        token = self.review().signed_payload
        first = self.create_single(token=token, team_ids=[]).events[0]
        self.assertEqual(first.required_teams.count(), 0)
        token = self.review().signed_payload
        second = self.create_single(
            token=token, team_ids=[self.team_a.pk, self.team_b.pk]
        ).events[0]
        self.assertEqual(
            set(second.required_teams.values_list("pk", flat=True)),
            {self.team_a.pk, self.team_b.pk},
        )

    def test_single_success_writes_exact_profile_teams_audience_revision_zero(self):
        event = self.create_single(token=self.review().signed_payload).events[0]
        self.assertEqual(event.service_profile_id, self.profile.pk)
        self.assertEqual(event.service_profile_key, "")
        pre_drop = build_pre_drop_legacy_key_inventory()
        self.assertEqual(pre_drop["summary"]["fk_only_blank_legacy"], 1)
        self.assertTrue(pre_drop["summary"]["ready_for_column_removal"])
        self.assertEqual(event.scheduling_revision, 0)
        self.assertEqual(
            set(ServiceEventRequiredTeam.objects.values_list("ministry_team_id", flat=True)),
            {self.team_a.pk},
        )
        self.assertEqual(
            set(ServiceEventAudienceScope.objects.values_list("unit_id", flat=True)),
            {self.audience.pk},
        )
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertIsNone(event.rotation_anchor_team_id)

    def test_single_child_failure_rolls_back_parent(self):
        with mock.patch(
            "events.service_event_creation._create_children",
            side_effect=RuntimeError("child failed"),
        ):
            with self.assertRaises(RuntimeError):
                self.create_single(token=self.review().signed_payload)
        self.assertEqual(ServiceEvent.objects.count(), 0)

    def test_single_post_first_write_recompute_failure_rolls_back_parent(self):
        from . import service_event_creation as service

        original = service._review_state
        calls = 0

        def fail_after_insert(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ServiceEventCreationError(
                    CreationReviewFailure.PROFILE_DEFAULTS_CHANGED
                )
            return original(*args, **kwargs)

        token = self.review().signed_payload
        with mock.patch.object(service, "_review_state", side_effect=fail_after_insert):
            with self.assertRaises(ServiceEventCreationError):
                self.create_single(token=token)
        self.assertEqual(ServiceEvent.objects.count(), 0)

    def test_recurring_review_binds_create_and_skip_dates(self):
        duplicate = ServiceEvent.objects.create(
            **self.single_data(start_datetime=timezone.make_aware(timezone.datetime(2030, 1, 6, 10, 0))),
            created_by=self.user,
        )
        review = self.review(
            mode="recurring", recurring_data=self.recurring_data()
        )
        self.assertEqual(review.dates_to_skip, (date(2030, 1, 6),))
        self.assertEqual(
            review.dates_to_create,
            (date(2030, 1, 13), date(2030, 1, 20)),
        )
        self.assertTrue(ServiceEvent.objects.filter(pk=duplicate.pk).exists())

    def test_recurring_writes_same_exact_explicit_state_to_every_event(self):
        data = self.recurring_data()
        review = self.review(mode="recurring", recurring_data=data)
        result = create_recurring_service_events(
            cleaned_data=data,
            user=self.user,
            profile_id=self.profile.pk,
            review_token=review.signed_payload,
            team_ids=[self.team_b.pk],
            audience_ids=[self.audience.pk],
        )
        self.assertEqual(len(result.events), 3)
        for event in result.events:
            self.assertEqual(event.service_profile_id, self.profile.pk)
            self.assertEqual(event.service_profile_key, "")
            self.assertEqual(event.scheduling_revision, 0)
            self.assertEqual(
                set(event.required_teams.values_list("pk", flat=True)),
                {self.team_b.pk},
            )
            self.assertEqual(
                set(event.get_audience_scope_units().values_list("pk", flat=True)),
                {self.audience.pk},
            )

    def test_recurring_input_or_duplicate_drift_rejects_complete_batch(self):
        data = self.recurring_data()
        review = self.review(mode="recurring", recurring_data=data)
        changed = {**data, "end_date": date(2030, 1, 27)}
        with self.assertRaises(ServiceEventCreationError):
            create_recurring_service_events(
                cleaned_data=changed,
                user=self.user,
                profile_id=self.profile.pk,
                review_token=review.signed_payload,
                team_ids=[],
                audience_ids=[self.audience.pk],
            )
        ServiceEvent.objects.create(**self.single_data(), created_by=self.user)
        with self.assertRaises(ServiceEventCreationError):
            create_recurring_service_events(
                cleaned_data=data,
                user=self.user,
                profile_id=self.profile.pk,
                review_token=review.signed_payload,
                team_ids=[],
                audience_ids=[self.audience.pk],
            )
        self.assertEqual(ServiceEvent.objects.count(), 1)

    def test_recurring_later_child_failure_rolls_back_complete_batch(self):
        data = self.recurring_data()
        review = self.review(mode="recurring", recurring_data=data)
        original = ServiceEventAudienceScope.objects.create
        calls = 0

        def fail_later(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("later child failed")
            return original(*args, **kwargs)

        with mock.patch.object(
            ServiceEventAudienceScope.objects, "create", side_effect=fail_later
        ):
            with self.assertRaises(RuntimeError):
                create_recurring_service_events(
                    cleaned_data=data,
                    user=self.user,
                    profile_id=self.profile.pk,
                    review_token=review.signed_payload,
                    team_ids=[],
                    audience_ids=[self.audience.pk],
                )
        self.assertEqual(ServiceEvent.objects.count(), 0)
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 0)

    def test_all_skip_review_is_accurate_zero_write_and_preserves_existing(self):
        data = self.recurring_data()
        for event_date in (date(2030, 1, 6), date(2030, 1, 13), date(2030, 1, 20)):
            ServiceEvent.objects.create(
                **self.single_data(
                    start_datetime=timezone.make_aware(
                        timezone.datetime.combine(event_date, time(10, 0))
                    ),
                    end_datetime=timezone.make_aware(
                        timezone.datetime.combine(event_date, time(11, 30))
                    ),
                ),
                created_by=self.user,
            )
        review = self.review(mode="recurring", recurring_data=data)
        before_ids = set(ServiceEvent.objects.values_list("pk", flat=True))
        result = create_recurring_service_events(
            cleaned_data=data,
            user=self.user,
            profile_id=self.profile.pk,
            review_token=review.signed_payload,
            team_ids=[],
            audience_ids=[self.audience.pk],
        )
        self.assertEqual(result.events, ())
        self.assertEqual(len(result.dates_to_skip), 3)
        self.assertEqual(
            set(ServiceEvent.objects.values_list("pk", flat=True)), before_ids
        )

    def test_signed_payload_does_not_expose_compatibility_key_in_form(self):
        review = self.review()
        payload = signing.loads(
            review.signed_payload,
            salt="events.service-event-profile-creation-review.v1",
        )
        self.assertEqual(payload["contract"], "SERVICE_EVENT_PROFILE_CREATION_REVIEW_V1")
        form = ServiceEventForm(language="en", include_profile_selection=True)
        self.assertNotIn("service_profile_key", form.fields)

    def test_single_route_reviews_merges_defaults_and_renders_bounded_copy(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("create_service_event"),
            self.single_post_data(review_profile="1"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["profile_review"])
        form = response.context["form"]
        self.assertEqual(
            set(form["required_teams"].value()),
            {str(self.team_a.pk), str(self.team_b.pk)},
        )
        self.assertTrue(form["review_token"].value())
        self.assertContains(response, "not assignments or live inheritance")
        self.assertContains(response, "General Sunday Gathering")

    def test_single_route_selected_profile_without_token_fails_closed(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("create_service_event"),
            self.single_post_data(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review the selected Service Profile")
        self.assertEqual(ServiceEvent.objects.count(), 0)

    def test_single_route_review_then_deliberate_final_adjustment_creates(self):
        self.client.force_login(self.user)
        preview = self.client.post(
            reverse("create_service_event"),
            self.single_post_data(review_profile="1"),
        )
        token = preview.context["form"]["review_token"].value()
        response = self.client.post(
            reverse("create_service_event"),
            self.single_post_data(
                review_token=token,
                required_teams=[str(self.team_b.pk)],
            ),
        )
        self.assertEqual(response.status_code, 302)
        event = ServiceEvent.objects.get()
        self.assertEqual(
            set(event.required_teams.values_list("pk", flat=True)),
            {self.team_b.pk},
        )

    def test_recurring_route_preview_then_create_uses_exact_review(self):
        self.client.force_login(self.user)
        preview = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(preview="1"),
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.context["preview"]["total_count"], 3)
        self.assertContains(preview, "Initial Required Ministry Team suggestions")
        form = preview.context["form"]
        self.assertEqual(
            set(form["required_teams"].value()),
            {str(self.team_a.pk), str(self.team_b.pk)},
        )
        token = form["review_token"].value()
        created = self.client.post(
            reverse("create_recurring_service_events"),
            self.recurring_post_data(
                create="1",
                review_token=token,
                required_teams=[str(self.team_a.pk)],
            ),
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(ServiceEvent.objects.count(), 3)
        for event in ServiceEvent.objects.all():
            self.assertEqual(
                set(event.required_teams.values_list("pk", flat=True)),
                {self.team_a.pk},
            )

    def test_edit_route_does_not_expose_profile_and_preserves_legacy_team(self):
        event = ServiceEvent.objects.create(**self.single_data(), created_by=self.user)
        ServiceEventAudienceScope.objects.create(
            service_event=event, unit=self.audience
        )
        ServiceEventRequiredTeam.objects.create(
            service_event=event, ministry_team=self.inactive_team
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("edit_service_event", args=[event.pk]),
            self.single_post_data(
                service_profile=str(self.profile.pk),
                service_profile_key="forged",
                required_teams=[str(self.inactive_team.pk)],
            ),
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertIsNone(event.service_profile_id)
        self.assertEqual(event.service_profile_key, "")
        self.assertEqual(
            set(event.required_teams.values_list("pk", flat=True)),
            {self.inactive_team.pk},
        )


class FileBackedSQLiteServiceEventCreationTests(unittest.TestCase):
    """Two real SQLite connections exercise the 7C first-write boundary."""

    competing_alias = "service_event_creation_competing"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        handle = tempfile.NamedTemporaryFile(
            prefix="service-event-creation-", suffix=".sqlite3", delete=False
        )
        cls.database_path = handle.name
        handle.close()
        cls.original_default_config = copy.deepcopy(connections.databases["default"])
        connections["default"].close()
        if hasattr(connections._connections, "default"):
            delattr(connections._connections, "default")
        file_config = copy.deepcopy(cls.original_default_config)
        file_config["NAME"] = cls.database_path
        file_config["OPTIONS"] = {
            **file_config.get("OPTIONS", {}),
            "timeout": 0.1,
        }
        file_config["TEST"] = {"NAME": None}
        connections.databases["default"] = file_config
        call_command("migrate", database="default", interactive=False, verbosity=0)
        competing = copy.deepcopy(file_config)
        competing["TEST"] = {"NAME": None}
        connections.databases[cls.competing_alias] = competing
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
        call_command("flush", database="default", interactive=False, verbosity=0)
        self.user = User.objects.create_user(
            username="sqlite_creator", password="testpass123", is_staff=True
        )
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="ROOT",
            name="教会",
            name_en="Church",
        )
        self.audience = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="GENERAL",
            name="一般事工",
            name_en="General Ministry",
        )
        self.team = MinistryTeam.objects.create(
            name="接待团队",
            name_en="Welcome Team",
            team_key="welcome",
            is_active=True,
            is_assignable=True,
        )
        self.profile = ServiceProfile.objects.create(
            key="general_sunday",
            name="一般主日聚会",
            name_en="General Sunday Gathering",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        self.requirement = ServiceProfileMinistryRequirement.objects.create(
            service_profile=self.profile,
            ministry_team=self.team,
            sort_order=10,
        )

    def single_data(self):
        return {
            "title": "一般主日聚会",
            "title_en": "General Sunday Gathering",
            "description": "",
            "description_en": "",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": timezone.make_aware(
                timezone.datetime(2030, 1, 6, 10, 0)
            ),
            "end_datetime": timezone.make_aware(
                timezone.datetime(2030, 1, 6, 11, 30)
            ),
            "location": "Main Hall",
            "meeting_link": "",
            "status": ServiceEvent.STATUS_PUBLISHED,
        }

    def recurring_data(self):
        return {
            "title": "一般主日聚会",
            "title_en": "General Sunday Gathering",
            "description": "",
            "description_en": "",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_date": date(2030, 1, 6),
            "end_date": date(2030, 1, 13),
            "weekday": "6",
            "start_time": time(10, 0),
            "end_time": time(11, 30),
            "location": "Main Hall",
            "meeting_link": "",
            "status": ServiceEvent.STATUS_PUBLISHED,
        }

    def review(self, mode="single"):
        return build_creation_review(
            mode=mode,
            user=self.user,
            profile_id=self.profile.pk,
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            audience_ids=[self.audience.pk],
            recurring_data=self.recurring_data() if mode == "recurring" else None,
        )

    def test_configuration_writer_wins_before_insert_and_create_is_stale(self):
        token = self.review().signed_payload
        ServiceProfileMinistryRequirement.objects.using(self.competing_alias).filter(
            pk=self.requirement.pk
        ).update(sort_order=20)
        with self.assertRaises(ServiceEventCreationError):
            create_single_service_event(
                cleaned_data=self.single_data(),
                user=self.user,
                profile_id=self.profile.pk,
                review_token=token,
                team_ids=[self.team.pk],
                audience_ids=[self.audience.pk],
            )
        self.assertEqual(ServiceEvent.objects.count(), 0)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 0)

    def test_event_insert_wins_and_competing_configuration_write_is_busy(self):
        from . import service_event_creation as service

        token = self.review().signed_payload
        original = service._review_state
        calls = 0
        competing_busy = []

        def compete_after_insert(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                try:
                    ServiceProfileMinistryRequirement.objects.using(
                        self.competing_alias
                    ).filter(pk=self.requirement.pk).update(sort_order=30)
                except OperationalError:
                    competing_busy.append(True)
            return original(*args, **kwargs)


        with mock.patch.object(service, "_review_state", side_effect=compete_after_insert):
            result = create_single_service_event(
                cleaned_data=self.single_data(),
                user=self.user,
                profile_id=self.profile.pk,
                review_token=token,
                team_ids=[self.team.pk],
                audience_ids=[self.audience.pk],
            )
        self.assertEqual(competing_busy, [True])
        self.assertEqual(len(result.events), 1)
        self.assertEqual(result.events[0].scheduling_revision, 0)

        ServiceProfileMinistryRequirement.objects.using(self.competing_alias).filter(
            pk=self.requirement.pk
        ).update(sort_order=30)
        with self.assertRaises(ServiceEventCreationError):
            create_single_service_event(
                cleaned_data=self.single_data(),
                user=self.user,
                profile_id=self.profile.pk,
                review_token=token,
                team_ids=[self.team.pk],
                audience_ids=[self.audience.pk],
            )

    def test_recurring_duplicate_writer_wins_and_no_partial_batch_survives(self):
        token = self.review(mode="recurring").signed_payload
        ServiceEvent.objects.using(self.competing_alias).create(
            **self.single_data(), created_by_id=self.user.pk
        )
        with self.assertRaises(ServiceEventCreationError) as caught:
            create_recurring_service_events(
                cleaned_data=self.recurring_data(),
                user=self.user,
                profile_id=self.profile.pk,
                review_token=token,
                team_ids=[self.team.pk],
                audience_ids=[self.audience.pk],
            )
        self.assertEqual(
            caught.exception.failure,
            CreationReviewFailure.RECURRING_SET_CHANGED,
        )
        self.assertEqual(ServiceEvent.objects.count(), 1)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 0)
