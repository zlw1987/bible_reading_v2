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

    def test_profile_key_grammar_and_normalized_uniqueness_are_enforced(self):
        for key in ("sunday.main-11", "sunday_main", "sunday.alt"):
            with self.subTest(key=key):
                profile = ServiceProfile.objects.create(
                    **profile_values(key=key, name=key)
                )
                self.assertEqual(profile.key, key)
        with self.assertRaises(ValidationError):
            ServiceProfile.objects.create(**profile_values(key=" SUNDAY.MAIN "))

    def test_profile_name_and_event_type_are_required_and_valid(self):
        with self.assertRaises(ValidationError):
            ServiceProfile.objects.create(**profile_values(name=""))
        with self.assertRaises(ValidationError):
            ServiceProfile.objects.create(**profile_values(event_type="not-an-event"))

    def test_unreferenced_identity_is_editable(self):
        self.profile.key = "weekday.study"
        self.profile.event_type = ServiceEvent.EVENT_BIBLE_STUDY
        self.profile.save()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.key, "weekday.study")
        self.assertEqual(self.profile.event_type, ServiceEvent.EVENT_BIBLE_STUDY)

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

    def test_referenced_profile_metadata_remains_editable_without_event_revision(self):
        event = ServiceEvent.objects.create(**event_values(service_profile=self.profile))
        before_revision = event.scheduling_revision
        self.profile.name = "Renamed Sunday"
        self.profile.description = "Updated description"
        self.profile.is_active = False
        self.profile.save()
        event.refresh_from_db()
        self.assertEqual(event.service_profile_id, self.profile.pk)
        self.assertEqual(event.scheduling_revision, before_revision)


class ServiceProfileAdminTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("profile-admin", "x@example.com", "pass")
        self.request = RequestFactory().get("/admin/events/serviceevent/")
        self.request.user = self.user

    def admin_event_form(self, event, *, profile):
        form_class = ServiceEventAdmin(ServiceEvent, admin.site).get_form(
            self.request, obj=event
        )
        start = timezone.localtime(event.start_datetime)
        return form_class(
            data={
                "title": event.title,
                "title_en": event.title_en,
                "description": event.description,
                "description_en": event.description_en,
                "event_type": event.event_type,
                "service_profile": str(profile.pk) if profile else "",
                "start_datetime_0": start.strftime("%Y-%m-%d"),
                "start_datetime_1": start.strftime("%H:%M:%S"),
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

    def test_admin_has_no_removed_compatibility_field(self):
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

    def test_profile_admin_creates_canonical_profile(self):
        form_class = ServiceProfileAdmin(ServiceProfile, admin.site).get_form(
            self.request
        )
        form = form_class(
            data={
                "key": " Sunday.Main-11 ",
                "name": "Sunday Main",
                "name_en": "",
                "description": "",
                "description_en": "",
                "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
                "is_active": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().key, "sunday.main-11")

    def test_admin_selects_and_clears_only_the_fk_with_revision_boundary(self):
        profile = ServiceProfile.objects.create(**profile_values())
        event = ServiceEvent.objects.create(**event_values())

        selected = self.admin_event_form(event, profile=profile)
        self.assertTrue(selected.is_valid(), selected.errors)
        saved = selected.save()
        saved.refresh_from_db()
        self.assertEqual(saved.service_profile_id, profile.pk)
        self.assertEqual(saved.scheduling_revision, 1)

        cleared = self.admin_event_form(saved, profile=None)
        self.assertTrue(cleared.is_valid(), cleared.errors)
        saved = cleared.save()
        saved.refresh_from_db()
        self.assertIsNone(saved.service_profile_id)
        self.assertEqual(saved.scheduling_revision, 2)
