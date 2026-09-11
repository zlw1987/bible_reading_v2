from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase
from django.utils import timezone

from .admin import ServiceEventAdmin, ServiceProfileAdmin
from .models import ServiceEvent, ServiceProfile


User = get_user_model()


def profile_values(**overrides):
    values = {
        "key": "sunday.main", "name": "Main Sunday",
        "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
    }
    values.update(overrides)
    return values


def event_values(**overrides):
    values = {
        "title": "Profile relation", "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
        "start_datetime": timezone.now() + timedelta(days=7),
    }
    values.update(overrides)
    return values


class ServiceProfileModelTests(TestCase):
    def setUp(self):
        self.profile = ServiceProfile.objects.create(**profile_values())

    def test_profile_key_is_canonical_and_invalid_keys_rejected(self):
        self.profile.key = " Sunday_Main "
        self.profile.save()
        self.assertEqual(self.profile.key, "sunday_main")
        with self.assertRaises(ValidationError):
            ServiceProfile.objects.create(**profile_values(key="not a key"))

    def test_fk_contract_is_optional_and_protected(self):
        field = ServiceEvent._meta.get_field("service_profile")
        self.assertTrue(field.null)
        self.assertTrue(field.blank)
        self.assertIs(field.remote_field.on_delete, models.PROTECT)
        event = ServiceEvent.objects.create(**event_values(service_profile=self.profile))
        with self.assertRaises(ProtectedError):
            self.profile.delete()
        self.assertTrue(ServiceEvent.objects.filter(pk=event.pk).exists())

    def test_event_profile_type_mismatch_is_rejected(self):
        with self.assertRaises(ValidationError) as raised:
            ServiceEvent.objects.create(
                **event_values(
                    service_profile=self.profile,
                    event_type=ServiceEvent.EVENT_BIBLE_STUDY,
                )
            )
        self.assertIn("event_type", raised.exception.error_dict)

    def test_stale_physical_value_is_ignored_by_ordinary_save(self):
        event = ServiceEvent.objects.create(**event_values(service_profile=self.profile))
        ServiceEvent.objects.filter(pk=event.pk).update(service_profile_key="invalid text")
        event.refresh_from_db()
        event.title = "Changed without compatibility normalization"
        event.save()
        event.refresh_from_db()
        self.assertEqual(event.service_profile_id, self.profile.pk)
        self.assertEqual(event.service_profile_key, "invalid text")

    def test_referenced_profile_key_and_type_are_immutable(self):
        ServiceEvent.objects.create(**event_values(service_profile=self.profile))
        self.profile.key = "changed"
        with self.assertRaises(ValidationError) as raised:
            self.profile.save()
        self.assertEqual(
            raised.exception.error_dict["key"][0].code,
            "referenced_service_profile_key_immutable",
        )
        self.profile.refresh_from_db()
        self.profile.event_type = ServiceEvent.EVENT_BIBLE_STUDY
        with self.assertRaises(ValidationError):
            self.profile.save()


class ServiceProfileAdminTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("profile-admin", "x@example.com", "pass")
        self.request = RequestFactory().get("/admin/events/serviceevent/")
        self.request.user = self.user

    def test_admin_hides_compatibility_field(self):
        model_admin = ServiceEventAdmin(ServiceEvent, admin.site)
        form_class = model_admin.get_form(self.request)
        self.assertNotIn("service_profile_key", form_class.base_fields)
        self.assertNotIn(
            "service_profile_key", model_admin.get_readonly_fields(self.request)
        )

    def test_admin_keeps_current_inactive_profile_selectable(self):
        profile = ServiceProfile.objects.create(**profile_values())
        event = ServiceEvent.objects.create(**event_values(service_profile=profile))
        profile.is_active = False
        profile.save()
        form_class = ServiceEventAdmin(ServiceEvent, admin.site).get_form(
            self.request, obj=event
        )
        self.assertIn(profile, form_class(instance=event).fields["service_profile"].queryset)

    def test_profile_admin_locks_referenced_identity(self):
        profile = ServiceProfile.objects.create(**profile_values())
        ServiceEvent.objects.create(**event_values(service_profile=profile))
        readonly = ServiceProfileAdmin(ServiceProfile, admin.site).get_readonly_fields(
            self.request, profile
        )
        self.assertIn("key", readonly)
        self.assertIn("event_type", readonly)
