"""SE-CTX.1A tests for the structure-native host/language display fallback."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import ChurchStructureUnit, MinistryContext
from events.models import ServiceEvent, ServiceEventAudienceScope
from events.templatetags.event_extras import (
    event_host_language_label,
    event_ministry_context_label,
)


User = get_user_model()


class HostLanguageDisplayFallbackTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(
            username="ctx_creator",
            password="pw123456",
        )
        self.future_time = timezone.now() + timezone.timedelta(days=2)

        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )
        self.cm_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="中文事工",
            name_en="Chinese Ministry",
        )
        self.em_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="EM",
            name="英文事工",
            name_en="English Ministry",
        )
        self.district_unit = ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="NORTH",
            name="北区",
            name_en="North",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.district_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4",
            name="彩虹四组",
            name_en="Rainbow 4",
        )
        self.cm_context = MinistryContext.objects.create(
            code="CM",
            name="中文事工",
            name_en="Chinese Ministry",
            church_structure_unit=self.cm_unit,
        )

    def make_event(self, **overrides):
        data = {
            "title": "Gathering",
            "title_en": "Gathering",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": self.future_time,
            "status": ServiceEvent.STATUS_PUBLISHED,
            "created_by": self.creator,
        }
        data.update(overrides)
        return ServiceEvent.objects.create(**data)

    def add_audience(self, event, unit):
        return ServiceEventAudienceScope.objects.create(
            service_event=event,
            unit=unit,
        )

    def test_existing_ministry_context_label_unchanged(self):
        event = self.make_event(ministry_context=self.cm_context)
        self.add_audience(event, self.em_unit)  # audience differs from FK

        # The legacy FK label is preserved verbatim while the FK is set.
        self.assertEqual(
            event_host_language_label(event, "en"),
            event_ministry_context_label(event, "en"),
        )
        self.assertEqual(event_host_language_label(event, "en"), "CM - Chinese Ministry")
        self.assertEqual(event_host_language_label(event, "zh"), "CM - 中文事工")

    def test_null_fk_derives_from_ministry_context_audience_row(self):
        event = self.make_event(ministry_context=None)
        self.add_audience(event, self.cm_unit)

        self.assertEqual(event_host_language_label(event, "en"), "CM - Chinese Ministry")
        self.assertEqual(event_host_language_label(event, "zh"), "CM - 中文事工")

    def test_null_fk_derives_ancestor_from_district_and_small_group_rows(self):
        district_event = self.make_event(ministry_context=None)
        self.add_audience(district_event, self.district_unit)
        self.assertEqual(
            event_host_language_label(district_event, "en"),
            "CM - Chinese Ministry",
        )

        group_event = self.make_event(ministry_context=None, title="Group")
        self.add_audience(group_event, self.group_unit)
        self.assertEqual(
            event_host_language_label(group_event, "en"),
            "CM - Chinese Ministry",
        )

    def test_multiple_derived_contexts_render_safe_mixed_label(self):
        event = self.make_event(ministry_context=None)
        self.add_audience(event, self.cm_unit)
        self.add_audience(event, self.em_unit)

        self.assertEqual(
            event_host_language_label(event, "en"),
            "Multiple ministry contexts",
        )
        self.assertEqual(event_host_language_label(event, "zh"), "多个事工/语言范围")

    def test_no_audience_or_no_context_ancestor_falls_back_to_empty(self):
        no_audience = self.make_event(ministry_context=None)
        self.assertEqual(event_host_language_label(no_audience, "en"), "")

        root_event = self.make_event(ministry_context=None, title="Root")
        self.add_audience(root_event, self.root)
        self.assertEqual(event_host_language_label(root_event, "en"), "")

        custom_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="CUSTOM",
            name="Custom",
        )
        custom_event = self.make_event(ministry_context=None, title="Custom")
        self.add_audience(custom_event, custom_unit)
        self.assertEqual(event_host_language_label(custom_event, "en"), "")


class HostLanguageDisplayViewRenderTests(TestCase):
    """Templates/views still render after ministry_context is null (SE-CTX.1A)."""

    def setUp(self):
        self.password = "pw123456"
        self.manager = User.objects.create_user(
            username="ctx_manager",
            password=self.password,
            is_staff=True,
        )
        self.future_time = timezone.now() + timezone.timedelta(days=2)
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )
        self.cm_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="中文事工",
            name_en="Chinese Ministry",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4",
            name="彩虹四组",
            name_en="Rainbow 4",
        )

    def _set_language(self, language):
        session = self.client.session
        session["language"] = language
        session.save()

    def test_event_list_and_detail_render_with_derived_label(self):
        event = ServiceEvent.objects.create(
            title="Gathering",
            title_en="Gathering",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.future_time,
            status=ServiceEvent.STATUS_PUBLISHED,
            created_by=self.manager,
            ministry_context=None,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=event,
            unit=self.group_unit,
        )

        self.client.login(username="ctx_manager", password=self.password)
        self._set_language("en")

        list_response = self.client.get("/events/")
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "CM - Chinese Ministry")

        detail_response = self.client.get(f"/events/{event.id}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "CM - Chinese Ministry")
