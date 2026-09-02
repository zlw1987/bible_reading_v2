from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit

from .admin import ServiceEventAdmin, ServiceProfileAdmin
from .forms import RecurringServiceEventForm, ServiceEventForm
from .models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceProfile,
)


User = get_user_model()


def profile_values(**overrides):
    values = {
        "key": "sunday.main",
        "name": "Main Sunday Service",
        "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
    }
    values.update(overrides)
    return values


def event_values(**overrides):
    values = {
        "title": "Profile relation test",
        "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
        "start_datetime": timezone.now() + timezone.timedelta(days=7),
        "status": ServiceEvent.STATUS_PUBLISHED,
    }
    values.update(overrides)
    return values


class ServiceProfileModelTests(TestCase):
    def test_frozen_field_contract_and_defaults(self):
        profile = ServiceProfile.objects.create(**profile_values())
        fields = {field.name: field for field in ServiceProfile._meta.fields}

        self.assertEqual(
            set(fields),
            {
                "id",
                "key",
                "name",
                "name_en",
                "description",
                "description_en",
                "event_type",
                "is_active",
                "created_at",
                "updated_at",
            },
        )
        self.assertEqual(fields["key"].max_length, 64)
        self.assertTrue(fields["key"].unique)
        self.assertEqual(fields["name"].max_length, 160)
        self.assertEqual(fields["name_en"].default, "")
        self.assertEqual(fields["description"].default, "")
        self.assertEqual(fields["description_en"].default, "")
        self.assertEqual(fields["event_type"].max_length, 40)
        self.assertEqual(
            list(fields["event_type"].choices),
            ServiceEvent.EVENT_TYPE_CHOICES,
        )
        self.assertTrue(profile.is_active)
        self.assertIsNotNone(profile.created_at)
        self.assertIsNotNone(profile.updated_at)

    def test_valid_key_is_trimmed_and_lowercased(self):
        profile = ServiceProfile.objects.create(
            **profile_values(key=" Sunday_Main ")
        )

        self.assertEqual(profile.key, "sunday_main")
        self.assertEqual(
            ServiceProfile.objects.values_list("key", flat=True).get(pk=profile.pk),
            "sunday_main",
        )

    def test_dot_underscore_and_hyphen_are_valid(self):
        profile = ServiceProfile.objects.create(
            **profile_values(key="sunday.main_11-v1")
        )

        self.assertEqual(profile.key, "sunday.main_11-v1")

    def test_blank_whitespace_unicode_slash_at_and_space_are_rejected(self):
        invalid_values = ("", "   ", "主日", "profile/key", "profile@main", "Sunday Main")

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    ServiceProfile.objects.create(**profile_values(key=value))

    def test_normalized_duplicate_is_rejected_with_validation_error(self):
        ServiceProfile.objects.create(**profile_values(key=" Sunday.Main "))

        with self.assertRaises(ValidationError) as raised:
            ServiceProfile.objects.create(
                **profile_values(key="sunday.main", name="Duplicate")
            )

        self.assertIn("key", raised.exception.error_dict)

    def test_required_name_and_valid_event_type_are_enforced(self):
        with self.assertRaises(ValidationError) as missing_name:
            ServiceProfile.objects.create(**profile_values(name=""))
        self.assertIn("name", missing_name.exception.error_dict)

        with self.assertRaises(ValidationError) as invalid_type:
            ServiceProfile.objects.create(**profile_values(event_type="unsupported"))
        self.assertIn("event_type", invalid_type.exception.error_dict)


