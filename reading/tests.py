import os
import re
import tempfile
from datetime import datetime, timedelta, timezone as datetime_timezone
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone

from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
)
from accounts.permissions import (
    can_view_group_progress_for,
    get_accessible_progress_groups,
)
from comments.forms import ReflectionCommentForm
from comments.models import ReflectionComment
from events.models import ServiceEvent, ServiceEventAudienceScope
from ministry.models import (
    MinistryTeam,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from reading.bible_sources import parse_reading_text
from reading.models import (
    ActivePlan,
    CheckIn,
    PlanEnrollment,
    ReadingGuidePost,
    ReadingPlan,
    ReadingPlanDay,
)
from reading.templatetags.datetime_extras import member_datetime
from reading.views import get_visible_reflection_filter
from studies.models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudyMeetingRole,
    BibleStudySeries,
)
from reading.structure_runtime_readiness import (
    run_audit as run_reading_structure_runtime_audit,
)
from accounts.management.commands.audit_legacy_structure_retirement_readiness import (
    run_audit as run_legacy_structure_retirement_audit,
)
from reading.group_progress_shadow import (
    get_membership_core_default_progress_group,
    get_membership_core_progress_roster_users,
)


class MemberDatetimeFilterTests(TestCase):
    def test_member_datetime_formats_aware_datetime_in_english(self):
        value = datetime(2026, 6, 12, 19, 30, tzinfo=datetime_timezone.utc)

        self.assertEqual(member_datetime(value, "en"), "Fri, Jun 12, 12:30 PM")

    def test_member_datetime_formats_aware_datetime_in_chinese(self):
        value = datetime(2026, 6, 12, 19, 30, tzinfo=datetime_timezone.utc)

        self.assertEqual(member_datetime(value, "zh"), "6月12日（周五）下午12:30")

    def test_member_datetime_handles_none_safely(self):
        self.assertEqual(member_datetime(None, "en"), "")


class StructuredPassageModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="passage_user",
            password="TestPass123!",
        )

        self.plan = ReadingPlan.objects.create(
            name="Structured Passage Plan",
            is_active=True,
        )

        self.day1 = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=1,
            reading_text="John 1, John 2",
            memory_verse="John 1:1",
        )

        self.active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=timezone.localdate(),
            title="Structured Active Plan",
        )

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def test_sync_plan_day_passages_creates_reading_and_memory_passages(self):
        from reading.models import ReadingPlanDayPassage
        from reading.passage_services import sync_plan_day_passages

        created_count = sync_plan_day_passages(self.day1)

        self.assertGreaterEqual(created_count, 3)

        reading_count = ReadingPlanDayPassage.objects.filter(
            plan_day=self.day1,
            passage_type=ReadingPlanDayPassage.TYPE_READING,
        ).count()

        memory_count = ReadingPlanDayPassage.objects.filter(
            plan_day=self.day1,
            passage_type=ReadingPlanDayPassage.TYPE_MEMORY,
        ).count()

        self.assertEqual(reading_count, 2)
        self.assertEqual(memory_count, 1)

    def test_get_reading_passages_uses_structured_passages_when_available(self):
        from reading.models import ReadingPlanDayPassage
        from reading.passage_services import get_reading_passages

        ReadingPlanDayPassage.objects.create(
            plan_day=self.day1,
            passage_type=ReadingPlanDayPassage.TYPE_READING,
            sort_order=0,
            raw_reference="John 9",
            scripture_ref_key="John 9",
            display_zh="约翰福音 第 9 章",
            display_en="John 9",
            text_url_zh="https://example.com/zh",
            text_url_en="https://example.com/en",
            audio_url="https://example.com/audio",
        )

        passages = get_reading_passages(self.day1)

        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0]["search_text"], "John 9")
        self.assertEqual(passages[0]["display_en"], "John 9")
        self.assertEqual(passages[0]["audio_url"], "https://example.com/audio")

    def test_passage_reader_can_use_structured_passage(self):
        from reading.models import ReadingPlanDayPassage

        ReadingPlanDayPassage.objects.create(
            plan_day=self.day1,
            passage_type=ReadingPlanDayPassage.TYPE_READING,
            sort_order=0,
            raw_reference="John 9",
            scripture_ref_key="John 9",
            display_zh="约翰福音 第 9 章",
            display_en="John 9",
            text_url_zh="https://example.com/zh",
            text_url_en="https://example.com/en",
            audio_url="https://example.com/audio",
        )

        self.set_language("en")
        self.client.login(username="passage_user", password="TestPass123!")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "John 9")
        self.assertContains(response, "https://example.com/en")

    def test_audio_reader_can_use_structured_passage(self):
        from reading.models import ReadingPlanDayPassage

        ReadingPlanDayPassage.objects.create(
            plan_day=self.day1,
            passage_type=ReadingPlanDayPassage.TYPE_READING,
            sort_order=0,
            raw_reference="John 9",
            scripture_ref_key="John 9",
            display_zh="约翰福音 第 9 章",
            display_en="John 9",
            text_url_zh="https://example.com/zh",
            text_url_en="https://example.com/en",
            audio_url="https://example.com/audio",
        )

        self.set_language("en")
        self.client.login(username="passage_user", password="TestPass123!")

        response = self.client.get(
            reverse("audio_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "John 9")
        self.assertContains(response, "https://example.com/audio")
        self.assertContains(response, "audio-frame-compact")

class ReadingCalendarViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="calendar_user",
            password="TestPass123!",
        )

        self.plan = ReadingPlan.objects.create(
            name="Calendar Test Plan",
            is_active=True,
        )

        today = timezone.localdate()

        self.day1 = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=1,
            reading_text="John 1",
            memory_verse="John 1:1",
        )

        # Day 2 intentionally missing = rest / catch-up day.

        self.day3 = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=3,
            reading_text="John 3",
            memory_verse="John 3:16",
        )

        self.active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=today - timezone.timedelta(days=1),
            title="Calendar Active Plan",
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def test_calendar_requires_enrollment(self):
        self.client.login(username="calendar_user", password="TestPass123!")

        response = self.client.get(
            reverse("active_plan_calendar", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_calendar_shows_checked_rest_and_future_states(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        CheckIn.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
        )

        self.client.login(username="calendar_user", password="TestPass123!")
        self.set_language("en")
        today = timezone.localdate()

        response = self.client.get(
            reverse("active_plan_calendar", args=[self.active_plan.id]),
            {
                "year": today.year,
                "month": today.month,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Calendar")
        self.assertContains(response, "calendar-day-checked")
        self.assertContains(response, "calendar-day-rest")
        self.assertContains(response, "calendar-day-future")
        self.assertContains(
            response,
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0]),
        )
        self.assertContains(
            response,
            reverse("audio_reader", args=[self.active_plan.id, self.day1.id, 0]),
        )

    def test_calendar_month_navigation_links_render(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="calendar_user", password="TestPass123!")
        self.set_language("en")
        today = timezone.localdate()

        response = self.client.get(
            reverse("active_plan_calendar", args=[self.active_plan.id]),
            {
                "year": today.year,
                "month": today.month,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Previous")
        self.assertContains(response, "Next")
        self.assertContains(response, "month=")

class ReflectionWallVisibilityRegressionTests(TestCase):
    def setUp(self):
        # CS-CORE.4G.2: group reflection visibility is membership-core, so each
        # small group is mapped to a structure unit and members get an active
        # primary membership in that unit.
        self.group_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RAINBOW4",
            name="Rainbow 4 Unit",
        )
        self.other_group_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RAINBOW5",
            name="Rainbow 5 Unit",
        )
        self.group = self.group_unit
        self.other_group = self.other_group_unit

        self.author = self.create_member("author", self.group, self.group_unit)
        self.same_group_user = self.create_member(
            "same_group", self.group, self.group_unit
        )
        self.other_group_user = self.create_member(
            "other_group", self.other_group, self.other_group_unit
        )

        self.staff = User.objects.create_user(
            username="staff",
            password="TestPass123!",
            is_staff=True,
        )

        self.plan = ReadingPlan.objects.create(
            name="Regression Test Plan",
            is_active=True,
        )

        self.day1 = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=1,
            reading_text="John 1",
            memory_verse="John 1:1",
        )

        self.active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=timezone.localdate(),
            title="Regression Active Plan",
        )

        for user in [
            self.author,
            self.same_group_user,
            self.other_group_user,
            self.staff,
        ]:
            PlanEnrollment.objects.create(
                user=user,
                active_plan=self.active_plan,
            )

    def create_member(self, username, group, unit):
        user = User.objects.create_user(username=username, password="TestPass123!")
        ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        return user

    def make_reflection(
        self,
        *,
        user=None,
        body="Test reflection.",
        visibility=ReflectionComment.VISIBILITY_GROUP,
        is_hidden=False,
        is_anonymous=False,
        small_group=None,
        parent=None,
    ):
        if user is None:
            user = self.author

        if small_group is None:
            small_group = self.group

        # CS-CORE.4G.2: stamp the structure snapshot that now drives group
        # visibility, mirroring the live create path.
        structure_unit = getattr(small_group, "church_structure_unit", small_group)

        return ReflectionComment.objects.create(
            user=user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            parent=parent,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=visibility,
            is_hidden=is_hidden,
            is_anonymous=is_anonymous,
            structure_unit_at_post=structure_unit,
            body=body,
        )

    def test_reader_shows_comment_thread_and_visible_reply(self):
        parent = self.make_reflection(
            body="Parent reflection.",
            visibility=ReflectionComment.VISIBILITY_GROUP,
        )

        self.make_reflection(
            user=self.same_group_user,
            parent=parent,
            body="Visible reply.",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.group,
        )

        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Parent reflection.")
        self.assertContains(response, "Visible reply.")

    def test_text_reader_and_audio_reader_share_reflection_flow(self):
        self.make_reflection(
            body="Shared reflection.",
            visibility=ReflectionComment.VISIBILITY_GROUP,
        )

        self.client.login(username="same_group", password="TestPass123!")

        text_response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        audio_response = self.client.get(
            reverse("audio_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(text_response.status_code, 200)
        self.assertEqual(audio_response.status_code, 200)

        self.assertContains(text_response, "Shared reflection.")
        self.assertContains(audio_response, "Shared reflection.")

        self.assertContains(text_response, "scripture-frame")
        self.assertNotContains(text_response, "audio-frame-compact")

        self.assertContains(audio_response, "audio-frame-compact")
        self.assertNotContains(audio_response, "scripture-frame")

    def test_group_reflection_is_visible_to_same_group_user(self):
        self.make_reflection(
            body="Same group reflection.",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.group,
        )

        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "group",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Same group reflection.")

    def test_group_reflection_is_hidden_from_other_group_user(self):
        self.make_reflection(
            body="Hidden from other group.",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.group,
        )

        self.client.login(username="other_group", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "group",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Hidden from other group.")

    def test_church_reflection_is_visible_on_reflection_wall(self):
        self.make_reflection(
            body="Church-wide reflection.",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
        )

        self.client.login(username="other_group", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "church",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Church-wide reflection.")

    def test_hidden_reflection_is_not_visible_to_other_regular_user_on_wall(self):
        self.make_reflection(
            body="Hidden wall reflection.",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            is_hidden=True,
        )

        self.client.login(username="other_group", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "church",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Hidden wall reflection.")

    def test_hidden_reflection_is_visible_to_author_on_wall(self):
        self.make_reflection(
            body="My hidden reflection.",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            is_hidden=True,
        )

        self.client.login(username="author", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "church",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My hidden reflection.")
        self.assertContains(response, "已隐藏")

    def test_hidden_reflection_is_visible_to_staff_on_wall(self):
        self.make_reflection(
            body="Staff-visible hidden reflection.",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            is_hidden=True,
        )

        self.client.login(username="staff", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "church",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff-visible hidden reflection.")
        self.assertContains(response, "已隐藏")

    def test_anonymous_reflection_hides_author_from_regular_user(self):
        self.make_reflection(
            body="Anonymous reflection.",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            is_anonymous=True,
        )

        self.client.login(username="other_group", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "church",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anonymous reflection.")
        self.assertContains(response, "Anonymous")
        self.assertNotContains(response, "author")

    def test_staff_can_see_anonymous_author(self):
        self.make_reflection(
            body="Anonymous staff-visible reflection.",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            is_anonymous=True,
        )

        self.client.login(username="staff", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "church",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anonymous staff-visible reflection.")
        self.assertContains(response, "Anonymous (author)")


class ReflectionPrivacyInvariantTests(TestCase):
    """Reflection privacy invariants.

    CS-CORE.4C originally locked the legacy reflection privacy behavior (driven by
    `Profile.small_group` and the since-removed `small_group_at_post` mirror).
    CS-CORE.4G.2 switched the ordinary-member group read path to
    `structure_unit_at_post` + active primary `ChurchStructureMembership`, and these
    tests now assert that membership-core behavior (fail-closed on
    missing/inactive/wrong-type snapshot, no/multiple active primary memberships).
    The legacy `small_group_at_post` mirror was removed in REFLECTION-MIRROR.1H.
    Staff/author/church/private/hidden/deleted behavior is unchanged.
    """

    def setUp(self):
        self.old_group_name = "Invariant Old Group"
        self.other_group_name = "Invariant Other Group"
        self.old_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="INV_OLD",
            name="Invariant Old Unit",
        )
        self.new_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="INV_NEW",
            name="Invariant New Unit",
        )
        self.other_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="INV_OTHER",
            name="Invariant Other Unit",
        )
        # Nested small-group unit under old_unit exercises the descendant rule:
        # a member of old_child_unit can see a post snapshotted to old_unit.
        self.old_child_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="INV_OLD_CHILD",
            name="Invariant Old Child Unit",
            parent=self.old_unit,
        )
        self.old_group = self.old_unit
        self.new_group = self.new_unit
        self.other_group = self.other_unit

        self.author = self.create_user("invariant_author", group=self.old_group)
        self.same_group_user = self.create_user(
            "invariant_same_group",
            group=self.old_group,
        )
        self.old_group_member = self.create_user(
            "invariant_old_member",
            group=self.old_group,
        )
        self.new_group_member = self.create_user(
            "invariant_new_member",
            group=self.new_group,
        )
        self.other_group_user = self.create_user(
            "invariant_other_group",
            group=self.other_group,
        )
        self.no_group_user = self.create_user("invariant_no_group")
        self.staff = User.objects.create_user(
            username="invariant_staff",
            password="TestPass123!",
            is_staff=True,
        )

        self.plan = ReadingPlan.objects.create(
            name="Invariant Reading Plan",
            is_active=True,
        )
        self.day = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=1,
            reading_text="John 1",
            memory_verse="John 1:1",
        )
        self.active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=timezone.localdate(),
            title="Invariant Active Plan",
        )

        for user in [
            self.author,
            self.same_group_user,
            self.old_group_member,
            self.new_group_member,
            self.other_group_user,
            self.no_group_user,
            self.staff,
        ]:
            PlanEnrollment.objects.create(user=user, active_plan=self.active_plan)

    def create_user(self, username, *, group=None, membership_unit="__from_group__"):
        """Create a user with optional legacy group and active primary membership.

        By default (CS-CORE.4G.2) the user also gets a single active primary
        ChurchStructureMembership in the group's mapped structure unit, because
        group reflection visibility is now membership-core. Pass
        ``membership_unit=None`` for a legacy-profile-only user with no
        membership, or an explicit unit to override.
        """
        user = User.objects.create_user(username=username, password="TestPass123!")
        if membership_unit == "__from_group__":
            membership_unit = getattr(group, "church_structure_unit", group)
        if membership_unit is not None:
            self.create_membership(user, membership_unit)
        return user

    def create_membership(self, user, unit):
        return ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

    def make_reflection(
        self,
        *,
        user=None,
        body="Invariant reflection",
        visibility=ReflectionComment.VISIBILITY_GROUP,
        small_group=None,
        is_hidden=False,
        is_deleted=False,
        parent=None,
        structure_unit="__from_group__",
    ):
        # CS-CORE.4G.2: group visibility is driven by the structure snapshot, so
        # by default stamp the snapshot from the fixture group's mapped unit, the
        # same way the live create path does. Tests pass an explicit unit (or
        # None) to exercise mismatch / missing-snapshot fail-closed cases.
        if structure_unit == "__from_group__":
            structure_unit = getattr(small_group, "church_structure_unit", small_group)
        return ReflectionComment.objects.create(
            user=user or self.author,
            active_plan=self.active_plan,
            plan_day=self.day,
            parent=parent,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=visibility,
            structure_unit_at_post=structure_unit,
            is_hidden=is_hidden,
            is_deleted=is_deleted,
            body=body,
        )

    def reflection_ids_visible_by_filter(self, user):
        return set(
            ReflectionComment.objects.filter(
                get_visible_reflection_filter(user),
                scripture_ref_key="John 1",
                parent__isnull=True,
            ).values_list("id", flat=True)
        )

    def reflection_ids_visible_by_gate(self, user):
        return {
            reflection.id
            for reflection in ReflectionComment.objects.filter(
                scripture_ref_key="John 1",
                parent__isnull=True,
            )
            if reflection.can_be_seen_by(user)
        }

    def passage_wall_group_ids_for(self, user):
        self.client.login(username=user.username, password="TestPass123!")
        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "group",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.client.logout()
        return {reflection.id for reflection in response.context["reflections"]}

    def test_group_church_private_and_hidden_canonical_gate(self):
        group_post = self.make_reflection(
            body="Group post",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
        )
        church_post = self.make_reflection(
            body="Church post",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
        )
        private_post = self.make_reflection(
            body="Private post",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
        )
        hidden_group_post = self.make_reflection(
            body="Hidden group post",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
            is_hidden=True,
        )
        deleted_group_post = self.make_reflection(
            body="Deleted group post",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
            is_deleted=True,
        )

        for viewer in [self.author, self.same_group_user, self.staff]:
            self.assertTrue(group_post.can_be_seen_by(viewer))

        for viewer in [self.other_group_user, self.no_group_user]:
            self.assertFalse(group_post.can_be_seen_by(viewer))

        for viewer in [
            self.same_group_user,
            self.other_group_user,
            self.no_group_user,
        ]:
            self.assertTrue(church_post.can_be_seen_by(viewer))
            self.assertFalse(private_post.can_be_seen_by(viewer))
            self.assertFalse(hidden_group_post.can_be_seen_by(viewer))
            self.assertFalse(deleted_group_post.can_be_seen_by(viewer))

        for viewer in [self.author, self.staff]:
            self.assertTrue(private_post.can_be_seen_by(viewer))
            self.assertTrue(hidden_group_post.can_be_seen_by(viewer))
            self.assertTrue(deleted_group_post.can_be_seen_by(viewer))

    def test_struct_1c_snapshot_row_first_precedence_no_legacy_fallback(self):
        # READING-STRUCT.1C guard: reflection group visibility is structure
        # snapshot row-first (snapshot-only). When a valid snapshot exists it is
        # the sole audience source (legacy Profile.small_group never overrides it);
        # when no valid snapshot exists the post fails closed for ordinary viewers
        # -- no legacy fallback was re-added. Holds for the per-row gate, the
        # list/feed filter, and the passage_wall group tab.
        snapshot_post = self.make_reflection(
            user=self.author,
            body="Snapshot wins over membership group",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            structure_unit=self.new_unit,  # snapshot points at new_unit
        )
        no_snapshot_post = self.make_reflection(
            user=self.author,
            body="No snapshot",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            structure_unit=None,
        )

        # Snapshot wins: the new_unit member sees it; the old member does not --
        # Profile.small_group does not override the snapshot.
        self.assertTrue(snapshot_post.can_be_seen_by(self.new_group_member))
        self.assertFalse(snapshot_post.can_be_seen_by(self.old_group_member))
        self.assertIn(
            snapshot_post.id,
            self.reflection_ids_visible_by_filter(self.new_group_member),
        )
        self.assertNotIn(
            snapshot_post.id,
            self.reflection_ids_visible_by_filter(self.old_group_member),
        )
        self.assertEqual(
            self.passage_wall_group_ids_for(self.new_group_member),
            {snapshot_post.id},
        )

        # No snapshot: fail closed for the membership-matching member -- no fallback.
        self.assertFalse(no_snapshot_post.can_be_seen_by(self.old_group_member))
        self.assertNotIn(
            no_snapshot_post.id,
            self.reflection_ids_visible_by_filter(self.old_group_member),
        )
        self.assertEqual(self.passage_wall_group_ids_for(self.old_group_member), set())

        # Detail gate and queryset filter stay in lockstep for both viewers.
        for viewer in [self.new_group_member, self.old_group_member]:
            self.assertEqual(
                self.reflection_ids_visible_by_filter(viewer),
                self.reflection_ids_visible_by_gate(viewer),
            )

    def test_filter_and_group_tab_agree_with_detail_for_group_privacy(self):
        group_post = self.make_reflection(
            body="Group invariant post",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
        )
        other_group_post = self.make_reflection(
            user=self.other_group_user,
            body="Other group invariant post",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.other_group,
        )
        author_private = self.make_reflection(
            body="Author private invariant post",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
        )
        other_user_church_post = self.make_reflection(
            user=self.other_group_user,
            body="Church invariant post",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
        )
        hidden_group_post = self.make_reflection(
            body="Hidden group invariant post",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
            is_hidden=True,
        )

        for viewer in [
            self.author,
            self.same_group_user,
            self.other_group_user,
            self.no_group_user,
            self.staff,
        ]:
            self.assertEqual(
                self.reflection_ids_visible_by_filter(viewer),
                self.reflection_ids_visible_by_gate(viewer),
            )

        # The group tab intentionally excludes church-wall posts and only adds
        # own non-deleted posts plus visible group posts for ordinary users.
        self.assertEqual(
            self.passage_wall_group_ids_for(self.same_group_user),
            {group_post.id},
        )
        self.assertEqual(
            self.passage_wall_group_ids_for(self.other_group_user),
            {other_group_post.id, other_user_church_post.id},
        )
        self.assertEqual(self.passage_wall_group_ids_for(self.no_group_user), set())
        self.assertEqual(
            self.passage_wall_group_ids_for(self.author),
            {group_post.id, author_private.id, hidden_group_post.id},
        )
        self.assertEqual(
            self.passage_wall_group_ids_for(self.staff),
            {group_post.id, other_group_post.id, hidden_group_post.id},
        )

        for viewer in [
            self.author,
            self.same_group_user,
            self.other_group_user,
            self.staff,
        ]:
            for reflection_id in self.passage_wall_group_ids_for(viewer):
                reflection = ReflectionComment.objects.get(id=reflection_id)
                self.assertTrue(reflection.can_be_seen_by(viewer))

    def test_structure_unit_snapshot_drives_group_visibility(self):
        # CS-CORE.4G.2: the structure snapshot drives group visibility. A post
        # whose structure_unit_at_post is new_unit is visible to the new-unit
        # member and hidden from the old-unit member, regardless of the author's
        # or viewers' Profile.small_group.
        mismatched_snapshot_post = self.make_reflection(
            user=self.author,
            body="Mismatched structure snapshot",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            structure_unit=self.new_unit,
        )

        self.assertTrue(mismatched_snapshot_post.can_be_seen_by(self.new_group_member))
        self.assertFalse(mismatched_snapshot_post.can_be_seen_by(self.old_group_member))
        self.assertIn(
            mismatched_snapshot_post.id,
            self.reflection_ids_visible_by_filter(self.new_group_member),
        )
        self.assertNotIn(
            mismatched_snapshot_post.id,
            self.reflection_ids_visible_by_filter(self.old_group_member),
        )
        self.assertEqual(
            self.passage_wall_group_ids_for(self.new_group_member),
            {mismatched_snapshot_post.id},
        )
        self.assertEqual(self.passage_wall_group_ids_for(self.old_group_member), set())

    def test_matching_legacy_group_without_structure_snapshot_is_not_visible(self):
        # CS-CORE.4G.2: a legacy-matching group post with NO structure snapshot
        # fails closed for an ordinary same-legacy-group viewer.
        post = self.make_reflection(
            user=self.author,
            body="Legacy only, no structure snapshot",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
            structure_unit=None,
        )

        self.assertFalse(post.can_be_seen_by(self.old_group_member))
        self.assertNotIn(
            post.id,
            self.reflection_ids_visible_by_filter(self.old_group_member),
        )
        self.assertEqual(self.passage_wall_group_ids_for(self.old_group_member), set())

    def test_profile_small_group_alone_does_not_grant_group_visibility(self):
        # CS-CORE.4G.2: Profile.small_group without an active primary membership
        # no longer grants group reflection visibility, even with a valid snapshot.
        profile_only_user = self.create_user(
            "invariant_profile_only",
            group=self.old_group,
            membership_unit=None,
        )
        PlanEnrollment.objects.create(
            user=profile_only_user, active_plan=self.active_plan
        )
        post = self.make_reflection(
            user=self.author,
            body="Valid snapshot, viewer has profile group only",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
        )

        self.assertFalse(post.can_be_seen_by(profile_only_user))
        self.assertNotIn(
            post.id,
            self.reflection_ids_visible_by_filter(profile_only_user),
        )
        self.assertEqual(self.passage_wall_group_ids_for(profile_only_user), set())

    def test_membership_descendant_of_snapshot_unit_can_see_post(self):
        # CS-CORE.4G.2: a member of a descendant unit of the snapshot unit matches.
        child_member = self.create_user(
            "invariant_child_member",
            membership_unit=self.old_child_unit,
        )
        PlanEnrollment.objects.create(user=child_member, active_plan=self.active_plan)
        post = self.make_reflection(
            user=self.author,
            body="Snapshot at parent unit",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
            structure_unit=self.old_unit,
        )

        self.assertTrue(post.can_be_seen_by(child_member))
        self.assertIn(
            post.id,
            self.reflection_ids_visible_by_filter(child_member),
        )
        self.assertEqual(
            self.passage_wall_group_ids_for(child_member),
            {post.id},
        )

    def test_no_active_primary_membership_fails_closed_for_group_visibility(self):
        no_membership_user = self.create_user(
            "invariant_no_membership",
            membership_unit=None,
        )
        PlanEnrollment.objects.create(
            user=no_membership_user, active_plan=self.active_plan
        )
        post = self.make_reflection(
            user=self.author,
            body="Valid snapshot, viewer has no membership",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
        )

        self.assertFalse(post.can_be_seen_by(no_membership_user))
        self.assertNotIn(
            post.id,
            self.reflection_ids_visible_by_filter(no_membership_user),
        )
        self.assertEqual(self.passage_wall_group_ids_for(no_membership_user), set())

    def test_multiple_active_primary_memberships_fail_closed(self):
        ambiguous_user = self.create_user(
            "invariant_ambiguous",
            membership_unit=None,
        )
        # bulk_create bypasses the single-active-primary model validation so the
        # helper's fail-closed handling of an ambiguous state is exercised.
        today = timezone.localdate()
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=ambiguous_user,
                    unit=self.old_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
                ChurchStructureMembership(
                    user=ambiguous_user,
                    unit=self.new_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
            ]
        )
        PlanEnrollment.objects.create(user=ambiguous_user, active_plan=self.active_plan)
        post = self.make_reflection(
            user=self.author,
            body="Valid snapshot, viewer has two active primary memberships",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
        )

        self.assertFalse(post.can_be_seen_by(ambiguous_user))
        self.assertNotIn(
            post.id,
            self.reflection_ids_visible_by_filter(ambiguous_user),
        )
        self.assertEqual(self.passage_wall_group_ids_for(ambiguous_user), set())

    def test_new_group_reflection_stamps_structure_unit(self):
        # CS-CORE.4G.2: a new group reflection stamps structure_unit_at_post from
        # the author's active primary membership, remaining visible to the same
        # membership group and hidden from other groups.
        self.client.login(username=self.author.username, password="TestPass123!")
        response = self.client.post(
            reverse("add_comment", args=[self.active_plan.id, self.day.id, 0]),
            {
                "body": "Mapped group reflection",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        comment = ReflectionComment.objects.get(body="Mapped group reflection")
        self.assertEqual(comment.visibility, ReflectionComment.VISIBILITY_GROUP)
        self.assertEqual(comment.structure_unit_at_post, self.old_unit)
        self.assertTrue(comment.can_be_seen_by(self.old_group_member))
        self.assertFalse(comment.can_be_seen_by(self.new_group_member))

    def test_new_group_reflection_with_membership_unit_without_legacy_group(self):
        # CS-CORE.4G.3 (coverage 7): a member of a small-group unit that has no
        # legacy SmallGroup mapping can still share to group. structure_unit_at_post
        # is stamped from the membership unit and is visible through the 4G.2 read
        # path.
        nolegacy_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="INV_NO_LEGACY",
            name="Invariant No-Legacy Unit",
        )
        author = self.create_user(
            "invariant_nolegacy_author",
            membership_unit=nolegacy_unit,
        )
        PlanEnrollment.objects.create(user=author, active_plan=self.active_plan)
        viewer = self.create_user(
            "invariant_nolegacy_viewer",
            membership_unit=nolegacy_unit,
        )
        PlanEnrollment.objects.create(user=viewer, active_plan=self.active_plan)

        self.client.login(username=author.username, password="TestPass123!")
        response = self.client.post(
            reverse("add_comment", args=[self.active_plan.id, self.day.id, 0]),
            {
                "body": "No-legacy group reflection",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        comment = ReflectionComment.objects.get(body="No-legacy group reflection")
        self.assertEqual(comment.visibility, ReflectionComment.VISIBILITY_GROUP)
        self.assertEqual(comment.structure_unit_at_post, nolegacy_unit)
        self.assertTrue(comment.can_be_seen_by(viewer))
        self.assertFalse(comment.can_be_seen_by(self.old_group_member))

    def test_new_private_or_church_reflection_records_structure_companion_only(self):
        self.client.login(username=self.author.username, password="TestPass123!")

        for visibility in [
            ReflectionComment.VISIBILITY_PRIVATE,
            ReflectionComment.VISIBILITY_CHURCH,
        ]:
            with self.subTest(visibility=visibility):
                response = self.client.post(
                    reverse("add_comment", args=[self.active_plan.id, self.day.id, 0]),
                    {
                        "body": f"{visibility} reflection structure companion",
                        "visibility": visibility,
                        "is_anonymous": "",
                    },
                )
                self.assertEqual(response.status_code, 302)

                comment = ReflectionComment.objects.get(
                    body=f"{visibility} reflection structure companion",
                )
                self.assertEqual(comment.visibility, visibility)
                # CS-CORE.4G.2: new posts record the structure snapshot companion.
                self.assertEqual(comment.structure_unit_at_post, self.old_unit)
                self.assertTrue(comment.can_be_seen_by(self.author))
                self.assertEqual(
                    comment.can_be_seen_by(self.old_group_member),
                    visibility == ReflectionComment.VISIBILITY_CHURCH,
                )

    def test_reply_inherits_parent_visibility_and_group_and_stays_inherited_on_edit(self):
        parent = self.make_reflection(
            user=self.author,
            body="Group parent for reply",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
            structure_unit=self.old_unit,
        )

        self.client.login(username=self.same_group_user.username, password="TestPass123!")
        response = self.client.post(
            reverse("add_reply", args=[parent.id]),
            {
                "body": "Inherited reply",
                "is_anonymous": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        reply = ReflectionComment.objects.get(parent=parent, body="Inherited reply")

        self.assertEqual(reply.visibility, parent.visibility)
        # CS-CORE.4G.2: replies inherit the parent structure snapshot.
        self.assertEqual(reply.structure_unit_at_post, parent.structure_unit_at_post)
        self.assertTrue(parent.can_be_seen_by(self.same_group_user))
        self.assertTrue(reply.can_be_seen_by(self.same_group_user))
        self.assertFalse(parent.can_be_seen_by(self.other_group_user))
        self.assertFalse(reply.can_be_seen_by(self.other_group_user))

        response = self.client.post(
            reverse("edit_comment", args=[reply.id]),
            {
                "body": "Edited inherited reply",
                "visibility": ReflectionComment.VISIBILITY_CHURCH,
                "is_anonymous": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        reply.refresh_from_db()

        self.assertEqual(reply.body, "Edited inherited reply")
        self.assertEqual(reply.visibility, parent.visibility)
        # CS-CORE.4G.2: editing a reply preserves the inherited parent snapshot.
        self.assertEqual(reply.structure_unit_at_post, parent.structure_unit_at_post)
        self.assertFalse(reply.can_be_seen_by(self.other_group_user))

    def test_group_post_keeps_historical_snapshot_after_author_transfer(self):
        post = self.make_reflection(
            user=self.author,
            body="Old group snapshot",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
        )


        post.refresh_from_db()
        self.assertTrue(post.can_be_seen_by(self.old_group_member))
        self.assertFalse(post.can_be_seen_by(self.new_group_member))
        self.assertTrue(post.can_be_seen_by(self.author))

    def test_top_level_group_edit_after_transfer_preserves_original_group_snapshot(self):
        post = self.make_reflection(
            user=self.author,
            body="Transfer edit source",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
            structure_unit=self.old_unit,
        )

        self.client.login(username=self.author.username, password="TestPass123!")
        response = self.client.post(
            reverse("edit_comment", args=[post.id]),
            {
                "body": "Transfer edit Policy C behavior",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()

        self.assertEqual(post.structure_unit_at_post, self.old_unit)
        self.assertTrue(post.can_be_seen_by(self.old_group_member))
        self.assertFalse(post.can_be_seen_by(self.new_group_member))
        self.assertTrue(post.can_be_seen_by(self.author))

    def test_top_level_group_body_and_anonymity_edit_preserves_group_snapshot(self):
        post = self.make_reflection(
            user=self.author,
            body="Body edit source",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
            structure_unit=self.old_unit,
        )

        self.client.login(username=self.author.username, password="TestPass123!")
        response = self.client.post(
            reverse("edit_comment", args=[post.id]),
            {
                "body": "Body edit stays in original group",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()

        self.assertEqual(post.body, "Body edit stays in original group")
        self.assertTrue(post.is_anonymous)
        self.assertEqual(post.structure_unit_at_post, self.old_unit)
        self.assertTrue(post.can_be_seen_by(self.old_group_member))
        self.assertFalse(post.can_be_seen_by(self.new_group_member))

    def test_migrated_group_post_group_edit_preserves_structure_snapshot(self):
        # CS-CORE.4G.2 / Policy C: a structure-native group post keeps its original
        # structure_unit_at_post after a group->group edit and is never re-homed to
        # the author's current membership.
        post = self.make_reflection(
            user=self.author,
            body="Migrated group source",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=None,
            structure_unit=self.old_unit,
        )

        self.client.login(username=self.author.username, password="TestPass123!")
        response = self.client.post(
            reverse("edit_comment", args=[post.id]),
            {
                "body": "Migrated group edit stays structure-native",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()

        self.assertEqual(post.body, "Migrated group edit stays structure-native")
        self.assertEqual(post.structure_unit_at_post, self.old_unit)
        self.assertTrue(post.can_be_seen_by(self.old_group_member))
        self.assertFalse(post.can_be_seen_by(self.new_group_member))

    def test_top_level_private_or_church_edit_to_group_stamps_membership_unit(self):
        # CS-CORE.4G.3 (coverage 8): editing a non-group top-level post into group
        # stamps the snapshot from the author's active primary membership unit, not
        # Profile.small_group. Move the author's membership to new_unit while their
        # profile still points at old_group, proving the membership is the source.
        ChurchStructureMembership.objects.filter(user=self.author).update(
            unit=self.new_unit,
        )
        self.client.login(username=self.author.username, password="TestPass123!")

        for original_visibility in [
            ReflectionComment.VISIBILITY_PRIVATE,
            ReflectionComment.VISIBILITY_CHURCH,
        ]:
            with self.subTest(original_visibility=original_visibility):
                post = self.make_reflection(
                    user=self.author,
                    body=f"{original_visibility} to group source",
                    visibility=original_visibility,
                    small_group=self.old_group,
                    structure_unit=self.old_unit,
                )

                response = self.client.post(
                    reverse("edit_comment", args=[post.id]),
                    {
                        "body": f"{original_visibility} now group",
                        "visibility": ReflectionComment.VISIBILITY_GROUP,
                        "is_anonymous": "",
                    },
                )
                self.assertEqual(response.status_code, 302)
                post.refresh_from_db()

                self.assertEqual(post.visibility, ReflectionComment.VISIBILITY_GROUP)
                self.assertEqual(post.structure_unit_at_post, self.new_unit)
                # REFLECTION-MIRROR.1D: entering group visibility leaves the legacy
                # mirror null even when a legacy SmallGroup maps to the new unit.
                self.assertTrue(post.can_be_seen_by(self.new_group_member))
                self.assertFalse(post.can_be_seen_by(self.old_group_member))
                self.assertTrue(post.can_be_seen_by(self.author))

    def test_no_group_user_has_safe_reflection_create_and_visibility_behavior(self):
        group_post = self.make_reflection(
            body="No-group hidden group post",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
        )
        own_group_post = self.make_reflection(
            user=self.no_group_user,
            body="Own no-group post",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=None,
        )

        self.assertFalse(group_post.can_be_seen_by(self.no_group_user))
        self.assertTrue(own_group_post.can_be_seen_by(self.no_group_user))
        self.assertEqual(
            self.passage_wall_group_ids_for(self.no_group_user),
            {own_group_post.id},
        )

        form = ReflectionCommentForm(
            {
                "body": "No-group attempted group post",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
            user=self.no_group_user,
            language="en",
        )
        self.assertNotIn(
            ReflectionComment.VISIBILITY_GROUP,
            [value for value, _label in form.fields["visibility"].choices],
        )
        self.assertFalse(form.is_valid())

        self.client.login(username=self.no_group_user.username, password="TestPass123!")
        before_count = ReflectionComment.objects.count()
        response = self.client.post(
            reverse("add_comment", args=[self.active_plan.id, self.day.id, 0]),
            {
                "body": "No-group view attempt",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ReflectionComment.objects.count(), before_count)

    def test_no_group_user_cannot_edit_reflection_into_group_visibility(self):
        post = self.make_reflection(
            user=self.no_group_user,
            body="No-group private edit source",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            small_group=None,
        )

        self.client.login(username=self.no_group_user.username, password="TestPass123!")
        response = self.client.post(
            reverse("edit_comment", args=[post.id]),
            {
                "body": "No-group attempted group edit",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()

        self.assertEqual(post.body, "No-group private edit source")
        self.assertEqual(post.visibility, ReflectionComment.VISIBILITY_PRIVATE)
        self.assertIsNone(post.structure_unit_at_post)

    def _group_choice_values(self, form):
        return [value for value, _label in form.fields["visibility"].choices]

    def test_membership_without_profile_group_offers_group_in_form(self):
        # CS-CORE.4G.3 (coverage 1 + 11): an active primary small-group membership
        # offers group sharing even without Profile.small_group, and
        # Profile.small_group alone no longer controls form option-gating.
        membership_only = self.create_user(
            "invariant_form_membership_only",
            membership_unit=self.old_unit,
        )

        form = ReflectionCommentForm(
            {
                "body": "Membership-only group post",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
            user=membership_only,
            language="en",
        )
        self.assertIn(ReflectionComment.VISIBILITY_GROUP, self._group_choice_values(form))
        self.assertTrue(form.is_valid())

        # Profile.small_group with no active primary membership does NOT offer group.
        profile_only = self.create_user(
            "invariant_form_profile_only",
            group=self.old_group,
            membership_unit=None,
        )
        profile_form = ReflectionCommentForm(
            {
                "body": "Profile-only attempted group post",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
            user=profile_only,
            language="en",
        )
        self.assertNotIn(
            ReflectionComment.VISIBILITY_GROUP,
            self._group_choice_values(profile_form),
        )
        self.assertFalse(profile_form.is_valid())

    def test_membership_user_creates_group_reflection_with_structure_snapshot(self):
        # CS-CORE.4G.3 (coverage 2 + 6): a membership-only user creates a group
        # reflection whose structure_unit_at_post is the membership unit. The post
        # is visible through the 4G.2 read path to a matching member.
        author = self.create_user(
            "invariant_membership_author",
            membership_unit=self.old_unit,
        )
        PlanEnrollment.objects.create(user=author, active_plan=self.active_plan)

        self.client.login(username=author.username, password="TestPass123!")
        response = self.client.post(
            reverse("add_comment", args=[self.active_plan.id, self.day.id, 0]),
            {
                "body": "Membership group reflection",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        comment = ReflectionComment.objects.get(body="Membership group reflection")
        self.assertEqual(comment.visibility, ReflectionComment.VISIBILITY_GROUP)
        self.assertEqual(comment.structure_unit_at_post, self.old_unit)
        self.assertTrue(comment.can_be_seen_by(self.old_group_member))
        self.assertFalse(comment.can_be_seen_by(self.new_group_member))

    def test_profile_only_user_group_write_path_is_rejected(self):
        # CS-CORE.4G.3 (coverage 3): Profile.small_group without an active primary
        # membership does not get the group choice, and a forced group POST is
        # rejected with no reflection created.
        profile_only = self.create_user(
            "invariant_profile_only_write",
            group=self.old_group,
            membership_unit=None,
        )
        PlanEnrollment.objects.create(user=profile_only, active_plan=self.active_plan)

        self.client.login(username=profile_only.username, password="TestPass123!")
        before_count = ReflectionComment.objects.count()
        response = self.client.post(
            reverse("add_comment", args=[self.active_plan.id, self.day.id, 0]),
            {
                "body": "Profile-only forced group post",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ReflectionComment.objects.count(), before_count)

    def test_wrong_type_membership_unit_has_no_group_write_path(self):
        # CS-CORE.4G.3 (coverage 4): an active primary membership on a non-small-group
        # unit does not offer group sharing and a forced group POST is rejected.
        district_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="INV_DISTRICT",
            name="Invariant District Unit",
        )
        author = self.create_user(
            "invariant_wrong_type",
            membership_unit=district_unit,
        )
        PlanEnrollment.objects.create(user=author, active_plan=self.active_plan)

        form = ReflectionCommentForm(
            {
                "body": "Wrong-type attempted group post",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
            user=author,
            language="en",
        )
        self.assertNotIn(
            ReflectionComment.VISIBILITY_GROUP,
            self._group_choice_values(form),
        )
        self.assertFalse(form.is_valid())

        self.client.login(username=author.username, password="TestPass123!")
        before_count = ReflectionComment.objects.count()
        response = self.client.post(
            reverse("add_comment", args=[self.active_plan.id, self.day.id, 0]),
            {
                "body": "Wrong-type forced group post",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ReflectionComment.objects.count(), before_count)

    def test_multiple_active_primary_memberships_fail_closed_for_write(self):
        # CS-CORE.4G.3 (coverage 5): two active primary memberships are ambiguous and
        # fail closed for the write path, mirroring the read-path gate. bulk_create
        # bypasses the single-active-primary model validation.
        author = self.create_user("invariant_multi_write", membership_unit=None)
        today = timezone.localdate()
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=author,
                    unit=self.old_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
                ChurchStructureMembership(
                    user=author,
                    unit=self.new_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
            ]
        )
        PlanEnrollment.objects.create(user=author, active_plan=self.active_plan)

        form = ReflectionCommentForm(
            {
                "body": "Ambiguous membership group post",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
            user=author,
            language="en",
        )
        self.assertNotIn(
            ReflectionComment.VISIBILITY_GROUP,
            self._group_choice_values(form),
        )
        self.assertFalse(form.is_valid())

        self.client.login(username=author.username, password="TestPass123!")
        before_count = ReflectionComment.objects.count()
        response = self.client.post(
            reverse("add_comment", args=[self.active_plan.id, self.day.id, 0]),
            {
                "body": "Ambiguous forced group post",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ReflectionComment.objects.count(), before_count)

    def test_existing_group_edit_preserves_snapshot_after_membership_transfer(self):
        # CS-CORE.4G.3 (coverage 9): an existing group post edited group -> group
        # preserves its original structure_unit_at_post under Policy C, even after
        # the author's active primary membership transfers.
        post = self.make_reflection(
            user=self.author,
            body="Existing group snapshot preserved",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
            structure_unit=self.old_unit,
        )
        ChurchStructureMembership.objects.filter(user=self.author).update(
            unit=self.new_unit,
        )

        self.client.login(username=self.author.username, password="TestPass123!")
        response = self.client.post(
            reverse("edit_comment", args=[post.id]),
            {
                "body": "Existing group edited after transfer",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()

        self.assertEqual(post.body, "Existing group edited after transfer")
        self.assertEqual(post.structure_unit_at_post, self.old_unit)
        self.assertTrue(post.can_be_seen_by(self.old_group_member))
        self.assertFalse(post.can_be_seen_by(self.new_group_member))
        self.assertTrue(post.can_be_seen_by(self.author))

    def test_passage_wall_label_uses_structure_unit_without_legacy_fallback(self):
        # REFLECTION-MIRROR.1G/1H: the passage wall group label relies solely on the
        # structure snapshot. There is no legacy SmallGroup fallback, so a
        # structure-native row renders its unit name and a row that lacks the
        # structure snapshot renders no group label. Legacy SmallGroup names are
        # never rendered.
        self.make_reflection(
            user=self.author,
            body="Structure-native labelled post",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            structure_unit=self.old_unit,
        )
        self.make_reflection(
            user=self.author,
            body="Post with no structure snapshot",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            structure_unit=None,
        )
        self.make_reflection(
            user=self.author,
            body="Another structure-native labelled post",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            structure_unit=self.new_unit,
        )

        self.client.login(username=self.author.username, password="TestPass123!")
        response = self.client.get(
            reverse("passage_wall"),
            {"ref": "John 1", "tab": "my"},
        )
        self.assertEqual(response.status_code, 200)
        # Structure-native rows render their unit name.
        self.assertContains(response, self.old_unit.name)
        self.assertContains(response, self.new_unit.name)
        # A legacy SmallGroup name is never rendered as a group label.
        self.assertNotContains(response, self.old_group_name)
        self.assertNotContains(response, self.other_group_name)


class GroupProgressPrivacyInvariantTests(TestCase):
    """CS-CORE.4C locks current group-progress roster and permission behavior."""

    def setUp(self):
        # CS-CORE.2D-B + LEGACY-STRUCTURE-SURFACE-RETIRE.1A: progress
        # permission/access is structure-aware and the list/selection surface is
        # canonical-unit based (district unit -> small-group unit).
        self.district_unit = self.create_unit(
            "INV-DIST", unit_type=ChurchStructureUnit.UNIT_DISTRICT
        )
        self.other_district_unit = self.create_unit(
            "INV-OTHER-DIST", unit_type=ChurchStructureUnit.UNIT_DISTRICT
        )
        self.group_unit = self.create_unit(
            "INV-PROGRESS-GROUP", parent=self.district_unit
        )
        self.other_group_unit = self.create_unit(
            "INV-PROGRESS-OTHER", parent=self.other_district_unit
        )

        self.viewer = self.create_user("progress_viewer")
        # The viewer reaches the page via a group-leader role on self.group_unit (not via
        # membership), so they can view it without appearing in the membership roster.
        # ROLE-RETIRE.1B: scoped role access requires an explicit structure_unit.
        ChurchRoleAssignment.objects.create(
            user=self.viewer,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )
        self.same_group_member = self.create_user("progress_same")
        self.profile_only_member = self.create_user("progress_profile_only")
        self.other_group_member = self.create_user("progress_other")
        self.no_group_user = self.create_user("progress_no_group")
        self.membership_only_user = self.create_user("progress_membership_only")
        self.staff = User.objects.create_user(
            username="progress_staff",
            password="TestPass123!",
            is_staff=True,
        )

        self.create_membership(self.membership_only_user, self.group_unit)

        self.plan = ReadingPlan.objects.create(
            name="Invariant Progress Plan",
            is_active=True,
        )
        self.day = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=1,
            reading_text="John 1",
            memory_verse="John 1:1",
        )
        self.active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=timezone.localdate(),
            title="Invariant Progress Active Plan",
        )

        for user in [
            self.viewer,
            self.same_group_member,
            self.profile_only_member,
            self.other_group_member,
            self.no_group_user,
            self.membership_only_user,
        ]:
            PlanEnrollment.objects.create(user=user, active_plan=self.active_plan)

    def create_user(self, username, *, group=None):
        user = User.objects.create_user(username=username, password="TestPass123!")
        return user

    def create_unit(self, code, *, unit_type=None, parent=None):
        return ChurchStructureUnit.objects.create(
            unit_type=unit_type or ChurchStructureUnit.UNIT_SMALL_GROUP,
            code=code,
            name=code,
            parent=parent,
        )

    def create_membership(self, user, unit):
        return ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

    def progress_response_for(self, user, *, unit=None):
        self.client.login(username=user.username, password="TestPass123!")
        params = {}
        if unit is not None:
            params["group"] = unit.id
        response = self.client.get(reverse("my_group_progress"), params)
        self.assertEqual(response.status_code, 200)
        self.client.logout()
        return response

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def row_usernames(self, response):
        return {
            row["member"].username
            for row in response.context["member_rows"]
        }

    def accessible_group_unit_ids(self, user):
        return set(get_accessible_progress_groups(user).values_list("id", flat=True))

    def test_roster_now_membership_core_driven_not_profile(self):
        # CS-CORE.4F.1 switched the visible roster source: member_rows now follows
        # active primary ChurchStructureMembership, not legacy Profile.small_group.
        # Only progress_membership_only has an active primary membership under the
        # group unit; the profile-only members are excluded.
        response = self.progress_response_for(self.viewer, unit=self.group_unit)

        expected_unit = self.group_unit
        self.assertEqual(response.context["selected_group"], expected_unit)
        self.assertEqual(
            self.row_usernames(response),
            {"progress_membership_only"},
        )
        self.assertNotIn("progress_viewer", self.row_usernames(response))
        self.assertNotIn("progress_same", self.row_usernames(response))
        self.assertNotIn("progress_profile_only", self.row_usernames(response))
        self.assertNotIn("progress_other", self.row_usernames(response))
        self.assertNotIn("progress_no_group", self.row_usernames(response))

    def test_membership_only_viewer_gets_own_group_progress(self):
        # CS-CORE.2D-B: own-group access now comes from the active primary membership.
        # A membership-only viewer (membership on the group unit) can view their own
        # group page and appears in the membership-core roster.
        membership_only_viewer = self.create_user("progress_membership_viewer")
        self.create_membership(membership_only_viewer, self.group_unit)
        PlanEnrollment.objects.create(
            user=membership_only_viewer, active_plan=self.active_plan
        )

        self.assertEqual(
            self.accessible_group_unit_ids(membership_only_viewer), {self.group_unit.id}
        )
        response = self.progress_response_for(membership_only_viewer)

        expected_unit = self.group_unit
        self.assertEqual(response.context["selected_group"], expected_unit)
        self.assertIn("progress_membership_viewer", self.row_usernames(response))

    def test_profile_only_viewer_gets_safe_empty_progress_state(self):
        self.set_language("en")
        # CS-CORE.2D-B: Profile.small_group no longer grants progress access. A viewer
        # with only a legacy profile group (no membership, no role) gets the safe
        # empty state.
        profile_only_viewer = self.create_user(
            "progress_profile_only_viewer"
        )
        PlanEnrollment.objects.create(
            user=profile_only_viewer, active_plan=self.active_plan
        )

        self.assertEqual(self.accessible_group_unit_ids(profile_only_viewer), set())
        response = self.progress_response_for(profile_only_viewer)

        self.assertIsNone(response.context["selected_group"])
        self.assertEqual(list(response.context["member_rows"]), [])
        self.assertContains(response, "You are not assigned to a small group yet.")

    def test_role_and_membership_grant_only_their_own_groups_not_siblings(self):
        # CS-CORE.2D-B: the viewer's group-leader role grants self.group_unit; an added
        # ordinary membership grants only its own mapped unit (other_group_unit); neither
        # grants a third sibling group under the same district.
        sibling_unit = self.create_unit("INV-SIBLING", parent=self.district_unit)
        self.create_membership(self.viewer, self.other_group_unit)

        self.assertEqual(
            self.accessible_group_unit_ids(self.viewer),
            {self.group_unit.id, self.other_group_unit.id},
        )
        self.assertTrue(can_view_group_progress_for(self.viewer, self.group_unit))
        self.assertTrue(can_view_group_progress_for(self.viewer, self.other_group_unit))
        self.assertFalse(can_view_group_progress_for(self.viewer, sibling_unit))

    def test_group_leader_can_view_assigned_group_only(self):
        leader = self.create_user("progress_group_leader")
        # ROLE-RETIRE.1B: scoped role access requires an explicit structure_unit.
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.other_group_unit,
        )

        self.assertFalse(can_view_group_progress_for(leader, self.group_unit))
        self.assertTrue(can_view_group_progress_for(leader, self.other_group_unit))
        self.assertEqual(
            self.accessible_group_unit_ids(leader), {self.other_group_unit.id}
        )

    def test_structure_district_leader_can_view_descendant_groups_only(self):
        district_group_b_unit = self.create_unit(
            "INV-DIST-GROUP-B", parent=self.district_unit
        )
        leader = self.create_user("progress_district_leader")
        # ROLE-RETIRE.1B: scoped role access requires an explicit structure_unit.
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            structure_unit=self.district_unit,
        )

        self.assertTrue(can_view_group_progress_for(leader, self.group_unit))
        self.assertTrue(can_view_group_progress_for(leader, district_group_b_unit))
        self.assertFalse(can_view_group_progress_for(leader, self.other_group_unit))
        self.assertEqual(
            self.accessible_group_unit_ids(leader),
            {self.group_unit.id, district_group_b_unit.id},
        )

    def test_staff_and_all_progress_role_can_view_all_active_groups(self):
        pastor = self.create_user("progress_pastor")
        ChurchRoleAssignment.objects.create(
            user=pastor,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        self.assertTrue(can_view_group_progress_for(self.staff, self.group_unit))
        self.assertTrue(can_view_group_progress_for(self.staff, self.other_group_unit))
        self.assertTrue(can_view_group_progress_for(pastor, self.group_unit))
        self.assertTrue(can_view_group_progress_for(pastor, self.other_group_unit))

        response = self.progress_response_for(self.staff, unit=self.other_group_unit)

        self.assertEqual(response.context["selected_group"], self.other_group_unit)


class GroupProgressRosterSourceSwitchTests(TestCase):
    """CS-CORE.4F.1 locks the group-progress roster-only source switch.

    The visible roster (``member_rows`` in ``reading.views.my_group_progress``) now
    uses the membership-core candidate (single active primary
    ``ChurchStructureMembership`` matched to the selected group's mapped small-group
    unit or a descendant) instead of legacy ``Profile.small_group``. Permission and
    the accessible group list are canonical-unit based, and ordinary membership grants
    own-group access only (privacy invariant 5).

    (The default *selected* group later switched to a permission-fenced
    membership-core candidate in CS-CORE.4F.2; see
    ``GroupProgressDefaultSourceSwitchTests``. The default-group cases in this 4F.1
    class still hold because their membership candidate is not in the viewer's
    legacy-accessible groups, so the 4F.2 fence excludes it and the legacy default
    applies — which is exactly the permission fence those cases exercise.)
    """

    def setUp(self):
        self.group_unit = self.create_unit("SWITCH-GROUP")
        self.other_group_unit = self.create_unit("SWITCH-OTHER")

        # Viewer has own-group access via active primary membership under the group
        # unit, so they can both view the page and appear in the membership-core roster.
        self.viewer = self.create_user("switch_viewer")
        self.create_membership(self.viewer, self.group_unit)

        self.plan = ReadingPlan.objects.create(name="Switch Plan", is_active=True)
        self.day = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=1,
            reading_text="John 1",
            memory_verse="John 1:1",
        )
        self.active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=timezone.localdate(),
            title="Switch Active Plan",
        )
        PlanEnrollment.objects.create(user=self.viewer, active_plan=self.active_plan)

    def create_user(self, username, *, group=None):
        user = User.objects.create_user(username=username, password="TestPass123!")
        return user

    def create_unit(self, code, *, unit_type=None, parent=None):
        return ChurchStructureUnit.objects.create(
            unit_type=unit_type or ChurchStructureUnit.UNIT_SMALL_GROUP,
            code=code,
            name=code,
            parent=parent,
        )

    def create_membership(self, user, unit):
        return ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

    def progress_response_for(self, user, *, unit=None):
        self.client.login(username=user.username, password="TestPass123!")
        params = {}
        if unit is not None:
            params["group"] = unit.id
        response = self.client.get(reverse("my_group_progress"), params)
        self.assertEqual(response.status_code, 200)
        self.client.logout()
        return response

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def row_usernames(self, response):
        return {row["member"].username for row in response.context["member_rows"]}

    def accessible_group_unit_ids(self, user):
        return set(get_accessible_progress_groups(user).values_list("id", flat=True))

    def test_roster_includes_membership_core_user_without_legacy_profile_group(self):
        # User has an active primary membership under the group unit but no legacy
        # Profile.small_group; the membership-core roster source must include them.
        membership_user = self.create_user("switch_membership")
        self.create_membership(membership_user, self.group_unit)
        PlanEnrollment.objects.create(
            user=membership_user, active_plan=self.active_plan
        )

        response = self.progress_response_for(self.viewer, unit=self.group_unit)

        self.assertIn("switch_membership", self.row_usernames(response))
        membership_user.refresh_from_db()

    def test_legacy_profile_only_user_excluded_from_roster(self):
        # User has no active primary membership; the
        # membership-core roster source must exclude them.
        self.create_user("switch_profile_only")

        response = self.progress_response_for(self.viewer, unit=self.group_unit)

        expected_unit = self.group_unit
        self.assertEqual(response.context["selected_group"], expected_unit)
        self.assertNotIn("switch_profile_only", self.row_usernames(response))
        # Sanity: the membership-core roster member is still present.
        self.assertIn("switch_viewer", self.row_usernames(response))

    def test_membership_grants_own_group_only_not_sibling(self):
        # CS-CORE.2D-B: an ordinary membership now grants progress access to its own
        # mapped group, but never to a different group.
        ordinary = self.create_user("switch_ordinary")
        self.create_membership(ordinary, self.group_unit)

        self.assertTrue(can_view_group_progress_for(ordinary, self.group_unit))
        self.assertFalse(can_view_group_progress_for(ordinary, self.other_group_unit))
        self.assertEqual(
            self.accessible_group_unit_ids(ordinary), {self.group_unit.id}
        )

        # Selecting an inaccessible other group falls back to the accessible own group.
        response = self.progress_response_for(ordinary, unit=self.other_group_unit)
        expected_unit = self.group_unit
        self.assertEqual(response.context["selected_group"], expected_unit)

    def test_default_selected_group_is_membership_own_group(self):
        # CS-CORE.2D-B: with no ?group=, the default selected group is the viewer's
        # membership-core own group (now both the access source and the 4F.2 default).
        dual = self.create_user("switch_dual")
        self.create_membership(dual, self.group_unit)
        PlanEnrollment.objects.create(user=dual, active_plan=self.active_plan)

        response = self.progress_response_for(dual)

        expected_unit = self.group_unit
        self.assertEqual(response.context["selected_group"], expected_unit)

    def test_accessible_group_selector_orders_by_visible_group_name(self):
        zeta = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="AAA-CODE",
            name="Zeta Group",
            name_en="Zeta Group",
        )
        alpha = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="ZZZ-CODE",
            name="Alpha Group",
            name_en="Alpha Group",
        )
        staff = User.objects.create_user(
            username="switch_staff",
            password="TestPass123!",
            is_staff=True,
        )
        self.set_language("en")

        response = self.progress_response_for(staff)

        group_ids = [group.id for group in response.context["groups"]]
        self.assertLess(group_ids.index(alpha.id), group_ids.index(zeta.id))

    def test_group_progress_member_rows_order_by_visible_identity(self):
        zed = User.objects.create_user(
            username="aaa_member",
            password="TestPass123!",
            first_name="Zed",
            last_name="Member",
        )
        amy = User.objects.create_user(
            username="zzz_member",
            password="TestPass123!",
            first_name="Amy",
            last_name="Member",
        )
        self.create_membership(zed, self.group_unit)
        self.create_membership(amy, self.group_unit)
        PlanEnrollment.objects.create(user=zed, active_plan=self.active_plan)
        PlanEnrollment.objects.create(user=amy, active_plan=self.active_plan)

        response = self.progress_response_for(self.viewer, unit=self.group_unit)

        member_names = [
            row["member"].get_full_name()
            for row in response.context["member_rows"]
        ]
        self.assertLess(
            member_names.index("Amy Member"),
            member_names.index("Zed Member"),
        )

    def test_inaccessible_selected_unit_falls_back_without_crash(self):
        # A staff viewer cannot select a non-small-group unit through the list; the
        # invalid explicit ?group= unit id falls back to the first active small-group
        # unit without crashing.
        staff = User.objects.create_user(
            username="switch_invalid_unit_staff",
            password="TestPass123!",
            is_staff=True,
        )
        district_unit = self.create_unit(
            "SWITCH-DISTRICT",
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
        )

        response = self.progress_response_for(staff, unit=district_unit)

        expected_unit = self.group_unit
        self.assertEqual(response.context["selected_group"], expected_unit)

    def test_multiple_active_primary_membership_user_excluded_from_roster(self):
        # User with two active primary memberships is ambiguous and fails closed,
        # so they are excluded from the membership-core roster.
        ambiguous = self.create_user("switch_ambiguous")
        today = timezone.localdate()
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=ambiguous,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
                ChurchStructureMembership(
                    user=ambiguous,
                    unit=self.other_group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
            ]
        )
        PlanEnrollment.objects.create(user=ambiguous, active_plan=self.active_plan)

        response = self.progress_response_for(self.viewer, unit=self.group_unit)

        self.assertNotIn("switch_ambiguous", self.row_usernames(response))
        self.assertIn("switch_viewer", self.row_usernames(response))

    def test_roster_helper_includes_descendant_unit_members(self):
        # The roster helper includes members whose active primary membership is in a
        # descendant unit of the selected group's mapped small-group unit.
        child_unit = self.create_unit("SWITCH-CHILD", parent=self.group_unit)
        child_member = self.create_user("switch_child")
        self.create_membership(child_member, child_unit)

        selected_unit = self.group_unit
        roster = get_membership_core_progress_roster_users(selected_unit)
        usernames = set(roster.values_list("username", flat=True))

        self.assertIn("switch_child", usernames)
        self.assertIn("switch_viewer", usernames)

    def test_roster_helper_fails_closed_for_none_and_wrong_type_unit(self):
        self.assertEqual(
            list(get_membership_core_progress_roster_users(None)), []
        )
        district_unit = self.create_unit(
            "SWITCH-HELPER-DISTRICT",
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
        )
        self.assertEqual(
            list(get_membership_core_progress_roster_users(district_unit)), []
        )


class GroupProgressDefaultSourceSwitchTests(TestCase):
    """CS-CORE.4F.2 + READING-STRUCT.1D lock the default-selected-group source.

    With no explicit ``?group=``, ``reading.views.my_group_progress`` uses the
    permission-fenced membership-core default candidate (single active primary
    ``ChurchStructureMembership`` on one active small-group unit). The
    candidate is **permission-fenced**: it is only used when it is already in the
    ``get_accessible_progress_groups()`` result, so ordinary membership grants only
    the user's own small-group unit and never expands role-scoped access.

    READING-STRUCT.1D removed the former legacy ``Profile.small_group`` default
    fallback: when there is no membership candidate the default is simply the first
    accessible group (role/permission driven), and ordinary users with no
    resolvable membership fall through to the safe no-group state.
    ``Profile.small_group`` is no longer a group-progress runtime source. Explicit
    ``?group=`` remains the URL-compatible parameter name, but its value is now a
    canonical small-group unit id; the visible roster stays the membership-core
    source switched in CS-CORE.4F.1.
    """

    def setUp(self):
        # CS-CORE.2D-B: district-leader scopes resolve through the mapped district
        # unit, so unit_a/unit_b sit under the district unit and unit_c under the
        # other district unit.
        self.district_unit = self.create_unit(
            "DEF-DIST", unit_type=ChurchStructureUnit.UNIT_DISTRICT
        )
        self.other_district_unit = self.create_unit(
            "DEF-OTHER-DIST", unit_type=ChurchStructureUnit.UNIT_DISTRICT
        )
        self.unit_a = self.create_unit("DEF-A", parent=self.district_unit)
        self.unit_b = self.create_unit("DEF-B", parent=self.district_unit)
        self.unit_c = self.create_unit("DEF-C", parent=self.other_district_unit)
        # unit_c is in another district: out of a self.district_unit leader's scope.

        self.plan = ReadingPlan.objects.create(name="Default Plan", is_active=True)
        self.day = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=1,
            reading_text="John 1",
            memory_verse="John 1:1",
        )
        self.active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=timezone.localdate(),
            title="Default Active Plan",
        )

    def create_user(self, username, *, group=None):
        user = User.objects.create_user(username=username, password="TestPass123!")
        return user

    def create_unit(self, code, *, unit_type=None, parent=None):
        return ChurchStructureUnit.objects.create(
            unit_type=unit_type or ChurchStructureUnit.UNIT_SMALL_GROUP,
            code=code,
            name=code,
            parent=parent,
        )

    def create_membership(self, user, unit):
        return ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

    def make_district_leader(self, user, district_unit):
        # ROLE-RETIRE.1B: scoped role access requires an explicit structure_unit.
        ChurchRoleAssignment.objects.create(
            user=user,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            structure_unit=district_unit,
        )

    def progress_response_for(self, user, *, unit=None):
        self.client.login(username=user.username, password="TestPass123!")
        params = {}
        if unit is not None:
            params["group"] = unit.id
        response = self.client.get(reverse("my_group_progress"), params)
        self.assertEqual(response.status_code, 200)
        self.client.logout()
        return response

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def row_usernames(self, response):
        return {row["member"].username for row in response.context["member_rows"]}

    def accessible_group_unit_ids(self, user):
        return set(get_accessible_progress_groups(user).values_list("id", flat=True))

    def test_default_uses_membership_core_when_candidate_is_legacy_accessible(self):
        # District leader over self.district_unit can access unit_a and unit_b.
        # The single active primary membership points to unit_b. With no ?group=,
        # the permission-fenced membership-core candidate (unit_b) is used.
        leader = self.create_user("default_leader")
        self.make_district_leader(leader, self.district_unit)
        self.create_membership(leader, self.unit_b)

        self.assertEqual(
            self.accessible_group_unit_ids(leader),
            {self.unit_a.id, self.unit_b.id},
        )

        response = self.progress_response_for(leader)

        self.assertEqual(response.context["selected_group"], self.unit_b)
        self.assertNotEqual(response.context["selected_group"], self.unit_a)

    def test_ordinary_membership_default_selects_own_group(self):
        # CS-CORE.2D-B: an ordinary user (no role) with an active primary membership in
        # unit_b now has own-group access to unit_b, and with no ?group= it is
        # the default selected group.
        user = self.create_user("default_ordinary")
        self.create_membership(user, self.unit_b)

        self.assertEqual(self.accessible_group_unit_ids(user), {self.unit_b.id})

        response = self.progress_response_for(user)

        self.assertEqual(response.context["selected_group"], self.unit_b)

    def test_membership_with_wrong_type_unit_gets_empty_state(self):
        self.set_language("en")
        # CS-CORE.2D-B: a membership whose unit is not a small-group unit yields no
        # own-group access and (with no role) the safe empty state.
        user = self.create_user("default_membership_only")
        wrong_type_unit = self.create_unit(
            "DEF-EMPTY-WRONG-TYPE",
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
        )
        self.create_membership(user, wrong_type_unit)

        self.assertEqual(self.accessible_group_unit_ids(user), set())

        response = self.progress_response_for(user)

        self.assertIsNone(response.context["selected_group"])
        self.assertEqual(list(response.context["member_rows"]), [])
        self.assertContains(response, "You are not assigned to a small group yet.")

    def test_explicit_accessible_group_overrides_membership_default(self):
        # District leader accesses unit_a and unit_b; membership default is unit_b.
        # An explicit accessible ?group=unit_a stays authoritative.
        leader = self.create_user("default_explicit")
        self.make_district_leader(leader, self.district_unit)
        self.create_membership(leader, self.unit_b)

        response = self.progress_response_for(leader, unit=self.unit_a)

        self.assertEqual(response.context["selected_group"], self.unit_a)

    def test_explicit_inaccessible_group_falls_through_to_membership_default(self):
        # District leader accesses unit_a and unit_b but not unit_c (other
        # district). An explicit inaccessible ?group=unit_c falls through the default
        # logic, which now selects the permission-fenced membership default unit_b.
        leader = self.create_user("default_explicit_bad")
        self.make_district_leader(leader, self.district_unit)
        self.create_membership(leader, self.unit_b)

        self.assertNotIn(self.unit_c.id, self.accessible_group_unit_ids(leader))

        response = self.progress_response_for(leader, unit=self.unit_c)

        self.assertEqual(response.context["selected_group"], self.unit_b)

    def test_multiple_active_primary_memberships_fall_through_to_first_accessible(self):
        # READING-STRUCT.1D: two active primary memberships are ambiguous, so the
        # membership candidate fails closed. No legacy profile group is
        # consulted; the default falls through to the first accessible group
        # (unit_a, the leader's first role-scoped unit by name).
        leader = self.create_user("default_ambiguous")
        self.make_district_leader(leader, self.district_unit)
        today = timezone.localdate()
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=leader,
                    unit=self.unit_a,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
                ChurchStructureMembership(
                    user=leader,
                    unit=self.unit_b,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
            ]
        )

        response = self.progress_response_for(leader)

        # First accessible unit (unit_a), not the ambiguous membership unit_b.
        self.assertEqual(response.context["selected_group"], self.unit_a)
        self.assertNotEqual(response.context["selected_group"], self.unit_b)

    def test_wrong_type_membership_unit_falls_through_to_first_accessible(self):
        # READING-STRUCT.1D: the active primary membership maps to no active
        # small-group unit, so the candidate fails closed. The default falls through
        # to the first accessible unit.
        leader = self.create_user("default_wrong_type")
        self.make_district_leader(leader, self.district_unit)
        wrong_type_unit = self.create_unit(
            "DEF-WRONG-TYPE",
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
        )
        self.create_membership(leader, wrong_type_unit)

        response = self.progress_response_for(leader)

        # First accessible unit (unit_a), not the wrong-type membership unit.
        self.assertEqual(response.context["selected_group"], self.unit_a)
        self.assertNotEqual(response.context["selected_group"], self.unit_b)

    def test_ordinary_profile_group_without_membership_gets_no_group_progress(self):
        self.set_language("en")
        # READING-STRUCT.1D: an ordinary user with no active primary membership gets
        # NO group progress via profile fallback -- accessible is empty and the safe
        # no-group state shows.
        user = self.create_user("default_profile_only")

        self.assertEqual(self.accessible_group_unit_ids(user), set())

        response = self.progress_response_for(user)

        self.assertIsNone(response.context["selected_group"])
        self.assertEqual(list(response.context["member_rows"]), [])
        self.assertContains(response, "You are not assigned to a small group yet.")

    def test_ordinary_membership_uses_membership_unit(self):
        # READING-STRUCT.1D: the active primary membership unit is the runtime source
        # and legacy profile-group fallback is never used.
        user = self.create_user("default_membership_unit")
        self.create_membership(user, self.unit_b)

        # Ordinary own-group access is membership-core: only unit_b is accessible.
        self.assertEqual(self.accessible_group_unit_ids(user), {self.unit_b.id})

        response = self.progress_response_for(user)

        self.assertEqual(response.context["selected_group"], self.unit_b)
        self.assertNotEqual(response.context["selected_group"], self.unit_a)

    def test_ordinary_ended_membership_fails_closed_to_no_group(self):
        self.set_language("en")
        # READING-STRUCT.1D: an ended (non-active) primary membership does not count,
        # and Profile.small_group is not a fallback, so the user gets no group
        # progress rather than a legacy fallback.
        user = self.create_user("default_ended")
        ChurchStructureMembership.objects.create(
            user=user,
            unit=self.unit_b,
            status=ChurchStructureMembership.STATUS_ENDED,
            is_primary=True,
            start_date=timezone.localdate() - timedelta(days=10),
            end_date=timezone.localdate() - timedelta(days=1),
        )

        self.assertEqual(self.accessible_group_unit_ids(user), set())

        response = self.progress_response_for(user)

        self.assertIsNone(response.context["selected_group"])
        self.assertContains(response, "You are not assigned to a small group yet.")

    def test_ordinary_membership_grants_only_own_group_not_others(self):
        # CS-CORE.2D-B: an active primary membership in unit_a grants own-group
        # access to unit_a only, never to other units (unit_b/unit_c).
        user = self.create_user("default_no_expand")
        self.create_membership(user, self.unit_a)

        self.assertEqual(self.accessible_group_unit_ids(user), {self.unit_a.id})
        self.assertTrue(can_view_group_progress_for(user, self.unit_a))
        self.assertFalse(can_view_group_progress_for(user, self.unit_b))
        self.assertFalse(can_view_group_progress_for(user, self.unit_c))

    def test_default_helper_is_permission_fenced(self):
        # Direct helper checks: a mapped candidate is only returned when it is in the
        # provided accessible set, and never when the set omits it or is None.
        user = self.create_user("default_helper")
        self.create_membership(user, self.unit_b)

        self.assertEqual(
            get_membership_core_default_progress_group(
                user, accessible_groups=[self.unit_a, self.unit_b]
            ),
            self.unit_b,
        )
        self.assertIsNone(
            get_membership_core_default_progress_group(
                user, accessible_groups=[self.unit_a]
            )
        )
        self.assertIsNone(
            get_membership_core_default_progress_group(user, accessible_groups=None)
        )
        # Id-based accessible sets are accepted too.
        self.assertEqual(
            get_membership_core_default_progress_group(
                user, accessible_groups={self.unit_b.id}
            ),
            self.unit_b,
        )


class ImportReadingPlanCommandTests(TestCase):
    def setUp(self):
        self.temp_files = []

    def tearDown(self):
        for file_path in self.temp_files:
            if os.path.exists(file_path):
                os.remove(file_path)

    def make_csv(self, content):
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            encoding="utf-8",
            newline="",
            delete=False,
        )
        temp_file.write(content)
        temp_file.close()

        self.temp_files.append(temp_file.name)
        return temp_file.name

    def test_import_reading_plan_creates_plan_and_days(self):
        csv_path = self.make_csv(
            "day_number,reading_text,memory_verse\n"
            "1,John 1,John 1:1\n"
            "2,John 2,John 2:11\n"
        )

        call_command(
            "import_reading_plan",
            "--name",
            "Imported John Plan",
            "--file",
            csv_path,
        )

        plan = ReadingPlan.objects.get(name="Imported John Plan")

        self.assertEqual(plan.days.count(), 2)
        self.assertTrue(
            ReadingPlanDay.objects.filter(
                plan=plan,
                day_number=1,
                reading_text="John 1",
                memory_verse="John 1:1",
            ).exists()
        )

    def test_import_reading_plan_with_start_date_creates_active_plan(self):
        csv_path = self.make_csv(
            "day_number,reading_text,memory_verse\n"
            "1,John 1,John 1:1\n"
        )

        call_command(
            "import_reading_plan",
            "--name",
            "Plan With Active Run",
            "--file",
            csv_path,
            "--start-date",
            "2026-05-12",
            "--active-title",
            "May Active Run",
        )

        plan = ReadingPlan.objects.get(name="Plan With Active Run")

        self.assertTrue(
            ActivePlan.objects.filter(
                plan=plan,
                start_date="2026-05-12",
                title="May Active Run",
            ).exists()
        )

    def test_import_reading_plan_rejects_duplicate_day_numbers(self):
        csv_path = self.make_csv(
            "day_number,reading_text,memory_verse\n"
            "1,John 1,John 1:1\n"
            "1,John 2,John 2:11\n"
        )

        with self.assertRaises(CommandError):
            call_command(
                "import_reading_plan",
                "--name",
                "Bad Duplicate Plan",
                "--file",
                csv_path,
            )

    def test_import_reading_plan_rejects_blank_reading_text(self):
        csv_path = self.make_csv(
            "day_number,reading_text,memory_verse\n"
            "1,,John 1:1\n"
        )

        with self.assertRaises(CommandError):
            call_command(
                "import_reading_plan",
                "--name",
                "Bad Blank Plan",
                "--file",
                csv_path,
            )

    def test_import_reading_plan_replace_overwrites_existing_days(self):
        plan = ReadingPlan.objects.create(
            name="Replace Plan",
            description="Old",
            is_active=True,
        )

        ReadingPlanDay.objects.create(
            plan=plan,
            day_number=1,
            reading_text="Old Reading",
            memory_verse="Old Verse",
        )

        csv_path = self.make_csv(
            "day_number,reading_text,memory_verse\n"
            "1,New Reading,New Verse\n"
            "2,Second Reading,\n"
        )

        call_command(
            "import_reading_plan",
            "--name",
            "Replace Plan",
            "--file",
            csv_path,
            "--replace",
        )

        plan.refresh_from_db()

        self.assertEqual(plan.days.count(), 2)
        self.assertTrue(
            ReadingPlanDay.objects.filter(
                plan=plan,
                day_number=1,
                reading_text="New Reading",
                memory_verse="New Verse",
            ).exists()
        )
        self.assertFalse(
            ReadingPlanDay.objects.filter(
                plan=plan,
                reading_text="Old Reading",
            ).exists()
        )

class BibleReadingFlowTests(TestCase):
    def setUp(self):
        # CS-CORE.4G.2: group reflection visibility is membership-core, so the
        # group is mapped to a structure unit. Ordinary-visibility tests below
        # add active primary memberships and stamp the structure snapshot.
        self.group_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RAINBOW4_FLOW",
            name="Rainbow 4 Flow Unit",
        )
        self.group = self.group_unit

        self.user = User.objects.create_user(
            username="levin",
            email="levin@example.com",
            password="testpass123",
        )

        self.other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="testpass123",
        )

        self.admin = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="testpass123",
            is_staff=True,
        )

        self.plan = ReadingPlan.objects.create(
            name="Test 7-Day Bible Reading",
            description="Test plan",
            is_active=True,
        )

        self.day1 = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=1,
            reading_text="John 1",
            memory_verse="John 1:1",
        )

        self.day2 = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=2,
            reading_text="John 2",
            memory_verse="John 2:11",
        )

        self.future_day = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=10,
            reading_text="John 10",
            memory_verse="John 10:11",
        )

        self.active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=timezone.localdate(),
            title="May Test Plan",
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def create_group_unit(self, code):
        """Create a canonical small-group ChurchStructureUnit for tests."""
        return ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code=code,
            name=code,
        )

    def add_active_primary_membership(self, user, unit):
        return ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

    def create_guide_publisher(self, username="pastor_user"):
        publisher = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="testpass123",
        )
        ChurchRoleAssignment.objects.create(
            user=publisher,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )
        return publisher

    def test_login_required_for_home(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_user_can_join_active_plan(self):
        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("join_active_plan", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            PlanEnrollment.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
            ).exists()
        )

    def test_user_cannot_join_same_plan_twice(self):
        self.client.login(username="levin", password="testpass123")

        self.client.post(reverse("join_active_plan", args=[self.active_plan.id]))
        self.client.post(reverse("join_active_plan", args=[self.active_plan.id]))

        count = PlanEnrollment.objects.filter(
            user=self.user,
            active_plan=self.active_plan,
        ).count()

        self.assertEqual(count, 1)

    def test_unenrolled_user_cannot_view_plan_detail(self):
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_detail", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_intro_page_requires_login(self):
        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_enrolled_user_can_view_intro_page(self):
        self.set_language("en")
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Plan Introduction")
        self.assertContains(response, "May Test Plan")

    def test_non_enrolled_user_can_view_active_plan_intro(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Plan Introduction")

    def test_non_enrolled_user_sees_join_plan_button_on_intro(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("join_active_plan", args=[self.active_plan.id]))
        self.assertContains(response, "Join this plan")

    def test_enrolled_user_sees_calendar_and_schedule_actions_on_intro(self):
        self.set_language("en")
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "View Calendar")
        self.assertContains(response, "View Schedule")
        self.assertContains(response, reverse("active_plan_calendar", args=[self.active_plan.id]))
        self.assertContains(response, reverse("active_plan_detail", args=[self.active_plan.id]))

    def test_intro_shows_today_text_and_audio_actions_for_enrolled_user(self):
        self.set_language("en")
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Start Today’s Reading")
        self.assertContains(response, "Listen to Today’s Reading")
        self.assertContains(
            response,
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0]),
        )
        self.assertContains(
            response,
            reverse("audio_reader", args=[self.active_plan.id, self.day1.id, 0]),
        )

    def test_inactive_plan_intro_hidden_from_regular_non_enrolled_user(self):
        self.plan.is_active = False
        self.plan.save()

        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_staff_can_view_inactive_plan_intro(self):
        self.plan.is_active = False
        self.plan.save()

        self.set_language("en")
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Plan Introduction")

    def test_chinese_intro_page_shows_chinese_labels(self):
        self.set_language("zh")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "读经计划介绍")
        self.assertContains(response, "计划简介")
        self.assertContains(response, "如何读")
        self.assertContains(response, "读经指引")

    def test_english_intro_page_shows_english_labels(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Plan Introduction")
        self.assertContains(response, "Overview")
        self.assertContains(response, "How to Read")
        self.assertContains(response, "Reading Guidance")

    def test_regular_enrolled_user_can_view_published_guide_posts(self):
        self.set_language("en")
        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="本周提醒",
            title_en="This Week's Focus",
            body="中文内容",
            body_en="Notice the signs in John.",
            is_published=True,
            published_at=timezone.now(),
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Guides")
        self.assertContains(response, "This Week&#x27;s Focus")

    def test_regular_enrolled_user_cannot_view_draft_guide_posts(self):
        self.set_language("en")
        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="Draft Guide",
            body="Draft body",
            is_published=False,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Draft Guide")

    def test_non_enrolled_user_can_view_published_guides_for_active_plan(self):
        self.set_language("en")
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="Open Guide",
            body="Visible before joining.",
            is_published=True,
            published_at=timezone.now(),
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Open Guide")

    def test_non_enrolled_regular_user_cannot_view_guides_for_inactive_plan(self):
        self.plan.is_active = False
        self.plan.save()
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="Inactive Guide",
            body="Hidden",
            is_published=True,
            published_at=timezone.now(),
        )

        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_staff_can_view_guides_for_inactive_plan(self):
        self.plan.is_active = False
        self.plan.save()
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="Staff Guide",
            body="Visible to staff",
            is_published=True,
            published_at=timezone.now(),
        )

        self.set_language("en")
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff Guide")

    def test_user_without_publish_capability_cannot_access_create_guide_page(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("create_reading_guide_post", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)

    def test_user_with_pastor_role_can_access_create_guide_page(self):
        self.set_language("en")
        self.create_guide_publisher()
        self.client.login(username="pastor_user", password="testpass123")

        response = self.client.get(
            reverse("create_reading_guide_post", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New Reading Guide")

    def test_user_with_capability_can_create_published_guide_post(self):
        self.set_language("en")
        self.create_guide_publisher()
        self.client.login(username="pastor_user", password="testpass123")

        response = self.client.post(
            reverse("create_reading_guide_post", args=[self.active_plan.id]),
            {
                "title": "Published Guide",
                "title_en": "Published Guide EN",
                "body": "中文指引",
                "body_en": "English guide",
                "guide_type": ReadingGuidePost.GUIDE_GENERAL,
                "is_published": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        guide_post = ReadingGuidePost.objects.get(title="Published Guide")
        self.assertTrue(guide_post.is_published)
        self.assertIsNotNone(guide_post.published_at)

    def test_user_with_capability_can_create_draft_guide_post(self):
        self.set_language("en")
        self.create_guide_publisher()
        self.client.login(username="pastor_user", password="testpass123")

        response = self.client.post(
            reverse("create_reading_guide_post", args=[self.active_plan.id]),
            {
                "title": "Draft Guide",
                "body": "Draft body",
                "guide_type": ReadingGuidePost.GUIDE_GENERAL,
            },
        )

        self.assertEqual(response.status_code, 302)
        guide_post = ReadingGuidePost.objects.get(title="Draft Guide")
        self.assertFalse(guide_post.is_published)
        self.assertIsNone(guide_post.published_at)

    def test_draft_guide_visible_to_capability_user_but_not_regular_user(self):
        self.set_language("en")
        self.create_guide_publisher()
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="Internal Draft",
            body="Only publishers should see this.",
            is_published=False,
        )

        self.client.login(username="pastor_user", password="testpass123")
        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )
        self.assertContains(response, "Internal Draft")
        self.client.logout()

        self.client.login(username="levin", password="testpass123")
        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )
        self.assertNotContains(response, "Internal Draft")

    def test_user_with_capability_can_edit_guide_post(self):
        self.set_language("en")
        self.create_guide_publisher()
        guide_post = ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="Original Guide",
            body="Original body",
            is_published=False,
        )

        self.client.login(username="pastor_user", password="testpass123")

        response = self.client.post(
            reverse("edit_reading_guide_post", args=[guide_post.id]),
            {
                "title": "Edited Guide",
                "body": "Edited body",
                "guide_type": ReadingGuidePost.GUIDE_GENERAL,
                "is_published": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        guide_post.refresh_from_db()
        self.assertEqual(guide_post.title, "Edited Guide")
        self.assertTrue(guide_post.is_published)
        self.assertIsNotNone(guide_post.published_at)

    def test_user_with_capability_can_delete_guide_post(self):
        self.set_language("en")
        self.create_guide_publisher()
        guide_post = ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="Delete Me",
            body="Delete body",
            is_published=True,
            published_at=timezone.now(),
        )

        self.client.login(username="pastor_user", password="testpass123")

        response = self.client.post(
            reverse("delete_reading_guide_post", args=[guide_post.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ReadingGuidePost.objects.filter(id=guide_post.id).exists())

    def test_reading_guide_post_type_validation(self):
        weekly = ReadingGuidePost(
            active_plan=self.active_plan,
            title="Weekly",
            body="Body",
            guide_type=ReadingGuidePost.GUIDE_WEEKLY,
        )
        daily = ReadingGuidePost(
            active_plan=self.active_plan,
            title="Daily",
            body="Body",
            guide_type=ReadingGuidePost.GUIDE_DAILY,
        )
        general = ReadingGuidePost(
            active_plan=self.active_plan,
            title="General",
            body="Body",
            guide_type=ReadingGuidePost.GUIDE_GENERAL,
            week_number=1,
        )

        with self.assertRaises(ValidationError):
            weekly.full_clean()
        with self.assertRaises(ValidationError):
            daily.full_clean()
        with self.assertRaises(ValidationError):
            general.full_clean()

    def test_chinese_guide_page_contains_chinese_labels(self):
        self.set_language("zh")
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="置顶指引",
            body="请留意约翰福音中的记号。",
            is_pinned=True,
            is_published=True,
            published_at=timezone.now(),
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "读经指引")
        self.assertContains(response, "置顶")
        self.assertContains(response, "已发布")

    def test_english_guide_page_contains_english_labels(self):
        self.set_language("en")
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="置顶指引",
            title_en="Pinned Guide",
            body="中文内容",
            body_en="English body",
            is_pinned=True,
            is_published=True,
            published_at=timezone.now(),
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Guides")
        self.assertContains(response, "Pinned")
        self.assertContains(response, "Published")

    def test_active_plan_intro_page_links_to_guides(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("active_plan_guides", args=[self.active_plan.id]))

    def test_enrolled_user_can_view_plan_detail(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_detail", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "May Test Plan")
        self.assertContains(response, "约翰福音 第 1 章")

    def test_enrolled_user_can_check_in_today(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("check_in", args=[self.active_plan.id, self.day1.id])
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            CheckIn.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.day1,
            ).exists()
        )

    def test_user_cannot_check_in_same_day_twice(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        url = reverse("check_in", args=[self.active_plan.id, self.day1.id])
        self.client.post(url)
        self.client.post(url)

        count = CheckIn.objects.filter(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
        ).count()

        self.assertEqual(count, 1)

    def test_unenrolled_user_cannot_check_in(self):
        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("check_in", args=[self.active_plan.id, self.day1.id])
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            CheckIn.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.day1,
            ).exists()
        )

    def test_user_cannot_check_in_future_day(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("check_in", args=[self.active_plan.id, self.future_day.id])
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            CheckIn.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.future_day,
            ).exists()
        )

    def test_checkin_is_scoped_to_active_plan(self):
        another_active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=timezone.localdate(),
            title="Another Run",
        )

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=another_active_plan,
        )

        CheckIn.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
        )

        self.assertFalse(
            CheckIn.objects.filter(
                user=self.user,
                active_plan=another_active_plan,
                plan_day=self.day1,
            ).exists()
        )

    def test_comment_owner_can_soft_delete_comment(self):
        comment = ReflectionComment.objects.create(
            user=self.user,
            plan_day=self.day1,
            body="My reflection",
            active_plan=self.active_plan,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("delete_comment", args=[comment.id])
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()
        self.assertTrue(comment.is_deleted)
        self.assertEqual(comment.body, "")

    def test_non_owner_cannot_delete_comment(self):
        comment = ReflectionComment.objects.create(
            user=self.user,
            plan_day=self.day1,
            body="My reflection",
            active_plan=self.active_plan,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.post(
            reverse("delete_comment", args=[comment.id])
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()
        self.assertFalse(comment.is_deleted)
        self.assertEqual(comment.body, "My reflection")

    def test_staff_can_soft_delete_any_comment(self):
        comment = ReflectionComment.objects.create(
            user=self.user,
            plan_day=self.day1,
            body="My reflection",
            active_plan=self.active_plan,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
        )

        self.client.login(username="admin", password="testpass123")

        response = self.client.post(
            reverse("delete_comment", args=[comment.id])
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()
        self.assertTrue(comment.is_deleted)
        self.assertEqual(comment.body, "")

    def test_group_progress_requires_login(self):
        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_user_without_group_sees_clear_message(self):
        self.set_language("en")

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Group Reading Progress")
        self.assertContains(
            response,
            "Group belonging comes from active primary Church Structure membership.",
        )
        self.assertContains(response, "You are not assigned to a small group yet.")
        self.assertNotContains(response, f'href="{reverse("my_group_progress")}"')

    def test_group_progress_shows_same_group_members_only(self):
        group_unit = self.group_unit
        other_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="FLOW-SAME-OTHER",
            name="Other Group",
        )

        # Group-progress access/default and the visible roster are membership-core
        # and canonical-unit based, so members need active primary membership under
        # the selected unit.
        self.add_active_primary_membership(self.user, group_unit)

        self.add_active_primary_membership(self.other_user, group_unit)

        outside_user = User.objects.create_user(
            username="outside",
            email="outside@example.com",
            password="testpass123",
        )
        # Membership in another mapped group unit: outside the selected roster.
        self.add_active_primary_membership(outside_user, other_unit)

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )
        PlanEnrollment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
        )
        PlanEnrollment.objects.create(
            user=outside_user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "levin")
        self.assertContains(response, "other")
        self.assertNotIn(">outside<", response.content.decode())

    def test_group_progress_shows_checked_and_missing_status(self):
        self.set_language("en")
        group_unit = self.group_unit

        self.add_active_primary_membership(self.user, group_unit)

        self.add_active_primary_membership(self.other_user, group_unit)

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )
        PlanEnrollment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
        )

        CheckIn.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Checked")
        self.assertContains(response, "Missing")

    def test_group_progress_shows_not_joined_member(self):
        self.set_language("en")
        group_unit = self.group_unit

        self.add_active_primary_membership(self.user, group_unit)

        self.add_active_primary_membership(self.other_user, group_unit)

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "levin")
        self.assertContains(response, "other")
        self.assertContains(response, "Not joined")

    def test_english_group_progress_keeps_english_labels_and_statuses(self):
        self.set_language("en")
        self.group_unit.name_en = "Rainbow 4 English"
        self.group_unit.save(update_fields=["name_en"])
        ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="FLOW-EN-SWITCH",
            name="Switch Group",
            name_en="Switch Group EN",
        )
        self.add_active_primary_membership(self.user, self.group_unit)
        self.add_active_primary_membership(self.other_user, self.group_unit)
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )
        second_active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=timezone.localdate() - timezone.timedelta(days=1),
            title="Second Group Plan",
        )
        PlanEnrollment.objects.create(
            user=self.other_user,
            active_plan=second_active_plan,
        )
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("my_group_progress"),
            {"group": self.group_unit.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Group Reading Progress")
        self.assertContains(
            response,
            "View your group's reading completion and today's check-in status for the selected reading plan.",
        )
        self.assertContains(
            response,
            "Group belonging comes from active primary Church Structure membership. Serving assignments and role permissions are separate.",
        )
        self.assertContains(response, "Rainbow 4 English")
        self.assertContains(response, "Current Group")
        self.assertContains(response, "Current Reading Plan")
        self.assertContains(response, "Start Date")
        self.assertContains(response, "Switch group")
        self.assertContains(response, "Switch plan")
        self.assertContains(response, "Second Group Plan")
        self.assertContains(response, "Member Progress")
        self.assertContains(response, "Member")
        self.assertContains(response, "Today")
        self.assertContains(response, "Progress")
        self.assertContains(response, "Completed")
        self.assertContains(response, "reading days")
        self.assertContains(response, "Not joined")
        self.assertContains(response, "Missing")

    def test_chinese_group_progress_localizes_labels_and_statuses(self):
        self.set_language("zh")
        ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="FLOW-ZH-SWITCH",
            name="可切换小组",
            name_en="Switchable Group",
        )
        self.add_active_primary_membership(self.user, self.group_unit)
        self.add_active_primary_membership(self.other_user, self.group_unit)
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("my_group_progress"),
            {"group": self.group_unit.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "我的小组读经进度")
        self.assertContains(response, "查看本小组成员在当前读经计划中的完成情况与今日打卡状态。")
        self.assertContains(response, "小组归属来自已生效的主要教会结构归属")
        self.assertContains(response, "当前小组")
        self.assertContains(response, "当前读经计划")
        self.assertContains(response, "开始日期")
        self.assertContains(response, "切换小组")
        self.assertContains(response, "切换计划")
        self.assertContains(response, "成员进度")
        self.assertContains(response, "今日状态")
        self.assertContains(response, "完成进度")
        self.assertContains(response, "已完成")
        self.assertContains(response, "未加入计划")
        self.assertContains(response, "未打卡")
        self.assertNotContains(response, "Members")
        self.assertNotContains(response, "Enrollment")
        self.assertNotContains(response, "Switch group")
        self.assertNotContains(response, "Not joined")
        self.assertNotContains(response, "Missing")

    def test_chinese_group_progress_no_group_state_is_localized(self):
        self.set_language("zh")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "你目前还没有可查看的小组读经进度。")
        self.assertNotContains(response, "You are not assigned to a small group yet.")

    def test_chinese_group_progress_no_active_plan_state_is_localized(self):
        self.set_language("zh")
        self.add_active_primary_membership(self.user, self.group_unit)
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "这个小组目前还没有成员加入正在进行的读经计划。",
        )
        self.assertNotContains(
            response,
            "No active reading plan has been joined by this group yet.",
        )

    def test_group_leader_can_view_assigned_group_progress(self):
        self.set_language("en")
        leader = User.objects.create_user(
            username="group_leader",
            email="leader@example.com",
            password="testpass123",
        )
        # ROLE-RETIRE.1B: scoped role access requires an explicit structure_unit.
        assigned_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="FLOW-LEADER-ASSIGNED",
            name="Assigned Group",
        )
        ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="FLOW-LEADER-OUTSIDE",
            name="Outside Group",
        )
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=assigned_unit,
        )

        self.client.login(username="group_leader", password="testpass123")

        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assigned Group")
        self.assertNotContains(response, "Outside Group")

    def test_district_leader_can_select_group_in_assigned_district(self):
        self.set_language("en")
        # CS-CORE.2D-B: a district-leader scope resolves through the mapped district
        # unit and covers its descendant small-group units.
        district_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="FLOW-DIST-N",
            name="North District Unit",
        )
        group_a_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="FLOW-DIST-N-A",
            name="North Group A",
            parent=district_unit,
        )
        group_b_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="FLOW-DIST-N-B",
            name="North Group B",
            parent=district_unit,
        )
        leader = User.objects.create_user(
            username="district_leader",
            email="district@example.com",
            password="testpass123",
        )
        # ROLE-RETIRE.1B: scoped role access requires an explicit structure_unit.
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            structure_unit=district_unit,
        )

        self.client.login(username="district_leader", password="testpass123")

        response = self.client.get(
            reverse("my_group_progress"),
            {"group": group_b_unit.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "North Group A")
        self.assertContains(response, "North Group B")
        self.assertContains(response, f'value="{group_b_unit.id}" selected')

    def test_district_leader_cannot_access_group_outside_district(self):
        self.set_language("en")
        # CS-CORE.2D-B: map both districts/groups so the structure-aware district
        # scope covers the in-district group but never the out-of-district one.
        district_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="FLOW-DIST-E",
            name="East District Unit",
        )
        inside_group_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="FLOW-DIST-E-IN",
            name="East Group",
            parent=district_unit,
        )
        outside_district_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="FLOW-DIST-W",
            name="West District Unit",
        )
        outside_group_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="FLOW-DIST-W-OUT",
            name="West Group",
            parent=outside_district_unit,
        )
        leader = User.objects.create_user(
            username="limited_leader",
            email="limited@example.com",
            password="testpass123",
        )
        # ROLE-RETIRE.1B: scoped role access requires an explicit structure_unit.
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            structure_unit=district_unit,
        )

        self.client.login(username="limited_leader", password="testpass123")

        response = self.client.get(
            reverse("my_group_progress"),
            {"group": outside_group_unit.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "East Group")
        self.assertNotContains(response, "West Group")
        self.assertEqual(response.context["selected_group"], inside_group_unit)

    def test_staff_can_select_any_group_progress(self):
        self.set_language("en")
        other_group_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="FLOW-STAFF-VISIBLE",
            name="Staff Visible Group",
        )

        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("my_group_progress"),
            {"group": other_group_unit.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff Visible Group")
        self.assertEqual(response.context["selected_group"], other_group_unit)

    def test_home_shows_rest_day_when_today_has_no_plan_day(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.active_plan.start_date = timezone.localdate() - timezone.timedelta(days=5)
        self.active_plan.save()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "休息 / 补读日")
        self.assertContains(response, "今天没有指定读经")


    def test_home_hides_not_started_plan_and_links_to_reading(self):
        self.set_language("en")
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.active_plan.start_date = timezone.localdate() + timezone.timedelta(days=1)
        self.active_plan.save()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Not started")
        self.assertContains(response, "You do not have an active reading plan right now.")
        self.assertContains(response, reverse("my_plans"))


    def test_home_does_not_show_ended_plan_as_primary_card(self):
        self.set_language("en")
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.active_plan.start_date = timezone.localdate() - timezone.timedelta(days=20)
        self.active_plan.save()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Ended")
        self.assertNotContains(response, "May Test Plan")
        self.assertContains(response, "Completed reading plans are available on the Reading page.")

        my_plans_response = self.client.get(reverse("my_plans"))
        self.assertContains(my_plans_response, "May Test Plan")
        self.assertContains(my_plans_response, "Ended")

    def test_plan_detail_shows_rest_days_for_missing_day_numbers(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_detail", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Day 3")
        self.assertContains(response, "休息 / 补读日")
        self.assertContains(response, "这一天没有指定读经")


    def test_plan_detail_progress_uses_reading_days_not_calendar_days(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        CheckIn.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_detail", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 / 3 读经日")
        self.assertContains(response, "总日历天数：10")
        self.assertContains(response, "休息 / 补读日：7")

    def test_my_plans_requires_login(self):
        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)


    def test_my_plans_shows_joined_plan(self):
        self.set_language("en")
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "May Test Plan")
        self.assertContains(response, "Progress")

    def test_group_progress_route_resolves_to_existing_view(self):
        match = resolve("/groups/my/progress/")

        self.assertEqual(match.url_name, "my_group_progress")

    def test_my_plans_links_to_group_progress_for_active_primary_membership(self):
        self.set_language("en")
        self.add_active_primary_membership(self.user, self.group_unit)
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Group Reading Progress")
        self.assertContains(response, reverse("my_group_progress"))
        self.assertContains(response, "Open group reading progress")

    def test_my_plans_does_not_link_group_progress_without_accessible_group(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Join a group to view group reading progress.")
        self.assertNotContains(response, reverse("my_group_progress"))

    def test_my_plans_does_not_link_group_progress_for_requested_membership(self):
        self.set_language("en")
        ChurchStructureMembership.objects.create(
            user=self.user,
            unit=self.group_unit,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_plans"))
        progress_response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Join a group to view group reading progress.")
        self.assertNotContains(response, reverse("my_group_progress"))
        self.assertContains(
            progress_response, "You are not assigned to a small group yet."
        )

    def test_my_plans_links_to_group_progress_for_scoped_group_leader(self):
        self.set_language("en")
        leader = User.objects.create_user(
            username="plans_group_leader",
            email="plans_leader@example.com",
            password="testpass123",
        )
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )
        self.client.login(username="plans_group_leader", password="testpass123")

        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Group Reading Progress")
        self.assertContains(response, reverse("my_group_progress"))

    def test_chinese_my_plans_links_to_group_progress_for_active_membership(self):
        self.set_language("zh")
        self.add_active_primary_membership(self.user, self.group_unit)
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "我的小组读经进度")
        self.assertContains(response, reverse("my_group_progress"))

    def test_chinese_my_plans_uses_chinese_labels(self):
        self.set_language("zh")
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "我的读经计划")
        self.assertContains(response, "返回今日")
        self.assertContains(response, "状态")
        self.assertContains(response, "进行中")
        self.assertContains(response, "开始日期")
        self.assertContains(response, "进度")
        self.assertContains(response, "查看计划")
        self.assertContains(response, "退出计划")
        self.assertNotContains(response, "My Reading Plans")
        self.assertNotContains(response, "Back to Today")


    def test_home_uses_lightweight_reading_cta_without_available_plan_grid(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You do not have an active reading plan right now.")
        self.assertContains(response, "Browse reading plans")
        self.assertContains(response, reverse("my_plans"))
        self.assertNotContains(response, "Available Reading Plans")
        self.assertNotContains(response, "Join this plan")


    def test_my_plans_shows_available_plan_discovery(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Available Reading Plans")
        self.assertContains(response, "May Test Plan")
        self.assertContains(response, "Join this plan")


    def test_user_can_leave_active_plan(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("leave_active_plan", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("my_plans"))

        self.assertFalse(
            PlanEnrollment.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
            ).exists()
        )


    def test_leave_plan_does_not_delete_checkins(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        CheckIn.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
        )

        self.client.login(username="levin", password="testpass123")

        self.client.post(
            reverse("leave_active_plan", args=[self.active_plan.id])
        )

        self.assertTrue(
            CheckIn.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.day1,
            ).exists()
        )


    def test_left_plan_no_longer_appears_as_joined_in_my_plans(self):
        enrollment = PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        enrollment.delete()

        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You have not joined any reading plan yet.")
        self.assertContains(response, "Available Reading Plans")
        self.assertContains(response, "May Test Plan")
        self.assertNotContains(response, "Progress:")
        self.assertNotContains(response, "Leave Plan")


    def test_user_cannot_leave_other_users_enrollment(self):
        PlanEnrollment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        self.client.post(
            reverse("leave_active_plan", args=[self.active_plan.id])
        )

        self.assertTrue(
            PlanEnrollment.objects.filter(
                user=self.other_user,
                active_plan=self.active_plan,
            ).exists()
        )

    def test_parse_reading_text_extracts_chapters_and_verse_ranges(self):
        passages = parse_reading_text(
            "创世记第 1 章，马可福音第 9 章 1-29 节"
        )

        self.assertEqual(len(passages), 2)

        self.assertEqual(passages[0]["display"], "创世记 第 1 章")
        self.assertEqual(passages[0]["search_text"], "Genesis 1")

        self.assertEqual(passages[1]["display"], "马可福音 第 9 章 1-29 节")
        self.assertEqual(passages[1]["search_text"], "Mark 9:1-29")


    def test_home_shows_scripture_reader_links(self):
        self.day1.reading_text = "创世记第 1 章，马可福音第 9 章 1-29 节"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "创世记 第 1 章")
        self.assertContains(response, "马可福音 第 9 章 1-29 节")


    def test_passage_reader_requires_enrollment(self):
        self.day1.reading_text = "创世记第 1 章"
        self.day1.save()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))


    def test_enrolled_user_can_open_passage_reader(self):
        self.day1.reading_text = "创世记第 1 章"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "创世记 第 1 章")

        # Text reader should show scripture iframe.
        self.assertContains(response, "scripture-frame")

        # Text reader should not show audio iframe.
        self.assertNotContains(response, "audio-frame-compact")
        self.assertNotContains(response, "interface=amp")

        # Text reader should still have reflection and check-in flow.
        self.assertContains(
            response,
            reverse("add_comment", args=[self.active_plan.id, self.day1.id, 0]),
        )
        self.assertContains(
            response,
            reverse("check_in", args=[self.active_plan.id, self.day1.id]),
        )

    def test_chinese_reflection_reader_localizes_form_and_wall_names(self):
        self.set_language("zh")
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )
        ReflectionComment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            body="Visible reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertContains(response, "默想墙")
        self.assertContains(response, "分享你的默想")
        self.assertContains(response, "匿名发表")
        self.assertContains(response, "匿名回复")
        self.assertNotContains(response, "Share your reflection")
        self.assertNotContains(response, "Post anonymously")
        self.assertNotContains(response, "Reply anonymously")
        # Match the visible English label only, not base.html JS identifiers
        # such as updateHeaderVisibility / requestHeaderVisibilityUpdate.
        self.assertNotRegex(response.content.decode(), r">\s*Visibility\s*<")
        self.assertNotContains(response, "Passage " + "Wall")
        self.assertNotContains(response, "经文" + "墙")

    def test_english_reflection_reader_uses_reflection_wall_names(self):
        self.set_language("en")
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )
        ReflectionComment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            body="Visible reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertContains(response, "Reflection Wall")
        self.assertContains(response, "Share your reflection")
        self.assertContains(response, "Post anonymously")
        self.assertContains(response, "Reply anonymously")
        self.assertNotContains(response, "Passage " + "Wall")
        self.assertNotContains(response, "经文" + "墙")


    def test_passage_reader_rejects_invalid_index(self):
        self.day1.reading_text = "创世记第 1 章"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 99])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("active_plan_detail", args=[self.active_plan.id]),
        )

    def test_parse_reading_text_extracts_english_chapters(self):
        passages = parse_reading_text("John 1")

        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0]["display"], "John 1")
        self.assertEqual(passages[0]["search_text"], "John 1")


    def test_parse_reading_text_extracts_english_verse_ranges(self):
        passages = parse_reading_text("John 1:1-18, 1 Corinthians 13")

        self.assertEqual(len(passages), 2)

        self.assertEqual(passages[0]["display"], "John 1:1-18")
        self.assertEqual(passages[0]["search_text"], "John 1:1-18")

        self.assertEqual(passages[1]["display"], "1 Corinthians 13")
        self.assertEqual(passages[1]["search_text"], "1 Corinthians 13")


    def test_home_shows_scripture_reader_link_for_english_reading_text(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "约翰福音 第 1 章")
        self.assertNotContains(response, "No scripture links could be generated")

    def test_parse_reading_text_extracts_chinese_compact_memory_verse(self):
        passages = parse_reading_text("马可福音 6:41")

        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0]["display"], "马可福音 第 6 章 41 节")
        self.assertEqual(passages[0]["display_zh"], "马可福音 第 6 章 41 节")
        self.assertEqual(passages[0]["display_en"], "Mark 6:41")
        self.assertEqual(passages[0]["search_text"], "Mark 6:41")
        self.assertIn("version=CUVS", passages[0]["text_url_zh"])
        self.assertIn("version=NIV", passages[0]["text_url_en"])


    def test_home_shows_memory_verse_reader_link(self):
        self.day1.reading_text = "John 1"
        self.day1.memory_verse = "马可福音 6:41"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "背诵经文")
        self.assertContains(response, "马可福音 第 6 章 41 节")
        self.assertContains(
            response,
            reverse("memory_verse_reader", args=[self.active_plan.id, self.day1.id, 0]),
        )


    def test_enrolled_user_can_open_memory_verse_reader(self):
        self.day1.memory_verse = "马可福音 6:41"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("memory_verse_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "马可福音 第 6 章 41 节")
        self.assertContains(response, "scripture-frame")

        # Memory verse reader is text-only.
        self.assertNotContains(response, "audio-frame-compact")
        self.assertNotContains(response, "interface=amp")

        # Memory verse reader should not show check-in / reflection flow.
        self.assertNotContains(
            response,
            reverse("check_in", args=[self.active_plan.id, self.day1.id]),
        )


    def test_memory_verse_reader_requires_enrollment(self):
        self.day1.memory_verse = "马可福音 6:41"
        self.day1.save()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("memory_verse_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_first_passage_does_not_show_check_in_when_multiple_passages(self):
        self.day1.reading_text = "John 1, John 2"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "继续下一段经文")
        self.assertNotContains(response, "我已完成今日读经")


    def test_last_passage_shows_reflection_and_check_in(self):
        self.day1.reading_text = "John 1, John 2"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 1])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "默想 / 评论")
        self.assertContains(response, "发表默想")
        self.assertContains(response, "现有默想")
        self.assertContains(response, "完成今日读经")
        self.assertContains(response, "我已完成今日读经")


    def test_check_in_from_passage_reader_redirects_back_to_reader(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        next_url = reverse(
            "passage_reader",
            args=[self.active_plan.id, self.day1.id, 0],
        )

        response = self.client.post(
            reverse("check_in", args=[self.active_plan.id, self.day1.id]),
            {"next": next_url},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)

        self.assertTrue(
            CheckIn.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.day1,
            ).exists()
        )


    def test_comment_from_passage_reader_redirects_back_to_reader(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        # CS-CORE.4G.3: group sharing is membership-core, not Profile.small_group.
        self.add_active_primary_membership(self.user, self.group_unit)

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        next_url = reverse(
            "passage_reader",
            args=[self.active_plan.id, self.day1.id, 0],
        )

        response = self.client.post(
            reverse("add_comment", args=[self.active_plan.id, self.day1.id, 0]),
            {
                "body": "This is my reflection.",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
                "next": next_url,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)

        self.assertTrue(
            ReflectionComment.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.day1,
                scripture_ref_key="John 1",
                visibility=ReflectionComment.VISIBILITY_GROUP,
                body="This is my reflection.",
            ).exists()
        )

    def test_passage_reader_defaults_to_chinese_tab(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "中文")
        self.assertContains(response, "English")
        self.assertContains(response, "约翰福音 第 1 章")
        self.assertContains(response, "version=CUVS")
        self.assertNotContains(response, "version=NIV")

    def test_passage_reader_can_switch_to_english_tab(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0]) + "?lang=en"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "中文")
        self.assertContains(response, "English")
        self.assertContains(response, "John 1")
        self.assertContains(response, "version=NIV")
        self.assertNotContains(response, "version=CUVS")

    def test_plan_detail_hides_raw_reading_text_when_passage_links_exist(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_detail", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)

        # There should be a generated passage button/link.
        self.assertContains(response, "约翰福音 第 1 章")

        # But the raw-text failure message should not appear.
        self.assertNotContains(response, "No scripture links could be generated")

    def test_memory_verse_reader_single_passage_does_not_reverse_none_next_index(self):
        self.day1.memory_verse = "马可福音 6:41"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("memory_verse_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "背诵经文")
        self.assertContains(response, "返回计划")
        self.assertNotContains(response, "继续下一段经文")
        self.assertNotContains(response, "我已完成今日读经")

    def test_scripture_reader_last_passage_still_shows_check_in(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "完成今日读经")
        self.assertContains(response, "我已完成今日读经")

    def test_home_dashboard_shows_start_reading_button(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "今日经文")
        self.assertContains(response, "开始今日读经")
        self.assertContains(response, "约翰福音 第 1 章")

    def test_home_dashboard_does_not_show_reflection_form(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "发表默想")

    def test_english_home_renders_dashboard_title_and_primary_reading_action(self):
        self.set_language("en")
        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "What to read today, and where to go next.")
        self.assertContains(response, "Today&#x27;s reading")
        self.assertContains(response, "Start Today")
        self.assertContains(response, 'class="card dashboard-hero"')
        self.assertNotContains(response, "dashboard-reading-completed")
        self.assertContains(
            response,
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0]),
        )

    def test_chinese_home_renders_dashboard_wording_and_primary_reading_action(self):
        self.set_language("zh")
        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "今天读什么")
        self.assertContains(response, "今日读经")
        self.assertContains(response, "开始今日读经")
        self.assertNotContains(response, "Today&#x27;s reading")
        self.assertContains(
            response,
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0]),
        )

    def test_home_reading_progress_distinguishes_plan_day_from_completed_days(self):
        self.set_language("en")
        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        CheckIn.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
        )
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        # Plan day (today's scheduled day) is distinct from completed reading days.
        self.assertContains(response, "Plan day 1")
        self.assertContains(response, "1 of 3 reading days completed")
        self.assertContains(response, "Checked in today")

    def test_home_completed_reading_renders_compact_check_in_card(self):
        self.set_language("en")
        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        CheckIn.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
        )
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="card dashboard-reading-completed"')
        self.assertContains(response, "Today's reading is complete.")
        self.assertContains(response, "Read Again")
        self.assertNotContains(response, 'class="card dashboard-hero"')
        self.assertNotContains(response, "Start Today")
        self.assertNotContains(response, "Today’s passages")

    def test_chinese_home_reading_progress_wording(self):
        self.set_language("zh")
        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "计划第 1 天")
        self.assertContains(response, "已完成 0 / 3 个读经日")
        self.assertContains(response, "今日未打卡")

    def test_home_empty_state_points_to_browse_reading_plans(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No reading plan in progress yet")
        self.assertContains(response, "You do not have an active reading plan right now.")
        self.assertContains(response, "Browse reading plans")
        self.assertContains(response, reverse("my_plans"))

    def test_home_shows_secondary_actions_for_logged_in_user(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Where to go next")
        self.assertContains(response, "Open Bible Study")
        self.assertContains(response, "Open Prayer Wall")
        self.assertContains(response, "Open My Serving")
        self.assertContains(response, reverse("study_session_list"))
        self.assertContains(response, reverse("prayer_list"))
        self.assertContains(response, reverse("my_serving"))

    def test_chinese_home_shows_secondary_actions_for_logged_in_user(self):
        self.set_language("zh")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "接下来去哪里")
        self.assertContains(response, "打开查经")
        self.assertContains(response, "打开代祷墙")
        self.assertContains(response, "打开我的服事")

    def test_home_shows_pending_confirmation_in_needs_attention(self):
        team = MinistryTeam.objects.create(name="Lighting Team", name_en="Lighting Team")
        membership = TeamMembership.objects.create(team=team, user=self.user)
        event = ServiceEvent.objects.create(
            title="主日崇拜",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=7),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(assignment=assignment, membership=membership)
        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Needs your attention")
        self.assertContains(response, "Pending confirmation")
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Confirm in My Serving")
        self.assertContains(response, reverse("my_serving"))
        self.assertContains(response, "Today&#x27;s reading")

    def test_staff_can_access_reading_plan_admin_list(self):
        self.set_language("en")
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(reverse("staff_reading_plan_list"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Plan Admin")
        self.assertContains(response, self.plan.name)
        self.assertIn("staff-plan-table-card", content)
        self.assertIn("staff-plan-card-list", content)
        self.assertIn("staff-plan-card-actions", content)
        self.assertContains(response, "Edit Header")
        self.assertContains(response, "Edit Days")
        self.assertContains(
            response,
            reverse("staff_reading_plan_header", args=[self.plan.id]),
        )
        self.assertContains(
            response,
            reverse("staff_reading_plan_days", args=[self.plan.id]),
        )

    def test_chinese_reading_plan_admin_list_uses_chinese_labels(self):
        self.set_language("zh")
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(reverse("staff_reading_plan_list"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "读经计划管理")
        self.assertContains(response, "分别编辑读经计划标题和每日读经内容")
        self.assertContains(response, "返回 Django 管理后台")
        self.assertContains(response, "英文名称")
        self.assertContains(response, "编辑标题")
        self.assertContains(response, "编辑每日内容")
        self.assertContains(response, "启用")
        self.assertIn("staff-plan-card-list", content)
        self.assertIn("staff-plan-card-actions", content)
        self.assertContains(
            response,
            reverse("staff_reading_plan_header", args=[self.plan.id]),
        )
        self.assertContains(
            response,
            reverse("staff_reading_plan_days", args=[self.plan.id]),
        )
        self.assertNotContains(response, "Reading Plan Admin")
        self.assertNotContains(response, "Edit reading plan headers")

    def test_reading_plan_admin_mobile_cards_replace_table_layout(self):
        css_path = Path(__file__).resolve().parent.parent / "static" / "css" / "app.css"
        css = css_path.read_text(encoding="utf-8")

        self.assertIn(".staff-plan-card-list", css)
        self.assertIn(".staff-plan-table-card", css)
        self.assertIn("display: none;", css)
        self.assertIn("display: grid;", css)
        self.assertIn(".staff-plan-card-actions .button", css)
        self.assertIn("white-space: nowrap;", css)

    def test_chinese_reading_plan_header_edit_page_uses_chinese_labels(self):
        self.set_language("zh")
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("staff_reading_plan_header", args=[self.plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "返回读经计划管理")
        self.assertContains(response, "编辑读经计划标题")
        self.assertContains(response, "名称")
        self.assertContains(response, "英文名称")
        self.assertContains(response, "描述")
        self.assertContains(response, "保存标题")
        self.assertContains(response, "编辑每日内容")
        self.assertNotContains(response, "Back to Reading Plan Admin")
        self.assertNotContains(response, "Edit Reading Plan Header")
        self.assertNotContains(response, "Name en")

    def test_english_reading_plan_header_edit_page_stays_english(self):
        self.set_language("en")
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("staff_reading_plan_header", args=[self.plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Back to Reading Plan Admin")
        self.assertContains(response, "Edit Reading Plan Header")
        self.assertContains(response, "Name")
        self.assertContains(response, "English Name")
        self.assertContains(response, "Description")
        self.assertContains(response, "Save Header")
        self.assertContains(response, "Edit Days")

    def test_chinese_reading_plan_days_edit_page_uses_chinese_labels(self):
        self.set_language("zh")
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("staff_reading_plan_days", args=[self.plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "返回读经计划管理")
        self.assertContains(response, "编辑每日读经内容")
        self.assertContains(response, "编辑标题")
        self.assertContains(response, "新增一天")
        self.assertContains(response, "第几天")
        self.assertContains(response, "读经内容")
        self.assertContains(response, "背诵经文")
        self.assertContains(response, "保存第 1 天")
        self.assertContains(response, "删除第 1 天")
        self.assertNotContains(response, "Back to Reading Plan Admin")
        self.assertNotContains(response, "Edit Reading Plan Days")
        self.assertNotContains(response, "Day number")
        self.assertNotContains(response, "Reading text")

    def test_english_reading_plan_days_edit_page_stays_english(self):
        self.set_language("en")
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("staff_reading_plan_days", args=[self.plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Back to Reading Plan Admin")
        self.assertContains(response, "Edit Reading Plan Days")
        self.assertContains(response, "Edit Header")
        self.assertContains(response, "Add Day")
        self.assertContains(response, "Day number")
        self.assertContains(response, "Reading text")
        self.assertContains(response, "Memory Verse")
        self.assertContains(response, "Save Day 1")
        self.assertContains(response, "Delete Day 1")

    def test_non_staff_cannot_access_reading_plan_admin_list(self):
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("staff_reading_plan_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)


    def test_staff_can_update_reading_plan_header_without_days_inline(self):
        self.client.login(username="admin", password="testpass123")

        response = self.client.post(
            reverse("staff_reading_plan_header", args=[self.plan.id]),
            {
                "name": self.plan.name,
                "name_en": "English Test Plan",
                "description": "中文说明",
                "description_en": "English description",
                "introduction": "中文计划简介",
                "introduction_en": "English introduction",
                "reading_guidance": "中文如何读",
                "reading_guidance_en": "English reading guidance",
                "pastoral_note": "中文读经指引",
                "pastoral_note_en": "English pastoral note",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.plan.refresh_from_db()

        self.assertEqual(self.plan.name_en, "English Test Plan")
        self.assertEqual(self.plan.description_en, "English description")
        self.assertEqual(self.plan.introduction, "中文计划简介")
        self.assertEqual(self.plan.introduction_en, "English introduction")
        self.assertEqual(self.plan.reading_guidance, "中文如何读")
        self.assertEqual(self.plan.reading_guidance_en, "English reading guidance")
        self.assertEqual(self.plan.pastoral_note, "中文读经指引")
        self.assertEqual(self.plan.pastoral_note_en, "English pastoral note")
        self.assertTrue(self.plan.is_active)


    def test_staff_can_update_single_reading_plan_day_line(self):
        self.client.login(username="admin", password="testpass123")

        response = self.client.post(
            reverse("staff_reading_plan_days", args=[self.plan.id]),
            {
                "action": "save_day",
                "day_id": self.day1.id,
                "day_number": "1",
                "reading_text": "Updated John 1",
                "memory_verse": "John 1:1",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.day1.refresh_from_db()
        self.day2.refresh_from_db()

        self.assertEqual(self.day1.reading_text, "Updated John 1")
        self.assertEqual(self.day2.reading_text, "John 2")


    def test_staff_can_add_reading_plan_day_line(self):
        self.client.login(username="admin", password="testpass123")

        response = self.client.post(
            reverse("staff_reading_plan_days", args=[self.plan.id]),
            {
                "action": "add_day",
                "day_number": "11",
                "reading_text": "John 11",
                "memory_verse": "John 11:25",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            ReadingPlanDay.objects.filter(
                plan=self.plan,
                day_number=11,
                reading_text="John 11",
                memory_verse="John 11:25",
            ).exists()
        )

    def test_comment_is_saved_with_passage_visibility_and_group_scope(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        # CS-CORE.4G.3: group sharing is membership-core, not Profile.small_group.
        self.add_active_primary_membership(self.user, self.group_unit)

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        next_url = reverse(
            "passage_reader",
            args=[self.active_plan.id, self.day1.id, 0],
        )

        response = self.client.post(
            reverse("add_comment", args=[self.active_plan.id, self.day1.id, 0]),
            {
                "body": "My group reflection.",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
                "next": next_url,
            },
        )

        self.assertEqual(response.status_code, 302)

        comment = ReflectionComment.objects.get(body="My group reflection.")

        self.assertEqual(comment.active_plan, self.active_plan)
        self.assertEqual(comment.plan_day, self.day1)
        self.assertEqual(comment.scripture_ref_key, "John 1")
        self.assertEqual(comment.visibility, ReflectionComment.VISIBILITY_GROUP)
        # REFLECTION-MIRROR.1D: the create path no longer writes the legacy mirror;
        # visibility is carried by structure_unit_at_post.
        self.assertEqual(comment.structure_unit_at_post, self.group_unit)


    def test_private_reflection_is_not_visible_to_other_user(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        PlanEnrollment.objects.create(user=self.other_user, active_plan=self.active_plan)

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            body="Private reflection.",
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Private reflection.")


    def test_group_reflection_is_visible_to_same_group_member(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        self.add_active_primary_membership(self.user, self.group_unit)

        self.add_active_primary_membership(self.other_user, self.group_unit)

        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        PlanEnrollment.objects.create(user=self.other_user, active_plan=self.active_plan)

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            structure_unit_at_post=self.group_unit,
            body="Group reflection.",
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Group reflection.")


    def test_group_reflection_is_not_visible_to_different_group_member(self):
        self.day1.reading_text = "John 1"
        self.day1.save()



        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        PlanEnrollment.objects.create(user=self.other_user, active_plan=self.active_plan)

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            body="Hidden group reflection.",
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Hidden group reflection.")


    def test_church_reflection_is_visible_to_other_enrolled_user(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        PlanEnrollment.objects.create(user=self.other_user, active_plan=self.active_plan)

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            body="Church-wide reflection.",
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Church-wide reflection.")


    def test_anonymous_reflection_hides_author_from_regular_user(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        PlanEnrollment.objects.create(user=self.other_user, active_plan=self.active_plan)

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            is_anonymous=True,
            body="Anonymous reflection.",
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anonymous reflection.")
        self.assertContains(response, "Anonymous")
        self.assertNotContains(response, "levin")


    def test_staff_can_see_anonymous_author(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(user=self.admin, active_plan=self.active_plan)

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            is_anonymous=True,
            body="Anonymous but staff visible.",
        )

        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anonymous (levin)")


    def test_passage_wall_shows_my_past_reflections(self):
        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            body="My old reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "my",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My old reflection.")


    def test_passage_wall_church_tab_shows_church_reflections(self):
        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            body="Wall reflection.",
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "church",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wall reflection.")

    def test_audio_reader_shows_audio_and_completion_section(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("audio_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "audio-frame-compact")
        self.assertContains(response, 'allow="autoplay"')
        self.assertContains(response, "interface=amp")
        self.assertContains(response, "audio-frame-compact")
        self.assertContains(response, 'allow="autoplay"')
        self.assertContains(response, "interface=amp")

        self.assertContains(
            response,
            reverse("add_comment", args=[self.active_plan.id, self.day1.id, 0]),
        )

        self.assertContains(
            response,
            reverse("check_in", args=[self.active_plan.id, self.day1.id]),
        )


    def test_audio_reader_does_not_show_scripture_iframe(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("audio_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "scripture-frame")
        self.assertNotContains(response, "open scripture directly")


    def test_text_reader_does_not_show_audio_iframe(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "scripture-frame")
        self.assertNotContains(response, "audio-frame-compact")


    def test_check_in_from_audio_reader_redirects_back_to_audio_reader(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        next_url = reverse(
            "audio_reader",
            args=[self.active_plan.id, self.day1.id, 0],
        )

        response = self.client.post(
            reverse("check_in", args=[self.active_plan.id, self.day1.id]),
            {"next": next_url},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)

        self.assertTrue(
            CheckIn.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.day1,
            ).exists()
        )


    def test_comment_from_audio_reader_redirects_back_to_audio_reader(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        # CS-CORE.4G.3: group sharing is membership-core, not Profile.small_group.
        self.add_active_primary_membership(self.user, self.group_unit)

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        next_url = reverse(
            "audio_reader",
            args=[self.active_plan.id, self.day1.id, 0],
        )

        response = self.client.post(
            reverse("add_comment", args=[self.active_plan.id, self.day1.id, 0]),
            {
                "body": "Audio reflection.",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
                "next": next_url,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)

        self.assertTrue(
            ReflectionComment.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.day1,
                scripture_ref_key="John 1",
                body="Audio reflection.",
            ).exists()
        )

    def test_user_can_edit_own_reflection_body_visibility_and_anonymous(self):

        comment = ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            body="Old reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("edit_comment", args=[comment.id]),
            {
                "body": "Updated reflection.",
                "visibility": ReflectionComment.VISIBILITY_CHURCH,
                "is_anonymous": "on",
            },
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()

        self.assertEqual(comment.body, "Updated reflection.")
        self.assertEqual(comment.visibility, ReflectionComment.VISIBILITY_CHURCH)
        self.assertTrue(comment.is_anonymous)


    def test_user_cannot_edit_other_users_reflection(self):
        comment = ReflectionComment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            body="Other user's reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("edit_comment", args=[comment.id]),
            {
                "body": "Hacked.",
                "visibility": ReflectionComment.VISIBILITY_CHURCH,
                "is_anonymous": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()

        self.assertEqual(comment.body, "Other user's reflection.")


    def test_user_cannot_edit_deleted_reflection(self):
        comment = ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            body="Deleted reflection.",
            is_deleted=True,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("edit_comment", args=[comment.id]),
            {
                "body": "Updated deleted reflection.",
                "visibility": ReflectionComment.VISIBILITY_PRIVATE,
                "is_anonymous": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()

        self.assertEqual(comment.body, "Deleted reflection.")
        self.assertTrue(comment.is_deleted)


    def test_reply_edit_does_not_change_parent_visibility(self):
        parent = ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            body="Parent reflection.",
        )

        reply = ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            parent=parent,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            body="Old reply.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("edit_comment", args=[reply.id]),
            {
                "body": "Updated reply.",
                "visibility": ReflectionComment.VISIBILITY_CHURCH,
                "is_anonymous": "on",
            },
        )

        self.assertEqual(response.status_code, 302)

        reply.refresh_from_db()

        self.assertEqual(reply.body, "Updated reply.")
        self.assertEqual(reply.visibility, ReflectionComment.VISIBILITY_GROUP)
        self.assertTrue(reply.is_anonymous)

    def test_reader_shows_new_comment_form_and_reply_form(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            body="Existing reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "默想 / 评论")
        self.assertContains(response, "发表默想")
        self.assertContains(response, "现有默想")
        self.assertContains(response, "Existing reflection.")
        self.assertContains(response, "回复")


    def test_user_can_reply_to_own_comment(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        parent = ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            body="My own reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("add_reply", args=[parent.id]),
            {
                "body": "Replying to myself.",
                "is_anonymous": "",
                "next": reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0]),
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            ReflectionComment.objects.filter(
                parent=parent,
                user=self.user,
                body="Replying to myself.",
            ).exists()
        )


    def test_user_can_reply_to_other_visible_comment(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        self.add_active_primary_membership(self.user, self.group_unit)

        self.add_active_primary_membership(self.other_user, self.group_unit)

        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        PlanEnrollment.objects.create(user=self.other_user, active_plan=self.active_plan)

        parent = ReflectionComment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            structure_unit_at_post=self.group_unit,
            body="Other user's reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("add_reply", args=[parent.id]),
            {
                "body": "Replying to another user.",
                "is_anonymous": "",
                "next": reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0]),
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            ReflectionComment.objects.filter(
                parent=parent,
                user=self.user,
                body="Replying to another user.",
            ).exists()
        )


    def test_reader_shows_replies_under_parent_comment(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        parent = ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            body="Parent reflection.",
        )

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            parent=parent,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            body="Child reply.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Parent reflection.")
        self.assertContains(response, "Child reply.")


class TodayActionCenterTests(TestCase):
    """TODAY-HOME.1B: read-only Today action center (three zones)."""

    def setUp(self):
        self.root_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="TODAY-CHURCH",
            name="Today Whole Church",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.root_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="TODAY-R4",
            name="Today Rainbow 4",
        )
        self.other_group_unit = ChurchStructureUnit.objects.create(
            parent=self.root_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="TODAY-R5",
            name="Today Rainbow 5",
        )
        self.group = self.group_unit
        self.other_group = self.other_group_unit

        self.user = User.objects.create_user(
            username="member",
            password="TestPass123!",
        )

        self.staff = User.objects.create_user(
            username="staff_member",
            password="TestPass123!",
            is_staff=True,
        )

        self.manager = User.objects.create_user(
            username="assignment_manager",
            password="TestPass123!",
            is_staff=True,
        )

        self.team = MinistryTeam.objects.create(name="灯光团队", name_en="Lighting Team")
        self.membership = TeamMembership.objects.create(
            team=self.team,
            user=self.user,
            role=TeamMembership.ROLE_MEMBER,
        )
        self.create_structure_membership(self.user, self.group_unit)

    # --- helpers ---------------------------------------------------------

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def make_event(self, *, title_en, days_from_now=1,
                   status=None, start_datetime=None):
        return ServiceEvent.objects.create(
            title=title_en,
            title_en=title_en,
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=start_datetime or timezone.now() + timedelta(days=days_from_now),
            status=status or ServiceEvent.STATUS_PUBLISHED,
        )

    def add_event_audience(self, event, *units):
        for unit in units:
            ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)

    def make_visible_event(self, **kwargs):
        # SE-RETIRE.1B: the zero-row legacy fallback is retired, so an ordinary
        # member only sees a gathering that carries audience rows. A root
        # audience row matches every authenticated user via membership-core.
        event = self.make_event(**kwargs)
        self.add_event_audience(event, self.root_unit)
        return event

    def local_datetime(self, days_from_today=0, *, hour=9, minute=0):
        local_date = timezone.localdate() + timedelta(days=days_from_today)
        naive_datetime = datetime.combine(local_date, datetime.min.time()).replace(
            hour=hour,
            minute=minute,
        )
        return timezone.make_aware(
            naive_datetime,
            timezone.get_current_timezone(),
        )

    def make_assignment(self, event, *, confirmed=False):
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.team,
            status=TeamAssignment.STATUS_SCHEDULED,
            created_by=self.manager,
        )
        member = TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=self.membership,
        )
        if confirmed:
            member.confirmed_at = timezone.now()
            member.save()
        return member

    def create_structure_membership(self, user, unit, **overrides):
        data = {
            "user": user,
            "unit": unit,
            "status": ChurchStructureMembership.STATUS_ACTIVE,
            "is_primary": True,
            "start_date": timezone.localdate() - timedelta(days=1),
        }
        data.update(overrides)
        return ChurchStructureMembership.objects.create(**data)

    def make_meeting(self, *, unit, days_from_now=2,
                     lesson_title_en="Lesson One", meeting_datetime=None):
        series = BibleStudySeries.objects.create(
            title="查经系列",
            title_en="Study Series",
            status=BibleStudySeries.STATUS_PUBLISHED,
            is_active=True,
        )
        lesson = BibleStudyLesson.objects.create(
            series=series,
            title="查经一",
            title_en=lesson_title_en,
            lesson_date=timezone.localdate(),
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        # BS-MEETING-MIRROR.1A removed the legacy BibleStudyMeeting.small_group FK.
        # V2 belonging is structure-native: anchor on the canonical unit and carry
        # an audience-scope row (ordinary-member visibility reads these rows plus
        # active primary membership; zero-row meetings fail closed).
        meeting = BibleStudyMeeting.objects.create(
            lesson=lesson,
            anchor_unit=unit,
            meeting_datetime=meeting_datetime or timezone.now() + timedelta(days=days_from_now),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        if unit is not None:
            BibleStudyMeetingAudienceScope.objects.create(meeting=meeting, unit=unit)
        return meeting

    def get_home(self, user=None, language="en"):
        self.client.force_login(user or self.user)
        self.set_language(language)
        return self.client.get(reverse("home"))

    # --- tests -----------------------------------------------------------

    def test_needs_attention_shows_pending_confirmation(self):
        event = self.make_event(title_en="Sunday Service Alpha")
        self.make_assignment(event, confirmed=False)

        response = self.get_home()

        self.assertContains(response, "Needs your attention")
        self.assertContains(response, "Sunday Service Alpha")
        self.assertContains(response, "Confirm in My Serving")

    def test_needs_attention_hidden_when_no_pending(self):
        event = self.make_event(title_en="Sunday Service Beta")
        self.make_assignment(event, confirmed=True)

        response = self.get_home()

        self.assertNotContains(response, "Needs your attention")
        self.assertNotContains(response, "Confirm in My Serving")

    def test_pending_assignment_not_duplicated_as_full_row_in_week(self):
        # The event must be visible in the This Week gatherings zone for the
        # compact serving note to render, so give it an audience row (the
        # zero-row legacy fallback is retired in SE-RETIRE.1B).
        event = self.make_visible_event(title_en="Sunday Service Gamma")
        self.make_assignment(event, confirmed=False)

        response = self.get_home()
        content = response.content.decode()

        # Pending item is a full row in "Needs your attention" (one confirm link),
        # and the same gathering shows only a compact serving note in This Week.
        self.assertEqual(content.count("Confirm in My Serving"), 1)
        self.assertContains(response, "You are serving — pending confirmation")

    def test_today_serving_summary_includes_started_today_assignment(self):
        event = self.make_visible_event(
            title_en="Started Today Pending Service",
            start_datetime=self.local_datetime(0, hour=0),
        )
        self.make_assignment(event, confirmed=False)

        response = self.get_home()

        self.assertContains(response, "Needs your attention")
        self.assertContains(response, "Started Today Pending Service")
        self.assertContains(response, "Confirm in My Serving")
        self.assertContains(response, "You are serving — pending confirmation")

    def test_today_gathering_keeps_confirmed_serving_note_after_start(self):
        event = self.make_visible_event(
            title_en="Started Today Confirmed Service",
            start_datetime=self.local_datetime(0, hour=0),
        )
        self.make_assignment(event, confirmed=True)

        response = self.get_home()

        self.assertContains(response, "Today's Church Gatherings")
        self.assertContains(response, "Started Today Confirmed Service")
        self.assertContains(response, "You are serving — confirmed")

    def test_today_gathering_includes_multiday_event_that_overlaps_today(self):
        event = ServiceEvent.objects.create(
            title="Overnight Retreat",
            title_en="Overnight Retreat",
            event_type=ServiceEvent.EVENT_SPECIAL_MEETING,
            start_datetime=self.local_datetime(-1, hour=20),
            end_datetime=self.local_datetime(0, hour=22),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.add_event_audience(event, self.root_unit)

        response = self.get_home()

        self.assertContains(response, "Today's Church Gatherings")
        self.assertContains(response, "Overnight Retreat")

    def test_today_gathering_rows_order_by_start_time(self):
        self.make_visible_event(
            title_en="Later Today Gathering",
            start_datetime=self.local_datetime(0, hour=19),
        )
        self.make_visible_event(
            title_en="Earlier Today Gathering",
            start_datetime=self.local_datetime(0, hour=9),
        )

        response = self.get_home()
        content = response.content.decode()

        self.assertContains(response, "Today's Church Gatherings")
        self.assertLess(
            content.index("Earlier Today Gathering"),
            content.index("Later Today Gathering"),
        )

    def test_today_gathering_window_uses_bay_area_local_date(self):
        late_today_utc = self.local_datetime(0, hour=23, minute=30).astimezone(
            datetime_timezone.utc
        )
        self.make_visible_event(
            title_en="Late Bay Area Gathering",
            start_datetime=late_today_utc,
        )

        response = self.get_home()

        self.assertContains(response, "Today's Church Gatherings")
        self.assertContains(response, "Late Bay Area Gathering")
        self.assertNotContains(response, "Church Gatherings this week")

    def test_church_gatherings_shows_visible_upcoming(self):
        self.make_visible_event(title_en="Midweek Prayer Gathering")

        response = self.get_home()

        self.assertContains(response, "Church Gatherings this week")
        self.assertContains(response, "Midweek Prayer Gathering")

    def test_church_gathering_today_appears_in_today_not_this_week(self):
        self.make_visible_event(
            title_en="Today Prayer Gathering",
            start_datetime=self.local_datetime(0, hour=9),
        )

        response = self.get_home()

        self.assertContains(response, "Today's Church Gatherings")
        self.assertContains(response, "Today Prayer Gathering")
        self.assertNotContains(response, "Church Gatherings this week")

    def test_church_gathering_tomorrow_appears_in_this_week_not_today(self):
        self.make_visible_event(
            title_en="Tomorrow Prayer Gathering",
            start_datetime=self.local_datetime(1, hour=9),
        )

        response = self.get_home()

        self.assertContains(response, "Church Gatherings this week")
        self.assertContains(response, "Tomorrow Prayer Gathering")
        self.assertNotContains(response, "Today's Church Gatherings")

    def test_church_gathering_week_window_is_half_open(self):
        self.make_visible_event(
            title_en="Final Included Gathering",
            start_datetime=self.local_datetime(7, hour=23),
        )
        self.make_visible_event(
            title_en="Boundary Excluded Gathering",
            start_datetime=self.local_datetime(8, hour=9),
        )

        response = self.get_home()

        self.assertContains(response, "Church Gatherings this week")
        self.assertContains(response, "Final Included Gathering")
        self.assertNotContains(response, "Boundary Excluded Gathering")

    def test_church_gathering_datetime_is_member_formatted(self):
        # Relative future datetime so the gathering always falls inside the Today
        # page's upcoming/this-week window, regardless of the current date.
        formatted_dt = (timezone.now() + timedelta(days=1)).replace(
            hour=19, minute=30, second=0, microsecond=0
        )
        self.make_visible_event(
            title_en="Formatted Gathering",
            start_datetime=formatted_dt,
        )

        response = self.get_home()

        self.assertContains(response, "Formatted Gathering")
        self.assertContains(response, member_datetime(formatted_dt, "en"))
        # Today must use the member-formatted datetime, not Django's raw default
        # rendering (which uses dotted "a.m."/"p.m."). Date-independent check.
        self.assertNotContains(response, "a.m.")
        self.assertNotContains(response, "p.m.")

    def test_draft_and_cancelled_gatherings_excluded_for_staff(self):
        self.make_event(
            title_en="Draft Conference",
            status=ServiceEvent.STATUS_DRAFT,
        )
        self.make_event(
            title_en="Cancelled Retreat",
            status=ServiceEvent.STATUS_CANCELLED,
        )

        response = self.get_home(user=self.staff)

        self.assertNotContains(response, "Draft Conference")
        self.assertNotContains(response, "Cancelled Retreat")

    def test_ordinary_user_does_not_see_out_of_scope_gathering(self):
        # SE-FIELD-RETIRE.1A: a zero-row gathering (no ServiceEventAudienceScope
        # rows) fails closed for ordinary users.
        self.make_event(title_en="Other Group Only Meeting")

        response = self.get_home()

        self.assertNotContains(response, "Other Group Only Meeting")

    def test_staff_gatherings_capped_with_view_all_link(self):
        for index in range(6):
            self.make_event(
                title_en=f"Staff Gathering {index}",
                days_from_now=index + 1,
            )

        response = self.get_home(user=self.staff)
        content = response.content.decode()

        rendered = sum(
            1 for index in range(6) if f"Staff Gathering {index}" in content
        )
        self.assertEqual(rendered, 5)
        self.assertContains(response, "View all Church Gatherings")

    def test_v2_meeting_appears_for_user_group(self):
        self.make_meeting(unit=self.group, lesson_title_en="My Group Lesson")

        response = self.get_home()

        self.assertContains(response, "Small group Bible study")
        self.assertContains(response, "My Group Lesson")

    def test_v2_meeting_today_appears_in_today_not_this_week(self):
        self.make_meeting(
            unit=self.group,
            lesson_title_en="Today Group Lesson",
            meeting_datetime=self.local_datetime(0, hour=19),
        )

        response = self.get_home()

        self.assertContains(response, "Today's Bible study")
        self.assertContains(response, "Today Group Lesson")
        self.assertNotContains(response, "Small group Bible study")

    def test_v2_meeting_tomorrow_appears_in_this_week_not_today(self):
        self.make_meeting(
            unit=self.group,
            lesson_title_en="Tomorrow Group Lesson",
            meeting_datetime=self.local_datetime(1, hour=19),
        )

        response = self.get_home()

        self.assertContains(response, "Small group Bible study")
        self.assertContains(response, "Tomorrow Group Lesson")
        self.assertNotContains(response, "Today's Bible study")

    def test_v2_meeting_datetime_is_member_formatted(self):
        # Relative future datetime so the meeting always falls inside the Today
        # page's upcoming/this-week window, regardless of the current date.
        formatted_dt = (timezone.now() + timedelta(days=2)).replace(
            hour=19, minute=30, second=0, microsecond=0
        )
        self.make_meeting(
            unit=self.group,
            lesson_title_en="Formatted Group Lesson",
            meeting_datetime=formatted_dt,
        )

        response = self.get_home()

        self.assertContains(response, "Formatted Group Lesson")
        self.assertContains(response, member_datetime(formatted_dt, "en"))
        # Today must use the member-formatted datetime, not Django's raw default
        # rendering (which uses dotted "a.m."/"p.m."). Date-independent check.
        self.assertNotContains(response, "a.m.")
        self.assertNotContains(response, "p.m.")

    def test_other_group_meeting_not_shown(self):
        self.make_meeting(
            unit=self.other_group,
            lesson_title_en="Other Group Lesson",
        )

        response = self.get_home()

        self.assertNotContains(response, "Other Group Lesson")

    def test_no_small_group_empty_state(self):
        self.user.church_structure_memberships.all().delete()

        response = self.get_home()

        self.assertContains(
            response,
            "Your confirmed group membership is not ready yet, so no current Bible Study is available.",
        )

    def test_membership_only_user_sees_v2_meeting(self):
        self.make_meeting(
            unit=self.group,
            lesson_title_en="Membership Only Today Lesson",
        )

        response = self.get_home()

        self.assertContains(response, "Small group Bible study")
        self.assertContains(response, "Membership Only Today Lesson")

    def test_profile_only_user_does_not_see_v2_meeting(self):
        self.user.church_structure_memberships.all().delete()
        self.make_meeting(
            unit=self.group,
            lesson_title_en="Profile Only Today Hidden",
        )

        response = self.get_home()

        self.assertContains(
            response,
            "Your confirmed group membership is not ready yet, so no current Bible Study is available.",
        )
        self.assertNotContains(response, "Profile Only Today Hidden")

    def test_no_inline_confirm_form_on_today(self):
        event = self.make_event(title_en="Sunday Service Delta")
        member = self.make_assignment(event, confirmed=False)

        response = self.get_home()
        content = response.content.decode()

        confirm_url = reverse(
            "confirm_team_assignment",
            args=[member.assignment_id],
        )
        self.assertNotIn(confirm_url, content)

    def test_bilingual_section_titles_render(self):
        self.make_visible_event(title_en="Bilingual Gathering")

        english = self.get_home(language="en")
        self.assertContains(english, "Today's Reading")
        self.assertContains(english, "This Week")
        self.assertContains(english, "Church Gatherings this week")

        chinese = self.get_home(language="zh")
        self.assertContains(chinese, "今日读经")
        self.assertContains(chinese, "本周")
        self.assertContains(chinese, "本周教会聚会")

    # --- TODAY-HOME.1D: linked Bible Study role chips --------------------

    def add_role(self, meeting, role, *, user=None, display_name=""):
        return BibleStudyMeetingRole.objects.create(
            meeting=meeting,
            role=role,
            user=user,
            display_name=display_name,
        )

    def test_my_linked_role_shown_on_visible_meeting(self):
        meeting = self.make_meeting(unit=self.group)
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )

        response = self.get_home()

        self.assertContains(response, "My role:")
        self.assertContains(response, "Discussion Leader")

    def test_today_meeting_with_linked_role_shows_role_note(self):
        meeting = self.make_meeting(
            unit=self.group,
            lesson_title_en="Today Role Lesson",
            meeting_datetime=self.local_datetime(0, hour=19),
        )
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )

        response = self.get_home()

        self.assertContains(response, "Today's Bible study")
        self.assertContains(response, "Today Role Lesson")
        self.assertContains(response, "My role:")
        self.assertContains(response, "Discussion Leader")

    def test_today_visible_meeting_without_linked_role_has_no_role_note(self):
        self.make_meeting(
            unit=self.group,
            lesson_title_en="Today No Role Lesson",
            meeting_datetime=self.local_datetime(0, hour=19),
        )

        response = self.get_home()

        self.assertContains(response, "Today's Bible study")
        self.assertContains(response, "Today No Role Lesson")
        self.assertNotContains(response, "My role:")
        self.assertNotContains(response, "My roles:")

    def test_tomorrow_meeting_with_linked_role_shows_this_week_role_note(self):
        meeting = self.make_meeting(
            unit=self.group,
            lesson_title_en="Tomorrow Role Lesson",
            meeting_datetime=self.local_datetime(1, hour=19),
        )
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_WORSHIP_LEAD,
            user=self.user,
        )

        response = self.get_home()

        self.assertContains(response, "Small group Bible study")
        self.assertContains(response, "Tomorrow Role Lesson")
        self.assertContains(response, "My role:")
        self.assertContains(response, "Worship Lead")

    def test_multiple_linked_roles_shown(self):
        meeting = self.make_meeting(unit=self.group)
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_WORSHIP_LEAD,
            user=self.user,
        )

        response = self.get_home()

        self.assertContains(response, "My roles:")
        self.assertContains(response, "Discussion Leader")
        self.assertContains(response, "Worship Lead")

    def test_display_name_only_role_not_shown_as_mine(self):
        self.user.first_name = "Grace"
        self.user.last_name = "Lee"
        self.user.save()
        meeting = self.make_meeting(
            unit=self.group,
            meeting_datetime=self.local_datetime(0, hour=19),
        )
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            display_name="Grace Lee",
        )

        response = self.get_home()

        self.assertNotContains(response, "My role:")
        self.assertNotContains(response, "My roles:")
        self.assertNotContains(response, "Discussion Leader")

    def test_other_users_linked_role_not_shown(self):
        meeting = self.make_meeting(unit=self.group)
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.staff,
        )

        response = self.get_home()

        self.assertNotContains(response, "My role:")
        self.assertNotContains(response, "Discussion Leader")

    def test_other_group_meeting_role_not_shown(self):
        self.other_user = User.objects.create_user(
            username="other_member",
            password="TestPass123!",
        )
        other_meeting = self.make_meeting(unit=self.other_group)
        self.add_role(
            other_meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )

        response = self.get_home()

        self.assertNotContains(response, "My role:")
        self.assertNotContains(response, "Discussion Leader")

    def test_profile_only_linked_role_not_shown_when_meeting_not_visible(self):
        self.user.church_structure_memberships.all().delete()
        meeting = self.make_meeting(unit=self.group)
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )

        response = self.get_home()

        self.assertNotContains(response, "My role:")
        self.assertNotContains(response, "Discussion Leader")

    def test_role_line_hidden_when_no_linked_role(self):
        self.make_meeting(
            unit=self.group,
            meeting_datetime=self.local_datetime(0, hour=19),
        )

        response = self.get_home()

        self.assertContains(response, "Today's Bible study")
        self.assertNotContains(response, "My role:")
        self.assertNotContains(response, "My roles:")
        self.assertNotContains(response, "You are serving")

    def test_cancelled_meeting_role_not_shown(self):
        meeting = self.make_meeting(unit=self.group)
        meeting.status = BibleStudyMeeting.STATUS_CANCELLED
        meeting.save()
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )

        response = self.get_home()

        self.assertNotContains(response, "My role:")
        self.assertNotContains(response, "Discussion Leader")

    def test_chinese_role_label_renders(self):
        meeting = self.make_meeting(unit=self.group)
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )

        response = self.get_home(language="zh")

        self.assertContains(response, "我的角色：")
        self.assertContains(response, "查经带领")

    def test_no_role_management_control_on_today(self):
        meeting = self.make_meeting(unit=self.group)
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )

        response = self.get_home()
        content = response.content.decode()

        manage_url = reverse(
            "manage_bible_study_meeting_roles",
            args=[meeting.id],
        )
        self.assertNotIn(manage_url, content)

    def test_no_role_confirmation_form_on_today(self):
        meeting = self.make_meeting(unit=self.group)
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )

        response = self.get_home()
        content = response.content.decode()

        # Role chips are read-only: no POST form to studies and no
        # accept/decline/confirm role controls on Today.
        self.assertContains(response, "My role:")
        self.assertNotIn('action="/studies', content)
        self.assertNotContains(response, "Accept role")
        self.assertNotContains(response, "Decline role")

    # --- TODAY-AGENDA.1A: serving vs belonging vs management separation ---

    def grant_ministry_management_role(self, user, team, code):
        role_type, _ = MinistryTeamRoleType.objects.get_or_create(
            code=code,
            defaults={"name": code, "name_en": code.title()},
        )
        return MinistryTeamRoleAssignment.objects.create(
            team=team,
            user=user,
            role_type=role_type,
            start_date=timezone.localdate(),
        )

    def make_uncovered_required_event(self, *, title_en, days_from_now=1):
        # A near-term, visible event that requires a team but has no assignment,
        # so it is an "Unassigned" coverage gap for managers of that team.
        event = self.make_event(title_en=title_en, days_from_now=days_from_now)
        event.required_teams.add(self.team)
        return event

    def test_team_serving_summary_requires_explicit_assignment_member(self):
        # setUp gives self.user a TeamMembership (candidate pool) but no
        # TeamAssignmentMember, so no personal serving is inferred from belonging.
        self.make_visible_event(title_en="Membership Only Service")

        response = self.get_home()

        self.assertNotContains(response, "Needs your attention")
        self.assertNotContains(response, "Confirm in My Serving")
        self.assertNotContains(response, "You are serving")

    def test_ministry_role_assignment_alone_is_not_personal_serving(self):
        # A management role assignment is team-management responsibility, not a
        # personal serving assignment; Today must not surface it as My Serving.
        self.grant_ministry_management_role(
            self.user,
            self.team,
            MinistryTeamRoleType.CODE_LEAD,
        )
        self.make_visible_event(title_en="Role Assignment Only Service")

        response = self.get_home()

        self.assertNotContains(response, "Needs your attention")
        self.assertNotContains(response, "Confirm in My Serving")
        self.assertNotContains(response, "You are serving")

    def test_leader_summary_shown_for_global_staff_manager(self):
        self.make_uncovered_required_event(title_en="Staff Managed Service")

        response = self.get_home(user=self.staff)

        self.assertContains(response, "Leader Needs Attention")
        self.assertContains(response, "Staff Managed Service")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Review coverage")

    def test_leader_summary_shown_for_active_ministry_role_manager(self):
        lead_user = User.objects.create_user(
            username="today_team_lead",
            password="TestPass123!",
        )
        self.grant_ministry_management_role(
            lead_user,
            self.team,
            MinistryTeamRoleType.CODE_LEAD,
        )
        self.make_uncovered_required_event(title_en="Lead Managed Service")

        response = self.get_home(user=lead_user)

        self.assertContains(response, "Leader Needs Attention")
        self.assertContains(response, "Lead Managed Service")
        self.assertContains(response, "Lighting Team")

    def test_leader_summary_hidden_for_ordinary_member(self):
        self.make_uncovered_required_event(title_en="Ordinary View Service")

        response = self.get_home()

        self.assertNotContains(response, "Leader Needs Attention")
        self.assertNotContains(response, "Review coverage")

    def test_leader_summary_hidden_for_team_membership_role_lead_without_assignment(self):
        role_lead_user = User.objects.create_user(
            username="today_role_lead_only",
            password="TestPass123!",
        )
        TeamMembership.objects.create(
            team=self.team,
            user=role_lead_user,
            role=TeamMembership.ROLE_LEAD,
        )
        self.make_uncovered_required_event(title_en="Role Lead Only Service")

        response = self.get_home(user=role_lead_user)

        self.assertNotContains(response, "Leader Needs Attention")
        self.assertNotContains(response, "Review coverage")

    def test_leader_summary_hidden_for_can_lead_membership(self):
        can_lead_user = User.objects.create_user(
            username="today_can_lead_only",
            password="TestPass123!",
        )
        TeamMembership.objects.create(
            team=self.team,
            user=can_lead_user,
            role=TeamMembership.ROLE_MEMBER,
            can_lead=True,
        )
        self.make_uncovered_required_event(title_en="Can Lead Only Service")

        response = self.get_home(user=can_lead_user)

        self.assertNotContains(response, "Leader Needs Attention")
        self.assertNotContains(response, "Review coverage")

    def test_leader_summary_bilingual_labels_render(self):
        self.make_uncovered_required_event(title_en="Bilingual Managed Service")

        chinese = self.get_home(user=self.staff, language="zh")
        self.assertContains(chinese, "组长待处理")
        self.assertContains(chinese, "查看排班")


class ReadingStructureRuntimeReadinessAuditTests(TestCase):
    """READING-STRUCT.1A read-only structure-runtime readiness inventory tests.

    The audit reports an inventory + blocker verdict for the remaining legacy
    small-group dependencies in the reading / reflection / progress runtime. It
    is strictly read-only, switches no runtime source, and never prints
    reflection body text.
    """

    plan_counter = 0

    def run_audit_command(self, *args):
        output = StringIO()
        call_command(
            "audit_reading_structure_runtime_readiness",
            *args,
            stdout=output,
        )
        return output.getvalue()

    def create_unit(self, code, *, unit_type=None, is_active=True):
        return ChurchStructureUnit.objects.create(
            unit_type=unit_type or ChurchStructureUnit.UNIT_SMALL_GROUP,
            code=code,
            name=code,
            is_active=is_active,
        )

    def create_group_reflection(self, *, structure_unit, body):
        type(self).plan_counter += 1
        plan = ReadingPlan.objects.create(
            name=f"Runtime Plan {self.plan_counter}",
            is_active=True,
        )
        day = ReadingPlanDay.objects.create(
            plan=plan,
            day_number=1,
            reading_text="John 1",
            memory_verse="John 1:1",
        )
        author = User.objects.create_user(username=f"runtime_author_{self.plan_counter}")
        return ReflectionComment.objects.create(
            user=author,
            plan_day=day,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            structure_unit_at_post=structure_unit,
            body=body,
        )

    def add_active_primary_membership(self, user, unit):
        return ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

    def test_clean_mapped_data_has_no_blockers(self):
        unit = self.create_unit("CLEAN-SG")
        self.create_group_reflection(structure_unit=unit, body="clean body")
        member = User.objects.create_user(username="clean_member")
        self.add_active_primary_membership(member, unit)

        audit = run_reading_structure_runtime_audit()
        stats = audit["stats"]

        self.assertEqual(stats["group_visible_reflections"], 1)
        self.assertEqual(stats["reflections_snapshot_resolvable"], 1)
        self.assertEqual(stats["reflections_group_visible_no_valid_snapshot"], 0)
        self.assertEqual(stats["progress_groups_total"], 1)
        self.assertEqual(stats["progress_groups_resolvable"], 1)
        self.assertEqual(stats["users_with_single_active_primary_membership"], 1)
        self.assertEqual(audit["blockers"], [])

        # --fail-on-blockers must succeed (no error) on clean data.
        self.run_audit_command("--fail-on-blockers")

    def test_missing_snapshot_group_post_is_blocker(self):
        # Group-visible post with no structure snapshot: invisible under 4G.2.
        self.create_group_reflection(structure_unit=None, body="SECRET_MISSING")

        audit = run_reading_structure_runtime_audit()
        stats = audit["stats"]

        self.assertEqual(stats["group_visible_reflections"], 1)
        self.assertEqual(stats["reflections_with_structure_snapshot"], 0)
        self.assertEqual(stats["reflections_snapshot_missing"], 1)
        self.assertEqual(stats["reflections_group_visible_no_valid_snapshot"], 1)
        self.assertIn(
            "reflections_group_visible_no_valid_snapshot", audit["blockers"]
        )

        with self.assertRaises(CommandError):
            self.run_audit_command("--fail-on-blockers")

        # Read-only: never prints reflection body text.
        self.assertNotIn("SECRET_MISSING", self.run_audit_command("--verbose"))

    def test_inactive_snapshot_unit_is_unresolved(self):
        inactive_unit = self.create_unit("INACT-SG", is_active=False)
        self.create_group_reflection(
            structure_unit=inactive_unit, body="inactive body"
        )

        audit = run_reading_structure_runtime_audit()
        stats = audit["stats"]

        self.assertEqual(stats["reflections_snapshot_inactive_unit"], 1)
        self.assertEqual(stats["reflections_snapshot_resolvable"], 0)
        self.assertEqual(stats["progress_groups_inactive_unit"], 0)
        self.assertEqual(stats["reflections_group_visible_no_valid_snapshot"], 1)
        self.assertIn("reflections_group_visible_no_valid_snapshot", audit["blockers"])

    def test_wrong_unit_type_snapshot_is_unresolved(self):
        district_unit = self.create_unit(
            "WRONG-DIST", unit_type=ChurchStructureUnit.UNIT_DISTRICT
        )
        self.create_group_reflection(
            structure_unit=district_unit, body="wrong type body"
        )

        audit = run_reading_structure_runtime_audit()
        stats = audit["stats"]

        self.assertEqual(stats["reflections_snapshot_wrong_unit_type"], 1)
        self.assertEqual(stats["progress_groups_wrong_unit_type"], 0)
        self.assertEqual(stats["reflections_snapshot_resolvable"], 0)
        self.assertIn("reflections_group_visible_no_valid_snapshot", audit["blockers"])

    def test_legacy_progress_group_mapping_blocker_is_retired(self):
        audit = run_reading_structure_runtime_audit()
        stats = audit["stats"]

        self.assertEqual(stats["progress_groups_total"], 0)
        self.assertEqual(stats["progress_groups_missing_mapping"], 0)
        self.assertEqual(stats["progress_groups_resolvable"], 0)
        self.assertNotIn("progress_groups_missing_mapping", audit["blockers"])

    def test_multiple_active_primary_membership_is_blocker(self):
        unit_a = self.create_unit("MULTI-A")
        unit_b = self.create_unit("MULTI-B")
        member = User.objects.create_user(username="multi_member")
        # The model forbids two active primary memberships via clean(); bulk_create
        # skips validation so we can reproduce the data-drift the audit defends
        # against (the DB has no unique constraint enforcing this).
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=member,
                    unit=unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=timezone.localdate(),
                )
                for unit in (unit_a, unit_b)
            ]
        )

        audit = run_reading_structure_runtime_audit()
        stats = audit["stats"]

        self.assertEqual(stats["users_with_multiple_active_primary_membership"], 1)
        self.assertEqual(stats["users_with_single_active_primary_membership"], 0)
        self.assertIn(
            "users_with_multiple_active_primary_membership", audit["blockers"]
        )

    def test_command_is_read_only(self):
        unit = self.create_unit("RO-SG")
        self.create_group_reflection(structure_unit=unit, body="read only body")
        member = User.objects.create_user(username="ro_member")
        self.add_active_primary_membership(member, unit)

        before = {
            "comments": ReflectionComment.objects.count(),
            "units": ChurchStructureUnit.objects.count(),
            "memberships": ChurchStructureMembership.objects.count(),
            "users": User.objects.count(),
        }

        with CaptureQueriesContext(connection) as queries:
            output = self.run_audit_command("--verbose")

        write_sql = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        ]
        self.assertEqual(write_sql, [])
        self.assertEqual(
            before,
            {
                "comments": ReflectionComment.objects.count(),
                "units": ChurchStructureUnit.objects.count(),
                "memberships": ChurchStructureMembership.objects.count(),
                "users": User.objects.count(),
            },
        )
        self.assertIn(
            "Reading structure-runtime readiness audit (READING-STRUCT.1A, read-only)",
            output,
        )
        self.assertIn("READ-ONLY: no reflection", output)
