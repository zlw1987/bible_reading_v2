from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from ministry.models import (
    MinistryTeam,
    MinistryTeamRoleAssignment,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from notifications.models import Notification

from .admin import ServiceEventAdmin
from .forms import RecurringServiceEventForm, ServiceEventForm
from .models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventPlannerAssignment,
    ServiceEventRequiredTeam,
    ServiceProfile,
)


User = get_user_model()


class ServiceEventProfileKeyTests(TestCase):
    def event_values(self, **overrides):
        values = {
            "title": "Profile key test",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": timezone.now() + timezone.timedelta(days=7),
            "status": ServiceEvent.STATUS_PUBLISHED,
        }
        values.update(overrides)
        return values

    def test_new_event_defaults_to_empty_profile_key(self):
        field = ServiceEvent._meta.get_field("service_profile_key")
        event = ServiceEvent.objects.create(**self.event_values())

        self.assertEqual(field.max_length, 64)
        self.assertTrue(field.blank)
        self.assertEqual(field.default, "")
        self.assertFalse(field.unique)
        self.assertFalse(field.db_index)
        self.assertEqual(event.service_profile_key, "")
        self.assertEqual(
            ServiceEvent.objects.values_list("service_profile_key", flat=True).get(
                pk=event.pk
            ),
            "",
        )

    def test_valid_machine_key_is_accepted(self):
        event = ServiceEvent.objects.create(
            **self.event_values(service_profile_key="bethany_0930.cm-v1")
        )

        self.assertEqual(event.service_profile_key, "bethany_0930.cm-v1")

    def test_whitespace_uppercase_and_unsafe_characters_are_rejected(self):
        invalid_values = (
            "bethany 0930 cm",
            "Bethany_0930_cm",
            "bethany/0930/cm",
            "bethany_上午",
        )

        for value in invalid_values:
            with self.subTest(value=value):
                event = ServiceEvent(
                    **self.event_values(service_profile_key=value)
                )
                with self.assertRaises(ValidationError) as raised:
                    event.full_clean()
                self.assertEqual(
                    raised.exception.error_dict["service_profile_key"][0].code,
                    "invalid_service_profile_key",
                )

    def test_duplicate_profile_keys_across_events_are_valid(self):
        first = ServiceEvent.objects.create(
            **self.event_values(service_profile_key="bethany_0930_cm")
        )
        second = ServiceEvent.objects.create(
            **self.event_values(
                title="Next Sunday",
                start_datetime=first.start_datetime + timezone.timedelta(days=7),
                service_profile_key="bethany_0930_cm",
            )
        )

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(
            ServiceEvent.objects.filter(
                service_profile_key="bethany_0930_cm"
            ).count(),
            2,
        )

    def test_ordinary_and_recurring_forms_do_not_expose_profile_key(self):
        self.assertNotIn("service_profile_key", ServiceEventForm().fields)
        self.assertNotIn("service_profile_key", RecurringServiceEventForm().fields)

    def test_admin_form_selects_fk_and_persists_readonly_compatibility_pair(self):
        event = ServiceEvent.objects.create(**self.event_values())
        profile = ServiceProfile.objects.create(
            key="bethany_0930_cm",
            name="Bethany 09:30 Chinese",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
            name_en="Whole Church",
        )
        scope = ServiceEventAudienceScope.objects.create(
            service_event=event,
            unit=root,
        )
        superuser = User.objects.create_superuser(
            username="profile_admin",
            email="profile-admin@example.com",
            password="testpass123",
        )
        request = RequestFactory().get("/admin/events/serviceevent/")
        request.user = superuser
        form_class = ServiceEventAdmin(ServiceEvent, admin.site).get_form(
            request,
            obj=event,
        )

        self.assertNotIn("service_profile_key", form_class.base_fields)
        self.assertIn("service_profile", form_class.base_fields)
        self.assertIn(
            "compatibility key below is read-only",
            form_class.base_fields["service_profile"].help_text,
        )
        self.client.force_login(superuser)
        response = self.client.post(
            reverse("admin:events_serviceevent_change", args=[event.pk]),
            {
                "title": "Profile plus title update",
                "title_en": event.title_en,
                "description": event.description,
                "description_en": event.description_en,
                "event_type": event.event_type,
                "service_profile": str(profile.pk),
                "start_datetime_0": timezone.localtime(
                    event.start_datetime
                ).strftime("%Y-%m-%d"),
                "start_datetime_1": timezone.localtime(
                    event.start_datetime
                ).strftime("%H:%M:%S"),
                "end_datetime_0": "",
                "end_datetime_1": "",
                "location": event.location,
                "meeting_link": event.meeting_link,
                "host_language_unit": "",
                "status": event.status,
                "created_by": "",
                "required_team_links-TOTAL_FORMS": "0",
                "required_team_links-INITIAL_FORMS": "0",
                "required_team_links-MIN_NUM_FORMS": "0",
                "required_team_links-MAX_NUM_FORMS": "1000",
                "audience_scope_links-TOTAL_FORMS": "1",
                "audience_scope_links-INITIAL_FORMS": "1",
                "audience_scope_links-MIN_NUM_FORMS": "0",
                "audience_scope_links-MAX_NUM_FORMS": "1000",
                "audience_scope_links-0-id": str(scope.pk),
                "audience_scope_links-0-service_event": str(event.pk),
                "audience_scope_links-0-unit": str(root.pk),
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.service_profile_key, "bethany_0930_cm")
        self.assertEqual(event.service_profile_id, profile.pk)
        self.assertEqual(event.title, "Profile plus title update")
        self.assertEqual(event.scheduling_revision, 1)
        self.assertTrue(
            ServiceEventAudienceScope.objects.filter(pk=scope.pk).exists()
        )
        self.assertEqual(LogEntry.objects.filter(object_id=str(event.pk)).count(), 1)

    def test_profile_change_advances_revision_and_failed_change_rolls_back(self):
        event = ServiceEvent.objects.create(**self.event_values())

        event.service_profile_key = "bethany_0930_cm"
        event.save(update_fields=["service_profile_key", "updated_at"])
        event.refresh_from_db()
        self.assertEqual(event.service_profile_key, "bethany_0930_cm")
        self.assertEqual(event.scheduling_revision, 1)

        event.service_profile_key = "invalid profile"
        with self.assertRaises(ValidationError):
            event.save(update_fields=["service_profile_key", "updated_at"])

        event.refresh_from_db()
        self.assertEqual(event.service_profile_key, "bethany_0930_cm")
        self.assertEqual(event.scheduling_revision, 1)

    def test_profile_change_has_no_cross_domain_side_effects_or_callbacks(self):
        event = ServiceEvent.objects.create(**self.event_values())
        tracked_models = (
            ServiceEvent,
            ServiceEventAudienceScope,
            ServiceEventRequiredTeam,
            ServiceEventPlannerAssignment,
            MinistryTeam,
            TeamAssignment,
            TeamAssignmentMember,
            TeamMembership,
            MinistryTeamRoleAssignment,
            ChurchStructureUnit,
            ChurchStructureMembership,
            LogEntry,
            Notification,
        )
        before = {model: model.objects.count() for model in tracked_models}

        event.service_profile_key = "bethany_0930_cm"
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            event.save(update_fields=["service_profile_key", "updated_at"])

        self.assertEqual(callbacks, [])
        self.assertEqual(
            {model: model.objects.count() for model in tracked_models},
            before,
        )
        event.refresh_from_db()
        self.assertEqual(event.location, "")
        self.assertIsNone(event.host_language_unit_id)
        self.assertIsNone(event.rotation_anchor_team_id)
        self.assertEqual(event.status, ServiceEvent.STATUS_PUBLISHED)

    def test_profile_key_grants_no_visibility_or_management_permission(self):
        user = User.objects.create_user(
            username="ordinary_profile_viewer",
            password="testpass123",
        )
        event = ServiceEvent.objects.create(
            **self.event_values(service_profile_key="bethany_0930_cm")
        )

        self.assertFalse(event.can_be_seen_by(user))
        self.assertFalse(event.can_be_managed_by(user))