class ServiceProfileImmutabilityTests(TestCase):
    def setUp(self):
        self.profile = ServiceProfile.objects.create(**profile_values())

    def test_unreferenced_key_and_event_type_may_change(self):
        self.profile.key = "weekday.study"
        self.profile.event_type = ServiceEvent.EVENT_BIBLE_STUDY
        self.profile.save()

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.key, "weekday.study")
        self.assertEqual(self.profile.event_type, ServiceEvent.EVENT_BIBLE_STUDY)

    def test_referenced_key_and_event_type_are_rejected(self):
        ServiceEvent.objects.create(
            **event_values(
                service_profile_key=self.profile.key,
                service_profile=self.profile,
            )
        )

        self.profile.key = "sunday.corrected"
        with self.assertRaises(ValidationError) as key_error:
            self.profile.save()
        self.assertEqual(
            key_error.exception.error_dict["key"][0].code,
            "referenced_service_profile_key_immutable",
        )

        self.profile.refresh_from_db()
        self.profile.event_type = ServiceEvent.EVENT_BIBLE_STUDY
        with self.assertRaises(ValidationError) as type_error:
            self.profile.save()
        self.assertEqual(
            type_error.exception.error_dict["event_type"][0].code,
            "referenced_service_profile_event_type_immutable",
        )

    def test_referenced_labels_descriptions_and_active_state_remain_editable(self):
        event = ServiceEvent.objects.create(
            **event_values(
                service_profile_key=self.profile.key,
                service_profile=self.profile,
            )
        )
        before_revision = event.scheduling_revision

        self.profile.name = "Updated local label"
        self.profile.name_en = "Updated English label"
        self.profile.description = "Updated description"
        self.profile.description_en = "Updated English description"
        self.profile.is_active = False
        self.profile.save()

        self.profile.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(self.profile.name, "Updated local label")
        self.assertEqual(self.profile.name_en, "Updated English label")
        self.assertEqual(self.profile.description, "Updated description")
        self.assertEqual(self.profile.description_en, "Updated English description")
        self.assertFalse(self.profile.is_active)
        self.assertEqual(event.service_profile_id, self.profile.pk)
        self.assertEqual(event.scheduling_revision, before_revision)
        event.full_clean()

    def test_referenced_profile_delete_is_protected(self):
        ServiceEvent.objects.create(
            **event_values(
                service_profile_key=self.profile.key,
                service_profile=self.profile,
            )
        )

        with self.assertRaises(ProtectedError):
            self.profile.delete()

        self.assertTrue(ServiceProfile.objects.filter(pk=self.profile.pk).exists())


class ServiceEventProfileRelationTests(TestCase):
    def setUp(self):
        self.profile = ServiceProfile.objects.create(**profile_values())

    def test_relation_contract_defaults_null_and_legacy_only_remains_valid(self):
        field = ServiceEvent._meta.get_field("service_profile")
        event = ServiceEvent.objects.create(
            **event_values(service_profile_key="legacy.profile")
        )

        self.assertTrue(field.null)
        self.assertTrue(field.blank)
        self.assertEqual(field.remote_field.model, ServiceProfile)
        self.assertEqual(field.remote_field.related_name, "service_events")
        self.assertIs(field.remote_field.on_delete, models.PROTECT)
        self.assertEqual(event.service_profile_key, "legacy.profile")
        self.assertIsNone(event.service_profile_id)
        event.full_clean()

    def test_matching_key_and_event_type_are_valid(self):
        event = ServiceEvent.objects.create(
            **event_values(
                service_profile_key=self.profile.key,
                service_profile=self.profile,
            )
        )

        self.assertEqual(event.service_profile_id, self.profile.pk)
        self.assertEqual(event.scheduling_revision, 0)

    def test_mismatched_legacy_key_is_rejected_without_auto_copy(self):
        with self.assertRaises(ValidationError) as raised:
            ServiceEvent.objects.create(
                **event_values(
                    service_profile_key="weekday.study",
                    service_profile=self.profile,
                )
            )

        self.assertIn("service_profile_key", raised.exception.error_dict)
        self.assertFalse(ServiceEvent.objects.exists())

    def test_mismatched_event_type_is_rejected(self):
        with self.assertRaises(ValidationError) as raised:
            ServiceEvent.objects.create(
                **event_values(
                    event_type=ServiceEvent.EVENT_BIBLE_STUDY,
                    service_profile_key=self.profile.key,
                    service_profile=self.profile,
                )
            )

        self.assertIn("event_type", raised.exception.error_dict)

    def test_blank_legacy_key_with_profile_is_rejected_without_inference(self):
        with self.assertRaises(ValidationError) as raised:
            ServiceEvent.objects.create(
                **event_values(service_profile_key="", service_profile=self.profile)
            )

        self.assertIn("service_profile_key", raised.exception.error_dict)
        self.assertEqual(self.profile.service_events.count(), 0)

    def test_inactive_profile_cannot_be_newly_assigned(self):
        self.profile.is_active = False
        self.profile.save()

        with self.assertRaises(ValidationError) as raised:
            ServiceEvent.objects.create(
                **event_values(
                    service_profile_key=self.profile.key,
                    service_profile=self.profile,
                )
            )

        self.assertIn("service_profile", raised.exception.error_dict)

    def test_existing_relation_survives_profile_deactivation(self):
        event = ServiceEvent.objects.create(
            **event_values(
                service_profile_key=self.profile.key,
                service_profile=self.profile,
            )
        )
        self.profile.is_active = False
        self.profile.save()

        event.refresh_from_db()
        event.full_clean()
        self.assertEqual(event.service_profile_id, self.profile.pk)
        self.assertFalse(event.service_profile.is_active)


class ServiceEventProfileRevisionTests(TestCase):
    def setUp(self):
        self.event = ServiceEvent.objects.create(**event_values())
        self.profile_a = ServiceProfile.objects.create(**profile_values())
        self.profile_b = ServiceProfile.objects.create(
            **profile_values(
                key="weekday.study",
                name="Weekday Study",
                event_type=ServiceEvent.EVENT_BIBLE_STUDY,
            )
        )

    def test_null_to_profile_advances_existing_revision_once(self):
        self.event.service_profile_key = self.profile_a.key
        self.event.service_profile = self.profile_a
        self.event.save(
            update_fields=["service_profile_key", "service_profile", "updated_at"]
        )

        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, 1)

    def test_profile_to_profile_with_matching_identity_advances_once(self):
        self.event.service_profile_key = self.profile_a.key
        self.event.service_profile = self.profile_a
        self.event.save()
        self.event.refresh_from_db()
        before = self.event.scheduling_revision

        self.event.service_profile_key = self.profile_b.key
        self.event.service_profile = self.profile_b
        self.event.event_type = self.profile_b.event_type
        self.event.save()

        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, before + 1)
        self.assertEqual(self.event.service_profile_id, self.profile_b.pk)

    def test_unchanged_fk_does_not_add_a_second_revision_advance(self):
        self.event.service_profile_key = self.profile_a.key
        self.event.service_profile = self.profile_a
        self.event.save()
        self.event.refresh_from_db()
        before = self.event.scheduling_revision

        self.event.title = "Ordinary event edit"
        self.event.save(update_fields=["title", "updated_at"])

        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, before + 1)

    def test_profile_label_and_active_edits_do_not_advance_event_revision(self):
        self.event.service_profile_key = self.profile_a.key
        self.event.service_profile = self.profile_a
        self.event.save()
        self.event.refresh_from_db()
        before = self.event.scheduling_revision

        self.profile_a.name = "Renamed profile"
        self.profile_a.save()
        self.profile_a.is_active = False
        self.profile_a.save()

        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, before)


class ServiceProfileAdminAndFormTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="service_profile_admin",
            email="profile-admin@example.com",
            password="testpass123",
        )
        self.request = RequestFactory().get("/admin/events/serviceprofile/")
        self.request.user = self.superuser

    def test_ordinary_and_recurring_forms_expose_no_profile_identity(self):
        ordinary_fields = ServiceEventForm().fields
        recurring_fields = RecurringServiceEventForm().fields

        self.assertNotIn("service_profile", ordinary_fields)
        self.assertNotIn("service_profile_key", ordinary_fields)
        self.assertNotIn("service_profile", recurring_fields)
        self.assertNotIn("service_profile_key", recurring_fields)

    def test_service_profile_admin_allows_normalized_creation(self):
        model_admin = ServiceProfileAdmin(ServiceProfile, admin.site)
        form_class = model_admin.get_form(self.request)
        form = form_class(
            data={
                "key": " Sunday.Main-11 ",
                "name": "Sunday Main",
                "name_en": "Sunday Main",
                "description": "Local description",
                "description_en": "English description",
                "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
                "is_active": "on",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        profile = form.save()
        self.assertEqual(profile.key, "sunday.main-11")

    def test_profile_admin_readonly_contract_changes_only_after_reference(self):
        profile = ServiceProfile.objects.create(**profile_values())
        model_admin = ServiceProfileAdmin(ServiceProfile, admin.site)

        unreferenced = model_admin.get_readonly_fields(self.request, profile)
        self.assertNotIn("key", unreferenced)
        self.assertNotIn("event_type", unreferenced)

        ServiceEvent.objects.create(
            **event_values(
                service_profile_key=profile.key,
                service_profile=profile,
            )
        )
        referenced = model_admin.get_readonly_fields(self.request, profile)
        self.assertIn("key", referenced)
        self.assertIn("event_type", referenced)
        self.assertNotIn("name", referenced)
        self.assertNotIn("name_en", referenced)
        self.assertNotIn("description", referenced)
        self.assertNotIn("description_en", referenced)
        self.assertNotIn("is_active", referenced)

    def test_profile_admin_can_correct_unreferenced_key_and_event_type(self):
        profile = ServiceProfile.objects.create(**profile_values())
        model_admin = ServiceProfileAdmin(ServiceProfile, admin.site)
        form_class = model_admin.get_form(self.request, obj=profile)
        form = form_class(
            data={
                "key": " Weekday.Study ",
                "name": profile.name,
                "name_en": profile.name_en,
                "description": profile.description,
                "description_en": profile.description_en,
                "event_type": ServiceEvent.EVENT_BIBLE_STUDY,
                "is_active": "on",
            },
            instance=profile,
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.key, "weekday.study")
        self.assertEqual(saved.event_type, ServiceEvent.EVENT_BIBLE_STUDY)

    def test_service_event_admin_keeps_fk_readonly_and_legacy_key_editable(self):
        profile = ServiceProfile.objects.create(**profile_values())
        event = ServiceEvent.objects.create(
            **event_values(
                service_profile_key=profile.key,
                service_profile=profile,
            )
        )
        model_admin = ServiceEventAdmin(ServiceEvent, admin.site)
        form_class = model_admin.get_form(self.request, obj=event)

        self.assertIn("service_profile", model_admin.get_readonly_fields(self.request, event))
        self.assertNotIn("service_profile", form_class.base_fields)
        self.assertIn("service_profile_key", form_class.base_fields)

    def test_service_event_admin_rejects_legacy_key_drift(self):
        profile = ServiceProfile.objects.create(**profile_values())
        event = ServiceEvent.objects.create(
            **event_values(
                service_profile_key=profile.key,
                service_profile=profile,
            )
        )
        form_class = ServiceEventAdmin(ServiceEvent, admin.site).get_form(
            self.request,
            obj=event,
        )
        local_start = timezone.localtime(event.start_datetime)
        form = form_class(
            data={
                "title": event.title,
                "title_en": event.title_en,
                "description": event.description,
                "description_en": event.description_en,
                "event_type": event.event_type,
                "service_profile_key": "weekday.study",
                "start_datetime_0": local_start.strftime("%Y-%m-%d"),
                "start_datetime_1": local_start.strftime("%H:%M:%S"),
                "end_datetime_0": "",
                "end_datetime_1": "",
                "location": event.location,
                "meeting_link": event.meeting_link,
                "host_language_unit": "",
                "status": event.status,
                "created_by": "",
            },
            instance=event,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("service_profile_key", form.errors)

    def test_member_detail_does_not_expose_profile_technical_identity(self):
        profile = ServiceProfile.objects.create(
            **profile_values(
                key="sunday.hidden-profile",
                name="Hidden technical profile label",
            )
        )
        event = ServiceEvent.objects.create(
            **event_values(
                service_profile_key=profile.key,
                service_profile=profile,
            )
        )
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
            name_en="Whole Church",
        )
        ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)
        member = User.objects.create_user(
            username="profile_member",
            password="testpass123",
        )
        ChurchStructureMembership.objects.create(
            user=member,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        self.client.force_login(member)

        response = self.client.get(reverse("service_event_detail", args=[event.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, profile.key)
        self.assertNotContains(response, profile.name)
