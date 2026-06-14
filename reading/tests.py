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
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User

from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
    District,
    SmallGroup,
)
from accounts.permissions import (
    can_view_group_progress_for,
    get_accessible_progress_groups,
)
from comments.forms import ReflectionCommentForm
from comments.models import ReflectionComment
from events.models import ServiceEvent
from ministry.models import (
    MinistryTeam,
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
    BibleStudyMeetingRole,
    BibleStudySeries,
    BibleStudySession,
)
from reading.management.commands.audit_reading_privacy_membership_readiness import (
    Command as ReadingPrivacyAuditCommand,
    run_audit,
)
from reading.group_progress_shadow import (
    GroupProgressShadow,
    REASON_DEFAULT_SAME,
    REASON_DEFAULT_WOULD_CHANGE,
    REASON_LEGACY_NO_SELECTED_GROUP,
    REASON_MEMBERSHIP_MULTIPLE_ACTIVE_PRIMARY,
    REASON_MEMBERSHIP_NO_ACTIVE_PRIMARY,
    REASON_PROFILE_MEMBERSHIP_MISMATCH,
    REASON_ROSTER_SAME,
    REASON_ROSTER_WOULD_GAIN,
    REASON_ROSTER_WOULD_LOSE,
    REASON_SELECTED_GROUP_UNMAPPED,
    compute_group_progress_shadow,
)


class MemberDatetimeFilterTests(TestCase):
    def test_member_datetime_formats_aware_datetime_in_english(self):
        value = datetime(2026, 6, 12, 19, 30, tzinfo=datetime_timezone.utc)

        self.assertEqual(member_datetime(value, "en"), "Fri, Jun 12, 7:30 PM")

    def test_member_datetime_formats_aware_datetime_in_chinese(self):
        value = datetime(2026, 6, 12, 19, 30, tzinfo=datetime_timezone.utc)

        self.assertEqual(member_datetime(value, "zh"), "6月12日（周五）晚上7:30")

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
        self.group = SmallGroup.objects.create(name="Rainbow 4")
        self.other_group = SmallGroup.objects.create(name="Rainbow 5")

        self.author = User.objects.create_user(
            username="author",
            password="TestPass123!",
        )
        self.author.profile.small_group = self.group
        self.author.profile.save()

        self.same_group_user = User.objects.create_user(
            username="same_group",
            password="TestPass123!",
        )
        self.same_group_user.profile.small_group = self.group
        self.same_group_user.profile.save()

        self.other_group_user = User.objects.create_user(
            username="other_group",
            password="TestPass123!",
        )
        self.other_group_user.profile.small_group = self.other_group
        self.other_group_user.profile.save()

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
            small_group_at_post=small_group,
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
    """CS-CORE.4C locks current reflection privacy behavior without changing it."""

    def setUp(self):
        self.old_group = SmallGroup.objects.create(name="Invariant Old Group")
        self.new_group = SmallGroup.objects.create(name="Invariant New Group")
        self.other_group = SmallGroup.objects.create(name="Invariant Other Group")
        self.unmapped_group = SmallGroup.objects.create(name="Invariant Unmapped Group")
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
        self.old_group.church_structure_unit = self.old_unit
        self.old_group.save()
        self.new_group.church_structure_unit = self.new_unit
        self.new_group.save()
        self.other_group.church_structure_unit = self.other_unit
        self.other_group.save()

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

    def create_user(self, username, *, group=None):
        user = User.objects.create_user(username=username, password="TestPass123!")
        if group is not None:
            user.profile.small_group = group
            user.profile.save()
        return user

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
        structure_unit=None,
    ):
        return ReflectionComment.objects.create(
            user=user or self.author,
            active_plan=self.active_plan,
            plan_day=self.day,
            parent=parent,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=visibility,
            small_group_at_post=small_group,
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

    def test_structure_unit_snapshot_does_not_drive_visibility(self):
        mismatched_snapshot_post = self.make_reflection(
            user=self.author,
            body="Mismatched structure snapshot",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
            structure_unit=self.new_unit,
        )

        self.assertTrue(mismatched_snapshot_post.can_be_seen_by(self.old_group_member))
        self.assertFalse(mismatched_snapshot_post.can_be_seen_by(self.new_group_member))
        self.assertIn(
            mismatched_snapshot_post.id,
            self.reflection_ids_visible_by_filter(self.old_group_member),
        )
        self.assertNotIn(
            mismatched_snapshot_post.id,
            self.reflection_ids_visible_by_filter(self.new_group_member),
        )
        self.assertEqual(
            self.passage_wall_group_ids_for(self.old_group_member),
            {mismatched_snapshot_post.id},
        )
        self.assertEqual(self.passage_wall_group_ids_for(self.new_group_member), set())

    def test_new_group_reflection_stamps_legacy_group_and_structure_unit(self):
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
        self.assertEqual(comment.small_group_at_post, self.old_group)
        self.assertEqual(comment.structure_unit_at_post, self.old_unit)
        self.assertTrue(comment.can_be_seen_by(self.old_group_member))
        self.assertFalse(comment.can_be_seen_by(self.new_group_member))

    def test_new_group_reflection_with_unmapped_group_leaves_structure_unit_empty(self):
        unmapped_user = self.create_user(
            "invariant_unmapped_author",
            group=self.unmapped_group,
        )
        PlanEnrollment.objects.create(user=unmapped_user, active_plan=self.active_plan)

        self.client.login(username=unmapped_user.username, password="TestPass123!")
        response = self.client.post(
            reverse("add_comment", args=[self.active_plan.id, self.day.id, 0]),
            {
                "body": "Unmapped group reflection",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        comment = ReflectionComment.objects.get(body="Unmapped group reflection")
        self.assertEqual(comment.visibility, ReflectionComment.VISIBILITY_GROUP)
        self.assertEqual(comment.small_group_at_post, self.unmapped_group)
        self.assertIsNone(comment.structure_unit_at_post)
        self.assertTrue(comment.can_be_seen_by(unmapped_user))
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
                self.assertEqual(comment.small_group_at_post, self.old_group)
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
        self.assertEqual(reply.small_group_at_post, parent.small_group_at_post)
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
        self.assertEqual(reply.small_group_at_post, parent.small_group_at_post)
        self.assertEqual(reply.structure_unit_at_post, parent.structure_unit_at_post)
        self.assertFalse(reply.can_be_seen_by(self.other_group_user))

    def test_group_post_keeps_historical_snapshot_after_author_transfer(self):
        post = self.make_reflection(
            user=self.author,
            body="Old group snapshot",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.old_group,
        )

        self.author.profile.small_group = self.new_group
        self.author.profile.save()

        post.refresh_from_db()
        self.assertEqual(post.small_group_at_post, self.old_group)
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
        self.author.profile.small_group = self.new_group
        self.author.profile.save()

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

        self.assertEqual(post.small_group_at_post, self.old_group)
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
        self.assertEqual(post.small_group_at_post, self.old_group)
        self.assertEqual(post.structure_unit_at_post, self.old_unit)
        self.assertTrue(post.can_be_seen_by(self.old_group_member))
        self.assertFalse(post.can_be_seen_by(self.new_group_member))

    def test_top_level_private_or_church_edit_to_group_stamps_current_profile_group(self):
        self.author.profile.small_group = self.new_group
        self.author.profile.save()
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
                self.assertEqual(post.small_group_at_post, self.new_group)
                self.assertEqual(post.structure_unit_at_post, self.new_unit)
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
        self.assertIsNone(post.small_group_at_post)
        self.assertIsNone(post.structure_unit_at_post)


class GroupProgressPrivacyInvariantTests(TestCase):
    """CS-CORE.4C locks current group-progress roster and permission behavior."""

    def setUp(self):
        self.district = District.objects.create(name="Invariant District")
        self.other_district = District.objects.create(name="Invariant Other District")
        self.group = SmallGroup.objects.create(
            name="Invariant Progress Group",
            district=self.district,
        )
        self.other_group = SmallGroup.objects.create(
            name="Invariant Progress Other Group",
            district=self.other_district,
        )
        self.group_unit = self.create_unit("INV-PROGRESS-GROUP")
        self.other_group_unit = self.create_unit("INV-PROGRESS-OTHER")
        self.group.church_structure_unit = self.group_unit
        self.group.save()
        self.other_group.church_structure_unit = self.other_group_unit
        self.other_group.save()

        self.viewer = self.create_user("progress_viewer", group=self.group)
        self.same_group_member = self.create_user("progress_same", group=self.group)
        self.profile_only_member = self.create_user("progress_profile_only", group=self.group)
        self.other_group_member = self.create_user(
            "progress_other",
            group=self.other_group,
        )
        self.no_group_user = self.create_user("progress_no_group")
        self.membership_only_user = self.create_user("progress_membership_only")
        self.staff = User.objects.create_user(
            username="progress_staff",
            password="TestPass123!",
            is_staff=True,
        )

        ChurchStructureMembership.objects.create(
            user=self.membership_only_user,
            unit=self.group_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

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
        if group is not None:
            user.profile.small_group = group
            user.profile.save()
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

    def progress_response_for(self, user, *, group=None):
        self.client.login(username=user.username, password="TestPass123!")
        params = {}
        if group is not None:
            params["group"] = group.id
        response = self.client.get(reverse("my_group_progress"), params)
        self.assertEqual(response.status_code, 200)
        self.client.logout()
        return response

    def row_usernames(self, response):
        return {
            row["member"].username
            for row in response.context["member_rows"]
        }

    def accessible_group_ids(self, user):
        return set(get_accessible_progress_groups(user).values_list("id", flat=True))

    def test_roster_stays_profile_small_group_driven_not_membership_driven(self):
        response = self.progress_response_for(self.viewer, group=self.group)

        self.assertEqual(response.context["selected_group"], self.group)
        self.assertEqual(
            self.row_usernames(response),
            {"progress_profile_only", "progress_same", "progress_viewer"},
        )
        self.assertNotIn("progress_membership_only", self.row_usernames(response))
        self.assertNotIn("progress_other", self.row_usernames(response))
        self.assertNotIn("progress_no_group", self.row_usernames(response))

    def test_no_group_user_with_membership_still_gets_safe_empty_progress_state(self):
        membership_only_viewer = self.create_user("progress_membership_viewer")
        self.create_membership(membership_only_viewer, self.group_unit)

        response = self.progress_response_for(membership_only_viewer)

        self.assertIsNone(response.context["selected_group"])
        self.assertEqual(list(response.context["member_rows"]), [])
        self.assertContains(response, "You are not assigned to a small group yet.")
        self.assertEqual(self.accessible_group_ids(membership_only_viewer), set())

    def test_ordinary_own_group_permission_ignores_unrelated_membership(self):
        self.create_membership(self.viewer, self.other_group_unit)

        self.assertTrue(can_view_group_progress_for(self.viewer, self.group))
        self.assertFalse(can_view_group_progress_for(self.viewer, self.other_group))
        self.assertEqual(self.accessible_group_ids(self.viewer), {self.group.id})

        response = self.progress_response_for(self.viewer, group=self.other_group)

        self.assertEqual(response.context["selected_group"], self.group)

    def test_legacy_group_leader_can_view_assigned_group_only(self):
        leader = self.create_user("progress_group_leader")
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=self.other_group,
        )

        self.assertFalse(can_view_group_progress_for(leader, self.group))
        self.assertTrue(can_view_group_progress_for(leader, self.other_group))
        self.assertEqual(self.accessible_group_ids(leader), {self.other_group.id})

    def test_legacy_district_leader_can_view_in_scope_groups_only(self):
        district_group_b = SmallGroup.objects.create(
            name="Invariant District Group B",
            district=self.district,
        )
        leader = self.create_user("progress_district_leader")
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            district=self.district,
        )

        self.assertTrue(can_view_group_progress_for(leader, self.group))
        self.assertTrue(can_view_group_progress_for(leader, district_group_b))
        self.assertFalse(can_view_group_progress_for(leader, self.other_group))
        self.assertEqual(
            self.accessible_group_ids(leader),
            {self.group.id, district_group_b.id},
        )

    def test_staff_and_all_progress_role_can_view_all_active_groups(self):
        pastor = self.create_user("progress_pastor")
        ChurchRoleAssignment.objects.create(
            user=pastor,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        self.assertTrue(can_view_group_progress_for(self.staff, self.group))
        self.assertTrue(can_view_group_progress_for(self.staff, self.other_group))
        self.assertTrue(can_view_group_progress_for(pastor, self.group))
        self.assertTrue(can_view_group_progress_for(pastor, self.other_group))

        response = self.progress_response_for(self.staff, group=self.other_group)

        self.assertEqual(response.context["selected_group"], self.other_group)


class GroupProgressShadowModeTests(TestCase):
    """CS-CORE.4E group-progress membership-core shadow mode (comparison only).

    The shadow layer computes a membership-core candidate default/roster alongside
    the legacy answer. It must never change the visible roster, the default selected
    group, or permissions, and ordinary membership must never grant progress access.
    """

    def setUp(self):
        self.district = District.objects.create(name="Shadow District")
        self.other_district = District.objects.create(name="Shadow Other District")
        self.group_unit = self.create_unit("SHADOW-GROUP")
        self.other_group_unit = self.create_unit("SHADOW-OTHER")
        self.group = SmallGroup.objects.create(
            name="Shadow Group",
            district=self.district,
            church_structure_unit=self.group_unit,
        )
        self.other_group = SmallGroup.objects.create(
            name="Shadow Other Group",
            district=self.other_district,
            church_structure_unit=self.other_group_unit,
        )

        # Viewer belongs to self.group under both legacy and membership sources.
        self.viewer = self.create_user("shadow_viewer", group=self.group)
        self.create_membership(self.viewer, self.group_unit)

        self.plan = ReadingPlan.objects.create(name="Shadow Plan", is_active=True)
        self.day = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=1,
            reading_text="John 1",
            memory_verse="John 1:1",
        )
        self.active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=timezone.localdate(),
            title="Shadow Active Plan",
        )
        PlanEnrollment.objects.create(user=self.viewer, active_plan=self.active_plan)

    def create_user(self, username, *, group=None):
        user = User.objects.create_user(username=username, password="TestPass123!")
        if group is not None:
            user.profile.small_group = group
            user.profile.save()
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

    def progress_response_for(self, user, *, group=None):
        self.client.login(username=user.username, password="TestPass123!")
        params = {}
        if group is not None:
            params["group"] = group.id
        response = self.client.get(reverse("my_group_progress"), params)
        self.assertEqual(response.status_code, 200)
        self.client.logout()
        return response

    def row_usernames(self, response):
        return {row["member"].username for row in response.context["member_rows"]}

    def shadow_for(self, user, group):
        return compute_group_progress_shadow(user, group)

    def test_visible_roster_and_default_stay_legacy_not_membership(self):
        membership_only = self.create_user("shadow_membership_only")
        self.create_membership(membership_only, self.group_unit)

        response = self.progress_response_for(self.viewer, group=self.group)

        # Legacy default selected group and legacy roster are unchanged.
        self.assertEqual(response.context["selected_group"], self.group)
        self.assertEqual(self.row_usernames(response), {"shadow_viewer"})
        self.assertNotIn("shadow_membership_only", self.row_usernames(response))

    def test_shadow_context_present_but_not_user_visible(self):
        response = self.progress_response_for(self.viewer, group=self.group)

        shadow = response.context["group_progress_shadow"]
        self.assertIsInstance(shadow, GroupProgressShadow)

        # Internal shadow labels and reason codes are never rendered to the page.
        self.assertNotContains(response, "group_progress_shadow")
        self.assertNotContains(response, "membership_candidate_group_id")
        self.assertNotContains(response, "would_gain")
        self.assertNotContains(response, REASON_DEFAULT_SAME)
        self.assertNotContains(response, REASON_ROSTER_SAME)

    def test_same_default_and_same_roster_when_sources_agree(self):
        shadow = self.shadow_for(self.viewer, self.group)

        self.assertEqual(shadow.legacy_selected_group_id, self.group.id)
        self.assertEqual(shadow.membership_candidate_group_id, self.group.id)
        self.assertTrue(shadow.same_default)
        self.assertTrue(shadow.same_roster)
        self.assertEqual(shadow.would_gain_user_ids, frozenset())
        self.assertEqual(shadow.would_lose_user_ids, frozenset())
        self.assertIn(REASON_DEFAULT_SAME, shadow.reason_codes)
        self.assertIn(REASON_ROSTER_SAME, shadow.reason_codes)

    def test_would_gain_membership_only_member(self):
        gain_user = self.create_user("shadow_gain")
        self.create_membership(gain_user, self.group_unit)

        shadow = self.shadow_for(self.viewer, self.group)

        self.assertIn(gain_user.id, shadow.would_gain_user_ids)
        self.assertNotIn(gain_user.id, shadow.legacy_roster_user_ids)
        self.assertIn(gain_user.id, shadow.membership_roster_user_ids)
        self.assertFalse(shadow.same_roster)
        self.assertIn(REASON_ROSTER_WOULD_GAIN, shadow.reason_codes)

    def test_would_lose_profile_only_member(self):
        lose_user = self.create_user("shadow_lose", group=self.group)

        shadow = self.shadow_for(self.viewer, self.group)

        self.assertIn(lose_user.id, shadow.would_lose_user_ids)
        self.assertIn(lose_user.id, shadow.legacy_roster_user_ids)
        self.assertNotIn(lose_user.id, shadow.membership_roster_user_ids)
        self.assertFalse(shadow.same_roster)
        self.assertIn(REASON_ROSTER_WOULD_LOSE, shadow.reason_codes)

    def test_profile_membership_mismatch_records_default_divergence(self):
        mismatch_user = self.create_user("shadow_mismatch", group=self.group)
        self.create_membership(mismatch_user, self.other_group_unit)

        shadow = self.shadow_for(mismatch_user, self.group)

        self.assertEqual(shadow.legacy_selected_group_id, self.group.id)
        self.assertEqual(shadow.membership_candidate_group_id, self.other_group.id)
        self.assertFalse(shadow.same_default)
        self.assertIn(REASON_PROFILE_MEMBERSHIP_MISMATCH, shadow.reason_codes)
        self.assertIn(REASON_DEFAULT_WOULD_CHANGE, shadow.reason_codes)

    def test_multiple_active_primary_memberships_fail_closed(self):
        ambiguous_user = self.create_user("shadow_ambiguous", group=self.group)
        # bulk_create bypasses the single-active-primary model validation so the
        # helper's fail-closed handling of an ambiguous state is exercised.
        today = timezone.localdate()
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=ambiguous_user,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
                ChurchStructureMembership(
                    user=ambiguous_user,
                    unit=self.other_group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
            ]
        )

        shadow = self.shadow_for(ambiguous_user, self.group)

        # Candidate refuses to silently choose a default group.
        self.assertIsNone(shadow.membership_candidate_group_id)
        self.assertIn(
            REASON_MEMBERSHIP_MULTIPLE_ACTIVE_PRIMARY, shadow.reason_codes
        )
        self.assertFalse(shadow.same_default)

    def test_unmapped_selected_group_yields_empty_candidate_roster(self):
        unmapped_group = SmallGroup.objects.create(
            name="Shadow Unmapped Group",
            district=self.district,
            church_structure_unit=None,
        )
        unmapped_member = self.create_user("shadow_unmapped", group=unmapped_group)
        PlanEnrollment.objects.create(
            user=unmapped_member, active_plan=self.active_plan
        )

        shadow = self.shadow_for(unmapped_member, unmapped_group)
        self.assertEqual(shadow.membership_roster_user_ids, frozenset())
        self.assertIn(REASON_SELECTED_GROUP_UNMAPPED, shadow.reason_codes)

        # Legacy page still works for the unmapped group.
        response = self.progress_response_for(unmapped_member, group=unmapped_group)
        self.assertEqual(response.context["selected_group"], unmapped_group)
        self.assertIn("shadow_unmapped", self.row_usernames(response))

    def test_ordinary_membership_does_not_grant_other_group_progress(self):
        # Ordinary user belongs to self.group legacy-wise, but their single active
        # primary membership points into other_group's unit. Membership must not
        # grant access to other_group's progress; permission stays legacy-only.
        ordinary_user = self.create_user("shadow_ordinary", group=self.group)
        self.create_membership(ordinary_user, self.other_group_unit)
        PlanEnrollment.objects.create(user=ordinary_user, active_plan=self.active_plan)

        self.assertFalse(can_view_group_progress_for(ordinary_user, self.other_group))
        self.assertEqual(
            set(
                get_accessible_progress_groups(ordinary_user).values_list(
                    "id", flat=True
                )
            ),
            {self.group.id},
        )

        response = self.progress_response_for(ordinary_user, group=self.other_group)
        # Falls back to the only accessible (own legacy) group.
        self.assertEqual(response.context["selected_group"], self.group)

    def test_no_selected_group_reports_only_default_divergence(self):
        membership_only = self.create_user("shadow_only_member")
        self.create_membership(membership_only, self.group_unit)

        shadow = self.shadow_for(membership_only, None)

        self.assertIsNone(shadow.legacy_selected_group_id)
        self.assertEqual(shadow.membership_candidate_group_id, self.group.id)
        self.assertEqual(shadow.legacy_roster_user_ids, frozenset())
        self.assertEqual(shadow.membership_roster_user_ids, frozenset())
        self.assertIn(REASON_LEGACY_NO_SELECTED_GROUP, shadow.reason_codes)
        self.assertIn(REASON_DEFAULT_WOULD_CHANGE, shadow.reason_codes)

    def test_no_active_primary_membership_fails_closed_on_default(self):
        no_membership_user = self.create_user("shadow_no_membership", group=self.group)

        shadow = self.shadow_for(no_membership_user, self.group)

        self.assertIsNone(shadow.membership_candidate_group_id)
        self.assertIn(REASON_MEMBERSHIP_NO_ACTIVE_PRIMARY, shadow.reason_codes)

    def test_shadow_roster_divergence_agrees_with_audit_command(self):
        gain_user = self.create_user("shadow_agree_gain")
        self.create_membership(gain_user, self.group_unit)
        lose_user = self.create_user("shadow_agree_lose", group=self.group)

        shadow = self.shadow_for(self.viewer, self.group)
        audit = run_audit()

        # self.other_group has no members or memberships, so the only roster
        # divergence the read-only audit can find is in self.group, matching the
        # helper's would-gain / would-lose sets exactly.
        self.assertEqual(
            audit["stats"]["progress_would_gain"],
            len(shadow.would_gain_user_ids),
        )
        self.assertEqual(
            audit["stats"]["progress_would_lose"],
            len(shadow.would_lose_user_ids),
        )
        self.assertEqual(shadow.would_gain_user_ids, frozenset({gain_user.id}))
        self.assertEqual(shadow.would_lose_user_ids, frozenset({lose_user.id}))


class GroupProgressShadowAuditCommandTests(TestCase):
    """CS-CORE.4E.1 operational group-progress shadow audit command tests.

    The command is read-only: it compares the legacy ``Profile.small_group`` roster
    and default against a membership-core candidate and writes nothing. It never
    switches the runtime source, changes a roster/default, or grants progress access.
    """

    def run_command(self, *args):
        output = StringIO()
        call_command("audit_group_progress_shadow", *args, stdout=output)
        return output.getvalue()

    def create_unit(self, code, *, unit_type=None, parent=None):
        return ChurchStructureUnit.objects.create(
            unit_type=unit_type or ChurchStructureUnit.UNIT_SMALL_GROUP,
            code=code,
            name=code,
            parent=parent,
        )

    def create_group(self, name, *, unit=None):
        return SmallGroup.objects.create(name=name, church_structure_unit=unit)

    def create_user(self, username, *, group=None):
        user = User.objects.create_user(username=username, password="TestPass123!")
        if group is not None:
            user.profile.small_group = group
            user.profile.save()
        return user

    def create_membership(self, user, unit, **overrides):
        defaults = {
            "user": user,
            "unit": unit,
            "status": ChurchStructureMembership.STATUS_ACTIVE,
            "is_primary": True,
            "start_date": timezone.localdate(),
        }
        defaults.update(overrides)
        return ChurchStructureMembership.objects.create(**defaults)

    def assert_summary_count(self, output, key, count):
        self.assertIn(f"{key}: {count}", output)

    def test_command_runs_read_only_and_prints_summary(self):
        unit = self.create_unit("AUDIT-GP-RO")
        group = self.create_group("Audit GP Read Only", unit=unit)
        user = self.create_user("audit_gp_ro", group=group)
        self.create_membership(user, unit)

        with CaptureQueriesContext(connection) as queries:
            output = self.run_command("--verbose")

        write_sql = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        ]
        self.assertEqual(write_sql, [])
        self.assertIn("READ-ONLY: no data was changed.", output)
        self.assertIn("Runtime remains legacy-driven.", output)
        self.assert_summary_count(output, "groups_checked", 1)

    def test_same_roster_group_reports_same_and_no_drift(self):
        unit = self.create_unit("AUDIT-GP-SAME")
        group = self.create_group("Audit GP Same", unit=unit)
        user = self.create_user("audit_gp_same", group=group)
        self.create_membership(user, unit)

        output = self.run_command("--fail-on-drift")

        self.assert_summary_count(output, "groups_checked", 1)
        self.assert_summary_count(output, "groups_same_roster", 1)
        self.assert_summary_count(output, "groups_with_roster_gain", 0)
        self.assert_summary_count(output, "groups_with_roster_loss", 0)
        self.assert_summary_count(output, "progress_would_gain", 0)
        self.assert_summary_count(output, "progress_would_lose", 0)
        self.assert_summary_count(output, "default_would_change", 0)

    def test_would_gain_membership_only_user_reported(self):
        unit = self.create_unit("AUDIT-GP-GAIN")
        group = self.create_group("Audit GP Gain", unit=unit)
        # Membership under the group's unit, but no legacy Profile.small_group.
        gain_user = self.create_user("audit_gp_gain")
        self.create_membership(gain_user, unit)

        output = self.run_command("--verbose")

        self.assert_summary_count(output, "progress_would_gain", 1)
        self.assert_summary_count(output, "groups_with_roster_gain", 1)
        self.assertIn("audit_gp_gain", output)

    def test_would_lose_profile_only_user_reported(self):
        unit = self.create_unit("AUDIT-GP-LOSE")
        group = self.create_group("Audit GP Lose", unit=unit)
        # Legacy default group but no active primary membership.
        self.create_user("audit_gp_lose", group=group)

        output = self.run_command()

        self.assert_summary_count(output, "progress_would_lose", 1)
        self.assert_summary_count(output, "groups_with_roster_loss", 1)
        self.assert_summary_count(output, "membership_no_active_primary", 1)

    def test_unmapped_group_reported_and_candidate_fails_closed(self):
        group = self.create_group("Audit GP Unmapped", unit=None)
        self.create_user("audit_gp_unmapped", group=group)

        output = self.run_command()

        self.assert_summary_count(output, "selected_group_unmapped", 1)
        # Legacy member is present but the candidate roster is empty -> would lose.
        self.assert_summary_count(output, "progress_would_lose", 1)

    def test_multiple_active_primary_membership_fails_closed(self):
        unit = self.create_unit("AUDIT-GP-MULTI")
        other_unit = self.create_unit("AUDIT-GP-MULTI-OTHER")
        group = self.create_group("Audit GP Multi", unit=unit)
        user = self.create_user("audit_gp_multi", group=group)
        # bulk_create bypasses single-active-primary validation to exercise the
        # fail-closed ambiguity handling, consistent with existing 4E tests.
        today = timezone.localdate()
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=user,
                    unit=unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
                ChurchStructureMembership(
                    user=user,
                    unit=other_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
            ]
        )

        output = self.run_command("--verbose")

        self.assert_summary_count(output, "membership_multiple_active_primary", 1)

    def test_group_id_limits_output_to_that_group(self):
        unit_one = self.create_unit("AUDIT-GP-ONE")
        unit_two = self.create_unit("AUDIT-GP-TWO")
        group_one = self.create_group("Audit GP One", unit=unit_one)
        group_two = self.create_group("Audit GP Two", unit=unit_two)
        user_one = self.create_user("audit_gp_one", group=group_one)
        self.create_membership(user_one, unit_one)
        user_two = self.create_user("audit_gp_two", group=group_two)
        self.create_membership(user_two, unit_two)

        output = self.run_command("--group-id", str(group_one.id))

        self.assert_summary_count(output, "groups_checked", 1)
        self.assertIn(f"group_id_filter: {group_one.id}", output)

    def test_fail_on_drift_raises_when_drift_exists(self):
        unit = self.create_unit("AUDIT-GP-DRIFT")
        group = self.create_group("Audit GP Drift", unit=unit)
        self.create_user("audit_gp_drift", group=group)

        with self.assertRaisesMessage(CommandError, "progress_would_lose=1"):
            self.run_command("--fail-on-drift")

    def test_command_does_not_write_any_rows(self):
        unit = self.create_unit("AUDIT-GP-NOWRITE")
        group = self.create_group("Audit GP No Write", unit=unit)
        user = self.create_user("audit_gp_nowrite", group=group)
        self.create_membership(user, unit)
        plan = ReadingPlan.objects.create(name="Audit GP Plan", is_active=True)

        before = {
            "users": User.objects.count(),
            "groups": SmallGroup.objects.count(),
            "memberships": ChurchStructureMembership.objects.count(),
            "plans": ReadingPlan.objects.count(),
        }

        self.run_command("--verbose", "--fail-on-drift")

        self.assertEqual(
            before,
            {
                "users": User.objects.count(),
                "groups": SmallGroup.objects.count(),
                "memberships": ChurchStructureMembership.objects.count(),
                "plans": ReadingPlan.objects.count(),
            },
        )
        # Sanity: the plan we created is still the only one.
        self.assertEqual(ReadingPlan.objects.filter(id=plan.id).count(), 1)


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
        self.group = SmallGroup.objects.create(name="Rainbow 4")

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
            small_group_at_post=self.group,
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
            small_group_at_post=self.group,
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
            small_group_at_post=self.group,
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
        self.user.profile.small_group = None
        self.user.profile.save()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You are not assigned to a small group yet.")

    def test_group_progress_shows_same_group_members_only(self):
        other_group = SmallGroup.objects.create(name="Other Group")

        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.other_user.profile.small_group = self.group
        self.other_user.profile.save()

        outside_user = User.objects.create_user(
            username="outside",
            email="outside@example.com",
            password="testpass123",
        )
        outside_user.profile.small_group = other_group
        outside_user.profile.save()

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
        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.other_user.profile.small_group = self.group
        self.other_user.profile.save()

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
        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.other_user.profile.small_group = self.group
        self.other_user.profile.save()

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

    def test_group_leader_can_view_assigned_group_progress(self):
        self.set_language("en")
        leader = User.objects.create_user(
            username="group_leader",
            email="leader@example.com",
            password="testpass123",
        )
        assigned_group = SmallGroup.objects.create(name="Assigned Group")
        other_group = SmallGroup.objects.create(name="Outside Group")
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=assigned_group,
        )

        self.client.login(username="group_leader", password="testpass123")

        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assigned Group")
        self.assertNotContains(response, "Outside Group")

    def test_district_leader_can_select_group_in_assigned_district(self):
        self.set_language("en")
        district = District.objects.create(name="North District")
        group_a = SmallGroup.objects.create(name="North Group A", district=district)
        group_b = SmallGroup.objects.create(name="North Group B", district=district)
        leader = User.objects.create_user(
            username="district_leader",
            email="district@example.com",
            password="testpass123",
        )
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            district=district,
        )

        self.client.login(username="district_leader", password="testpass123")

        response = self.client.get(
            reverse("my_group_progress"),
            {"group": group_b.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "North Group A")
        self.assertContains(response, "North Group B")
        self.assertContains(response, f'value="{group_b.id}" selected')

    def test_district_leader_cannot_access_group_outside_district(self):
        self.set_language("en")
        district = District.objects.create(name="East District")
        outside_district = District.objects.create(name="West District")
        inside_group = SmallGroup.objects.create(name="East Group", district=district)
        outside_group = SmallGroup.objects.create(
            name="West Group",
            district=outside_district,
        )
        leader = User.objects.create_user(
            username="limited_leader",
            email="limited@example.com",
            password="testpass123",
        )
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            district=district,
        )

        self.client.login(username="limited_leader", password="testpass123")

        response = self.client.get(
            reverse("my_group_progress"),
            {"group": outside_group.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "East Group")
        self.assertNotContains(response, "West Group")
        self.assertEqual(response.context["selected_group"], inside_group)

    def test_staff_can_select_any_group_progress(self):
        self.set_language("en")
        other_group = SmallGroup.objects.create(name="Staff Visible Group")

        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("my_group_progress"),
            {"group": other_group.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff Visible Group")
        self.assertEqual(response.context["selected_group"], other_group)

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

        self.user.profile.small_group = self.group
        self.user.profile.save()
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

        self.user.profile.small_group = self.group
        self.user.profile.save()
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

        self.user.profile.small_group = self.group
        self.user.profile.save()

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
            scope_type=ServiceEvent.SCOPE_GLOBAL,
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

        self.user.profile.small_group = self.group
        self.user.profile.save()

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
        self.assertEqual(comment.small_group_at_post, self.group)


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

        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.other_user.profile.small_group = self.group
        self.other_user.profile.save()

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
            small_group_at_post=self.group,
            body="Group reflection.",
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Group reflection.")


    def test_group_reflection_is_not_visible_to_different_group_member(self):
        other_group = SmallGroup.objects.create(name="Other Group")

        self.day1.reading_text = "John 1"
        self.day1.save()

        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.other_user.profile.small_group = other_group
        self.other_user.profile.save()

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
            small_group_at_post=self.group,
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

        self.user.profile.small_group = self.group
        self.user.profile.save()

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
        self.user.profile.small_group = self.group
        self.user.profile.save()

        comment = ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group_at_post=self.group,
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
            small_group_at_post=self.group,
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
            small_group_at_post=self.group,
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

        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.other_user.profile.small_group = self.group
        self.other_user.profile.save()

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
            small_group_at_post=self.group,
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
        self.group = SmallGroup.objects.create(
            name="Rainbow 4",
            church_structure_unit=self.group_unit,
        )
        self.other_group = SmallGroup.objects.create(
            name="Rainbow 5",
            church_structure_unit=self.other_group_unit,
        )

        self.user = User.objects.create_user(
            username="member",
            password="TestPass123!",
        )
        self.user.profile.small_group = self.group
        self.user.profile.save()

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

    def make_event(self, *, title_en, days_from_now=1, scope=None, small_group=None,
                   status=None, start_datetime=None):
        return ServiceEvent.objects.create(
            title=title_en,
            title_en=title_en,
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=start_datetime or timezone.now() + timedelta(days=days_from_now),
            scope_type=scope or ServiceEvent.SCOPE_GLOBAL,
            small_group=small_group,
            status=status or ServiceEvent.STATUS_PUBLISHED,
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

    def make_meeting(self, *, small_group, days_from_now=2,
                     lesson_title_en="Lesson One", meeting_datetime=None):
        series = BibleStudySeries.objects.create(
            title="查经系列",
            title_en="Study Series",
            scope_type=BibleStudySeries.SCOPE_GLOBAL,
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
        return BibleStudyMeeting.objects.create(
            lesson=lesson,
            small_group=small_group,
            meeting_datetime=meeting_datetime or timezone.now() + timedelta(days=days_from_now),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )

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
        event = self.make_event(title_en="Sunday Service Gamma")
        self.make_assignment(event, confirmed=False)

        response = self.get_home()
        content = response.content.decode()

        # Pending item is a full row in "Needs your attention" (one confirm link),
        # and the same gathering shows only a compact serving note in This Week.
        self.assertEqual(content.count("Confirm in My Serving"), 1)
        self.assertContains(response, "You are serving — pending confirmation")

    def test_church_gatherings_shows_visible_upcoming(self):
        self.make_event(title_en="Midweek Prayer Gathering")

        response = self.get_home()

        self.assertContains(response, "Church Gatherings this week")
        self.assertContains(response, "Midweek Prayer Gathering")

    def test_church_gathering_datetime_is_member_formatted(self):
        self.make_event(
            title_en="Formatted Gathering",
            start_datetime=datetime(2026, 6, 12, 19, 30, tzinfo=datetime_timezone.utc),
        )

        response = self.get_home()

        self.assertContains(response, "Formatted Gathering")
        self.assertContains(response, "Fri, Jun 12, 7:30 PM")
        self.assertNotContains(response, "June 12, 2026")

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
        self.make_event(
            title_en="Other Group Only Meeting",
            scope=ServiceEvent.SCOPE_SMALL_GROUP,
            small_group=self.other_group,
        )

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
        self.make_meeting(small_group=self.group, lesson_title_en="My Group Lesson")

        response = self.get_home()

        self.assertContains(response, "Small group Bible study")
        self.assertContains(response, "My Group Lesson")

    def test_v2_meeting_datetime_is_member_formatted(self):
        self.make_meeting(
            small_group=self.group,
            lesson_title_en="Formatted Group Lesson",
            meeting_datetime=datetime(2026, 6, 12, 19, 30, tzinfo=datetime_timezone.utc),
        )

        response = self.get_home()

        self.assertContains(response, "Formatted Group Lesson")
        self.assertContains(response, "Fri, Jun 12, 7:30 PM")
        self.assertNotContains(response, "June 12, 2026")

    def test_other_group_meeting_not_shown(self):
        self.make_meeting(
            small_group=self.other_group,
            lesson_title_en="Other Group Lesson",
        )

        response = self.get_home()

        self.assertNotContains(response, "Other Group Lesson")

    def test_no_small_group_empty_state(self):
        self.user.church_structure_memberships.all().delete()
        self.user.profile.small_group = None
        self.user.profile.save()

        response = self.get_home()

        self.assertContains(
            response,
            "Your confirmed group membership is not ready yet, so no current Bible Study is available.",
        )

    def test_membership_only_user_sees_v2_meeting(self):
        self.user.profile.small_group = None
        self.user.profile.save()
        self.make_meeting(
            small_group=self.group,
            lesson_title_en="Membership Only Today Lesson",
        )

        response = self.get_home()

        self.assertContains(response, "Small group Bible study")
        self.assertContains(response, "Membership Only Today Lesson")

    def test_profile_only_user_does_not_see_v2_meeting(self):
        self.user.church_structure_memberships.all().delete()
        self.make_meeting(
            small_group=self.group,
            lesson_title_en="Profile Only Today Hidden",
        )

        response = self.get_home()

        self.assertContains(
            response,
            "Your confirmed group membership is not ready yet, so no current Bible Study is available.",
        )
        self.assertNotContains(response, "Profile Only Today Hidden")

    def test_legacy_session_block_not_shown(self):
        series = BibleStudySeries.objects.create(
            title="旧查经系列",
            title_en="Legacy Series",
            scope_type=BibleStudySeries.SCOPE_GLOBAL,
            status=BibleStudySeries.STATUS_PUBLISHED,
            is_active=True,
        )
        BibleStudySession.objects.create(
            series=series,
            title="旧查经场次",
            title_en="Legacy Session Title",
            study_datetime=timezone.now() + timedelta(days=1),
            scope_type=BibleStudySession.SCOPE_GLOBAL,
            status=BibleStudySession.STATUS_PUBLISHED,
        )

        response = self.get_home()

        self.assertNotContains(response, "Legacy Session Title")

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
        self.make_event(title_en="Bilingual Gathering")

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
        meeting = self.make_meeting(small_group=self.group)
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )

        response = self.get_home()

        self.assertContains(response, "My role:")
        self.assertContains(response, "Discussion Leader")

    def test_multiple_linked_roles_shown(self):
        meeting = self.make_meeting(small_group=self.group)
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
        meeting = self.make_meeting(small_group=self.group)
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
        meeting = self.make_meeting(small_group=self.group)
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
        self.other_user.profile.small_group = self.other_group
        self.other_user.profile.save()
        other_meeting = self.make_meeting(small_group=self.other_group)
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
        meeting = self.make_meeting(small_group=self.group)
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )

        response = self.get_home()

        self.assertNotContains(response, "My role:")
        self.assertNotContains(response, "Discussion Leader")

    def test_role_line_hidden_when_no_linked_role(self):
        self.make_meeting(small_group=self.group)

        response = self.get_home()

        self.assertContains(response, "Small group Bible study")
        self.assertNotContains(response, "My role:")
        self.assertNotContains(response, "My roles:")

    def test_cancelled_meeting_role_not_shown(self):
        meeting = self.make_meeting(small_group=self.group)
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
        meeting = self.make_meeting(small_group=self.group)
        self.add_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )

        response = self.get_home(language="zh")

        self.assertContains(response, "我的角色：")
        self.assertContains(response, "查经带领")

    def test_no_role_management_control_on_today(self):
        meeting = self.make_meeting(small_group=self.group)
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
        meeting = self.make_meeting(small_group=self.group)
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


class ReadingPrivacyMembershipReadinessAuditCommandTests(TestCase):
    """CS-CORE.4B readiness audit command tests. The command is read-only."""

    def run_audit_command(self, *args):
        output = StringIO()
        call_command(
            "audit_reading_privacy_membership_readiness",
            *args,
            stdout=output,
        )
        return output.getvalue()

    def create_unit(self, code, *, unit_type=None, parent=None):
        return ChurchStructureUnit.objects.create(
            unit_type=unit_type or ChurchStructureUnit.UNIT_SMALL_GROUP,
            code=code,
            name=code,
            parent=parent,
        )

    def create_mapped_group(self, name, *, unit=None):
        unit = unit or self.create_unit(name.upper().replace(" ", "-")[:32])
        group = SmallGroup.objects.create(name=name, church_structure_unit=unit)
        return group, unit

    def create_user(self, username, *, group=None):
        user = User.objects.create_user(username=username)
        if group is not None:
            user.profile.small_group = group
            user.profile.save()
        return user

    def create_membership(self, user, unit, **overrides):
        defaults = {
            "user": user,
            "unit": unit,
            "status": ChurchStructureMembership.STATUS_ACTIVE,
            "is_primary": True,
            "start_date": timezone.localdate(),
        }
        defaults.update(overrides)
        return ChurchStructureMembership.objects.create(**defaults)

    def create_reflection(self, group, *, user=None, **overrides):
        plan = ReadingPlan.objects.create(
            name=f"Audit Plan {ReadingPlan.objects.count() + 1}",
            is_active=True,
        )
        day = ReadingPlanDay.objects.create(
            plan=plan,
            day_number=1,
            reading_text="John 1",
            memory_verse="John 1:1",
        )
        user = user or self.create_user(
            f"audit_author_{User.objects.count() + 1}",
            group=group,
        )
        defaults = {
            "user": user,
            "plan_day": day,
            "scripture_ref_key": "John 1",
            "scripture_display_zh": "约翰福音 第 1 章",
            "scripture_display_en": "John 1",
            "visibility": ReflectionComment.VISIBILITY_GROUP,
            "small_group_at_post": group,
            "body": "Audit reflection",
        }
        defaults.update(overrides)
        return ReflectionComment.objects.create(**defaults)

    def create_duplicate_active_primaries(self, user, first_unit, second_unit):
        today = timezone.localdate()
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=user,
                    unit=first_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
                ChurchStructureMembership(
                    user=user,
                    unit=second_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
            ]
        )

    def assert_summary_count(self, output, category, count):
        self.assertIn(f"{category}: {count}", output)

    def test_command_runs_writes_nothing_and_has_no_apply_option(self):
        group, unit = self.create_mapped_group("Audit Read Only")
        user = self.create_user("audit_read_only", group=group)
        self.create_membership(user, unit)
        self.create_reflection(group, user=user)
        before_counts = {
            "comments": ReflectionComment.objects.count(),
            "memberships": ChurchStructureMembership.objects.count(),
            "groups": SmallGroup.objects.count(),
            "units": ChurchStructureUnit.objects.count(),
            "users": User.objects.count(),
            "plans": ReadingPlan.objects.count(),
            "days": ReadingPlanDay.objects.count(),
        }

        parser = ReadingPrivacyAuditCommand().create_parser(
            "manage.py",
            "audit_reading_privacy_membership_readiness",
        )
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        self.assertNotIn("--apply", option_strings)

        with CaptureQueriesContext(connection) as queries:
            output = self.run_audit_command("--verbose")

        write_sql = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE")
            )
        ]
        self.assertEqual(write_sql, [])
        self.assertIn("Audit only:", output)
        self.assertEqual(
            before_counts,
            {
                "comments": ReflectionComment.objects.count(),
                "memberships": ChurchStructureMembership.objects.count(),
                "groups": SmallGroup.objects.count(),
                "units": ChurchStructureUnit.objects.count(),
                "users": User.objects.count(),
                "plans": ReadingPlan.objects.count(),
                "days": ReadingPlanDay.objects.count(),
            },
        )

    def test_in_sync_case_reports_same_and_no_drift(self):
        group, unit = self.create_mapped_group("Audit In Sync")
        user = self.create_user("audit_in_sync", group=group)
        self.create_membership(user, unit)
        self.create_reflection(group, user=user)

        output = self.run_audit_command("--fail-on-drift")

        self.assert_summary_count(output, "same_visible", 1)
        self.assert_summary_count(output, "same_in_roster", 1)
        self.assert_summary_count(output, "would_gain", 0)
        self.assert_summary_count(output, "would_lose", 0)
        self.assert_summary_count(output, "user_profile_membership_mismatch", 0)

    def test_profile_only_case_reports_would_lose(self):
        group, _unit = self.create_mapped_group("Audit Profile Only")
        user = self.create_user("audit_profile_only", group=group)
        self.create_reflection(group, user=user)

        output = self.run_audit_command()

        self.assert_summary_count(output, "same_visible", 0)
        self.assert_summary_count(output, "same_in_roster", 0)
        self.assert_summary_count(output, "would_lose", 1)
        self.assert_summary_count(
            output, "user_profile_without_active_primary_membership", 1
        )

    def test_membership_only_case_reports_would_gain(self):
        group, unit = self.create_mapped_group("Audit Membership Only")
        user = self.create_user("audit_membership_only")
        self.create_membership(user, unit)
        self.create_reflection(group, user=user)

        output = self.run_audit_command()

        self.assert_summary_count(output, "would_gain", 1)
        self.assert_summary_count(
            output, "user_active_primary_without_profile_group", 1
        )

    def test_mismatch_reports_gain_loss_and_mismatch(self):
        group_a, unit_a = self.create_mapped_group("Audit Group A")
        group_b, unit_b = self.create_mapped_group("Audit Group B")
        user = self.create_user("audit_mismatch", group=group_a)
        self.create_membership(user, unit_b)
        self.create_reflection(group_a, user=user)
        self.create_reflection(group_b, user=user)

        output = self.run_audit_command()

        self.assert_summary_count(output, "would_gain", 1)
        self.assert_summary_count(output, "would_lose", 1)
        self.assert_summary_count(output, "user_profile_membership_mismatch", 1)
        self.assertNotEqual(unit_a, unit_b)

    def test_unmapped_group_fails_closed_and_reports_unmapped(self):
        group = SmallGroup.objects.create(name="Audit Unmapped")
        user = self.create_user("audit_unmapped", group=group)
        self.create_reflection(group, user=user)

        output = self.run_audit_command()

        self.assert_summary_count(output, "reflection_group_unmapped", 1)
        self.assert_summary_count(output, "progress_group_unmapped", 1)
        self.assert_summary_count(output, "would_lose", 1)

    def test_multiple_active_primary_memberships_fail_closed(self):
        group, unit = self.create_mapped_group("Audit Multi Primary")
        other_unit = self.create_unit("AUDIT-MULTI-OTHER")
        user = self.create_user("audit_multi_primary", group=group)
        self.create_duplicate_active_primaries(user, unit, other_unit)
        self.create_reflection(group, user=user)

        output = self.run_audit_command("--verbose")

        self.assert_summary_count(output, "multiple_active_primary_memberships", 1)
        self.assert_summary_count(output, "would_lose", 1)
        self.assertIn("active_primary_membership_ids=", output)

    def test_non_active_memberships_do_not_grant_candidate_membership(self):
        group, unit = self.create_mapped_group("Audit Inactive States")
        today = timezone.localdate()
        requested = self.create_user("audit_requested", group=group)
        ended = self.create_user("audit_ended", group=group)
        future = self.create_user("audit_future", group=group)
        self.create_reflection(group, user=requested)
        ChurchStructureMembership.objects.create(
            user=requested,
            unit=unit,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=True,
            start_date=today,
        )
        ChurchStructureMembership.objects.create(
            user=ended,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ENDED,
            is_primary=True,
            start_date=today - timedelta(days=10),
            end_date=today - timedelta(days=1),
        )
        ChurchStructureMembership.objects.create(
            user=future,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=today + timedelta(days=1),
        )

        output = self.run_audit_command()

        self.assert_summary_count(output, "would_lose", 3)
        self.assert_summary_count(
            output, "user_profile_without_active_primary_membership", 3
        )
        self.assert_summary_count(output, "multiple_active_primary_memberships", 0)

    def test_fail_on_drift_raises_only_when_risky_drift_exists(self):
        group, unit = self.create_mapped_group("Audit Clean")
        synced = self.create_user("audit_clean_synced", group=group)
        self.create_membership(synced, unit)
        self.create_user("audit_clean_nobody")
        self.create_reflection(group, user=synced)

        clean_output = self.run_audit_command("--fail-on-drift")
        self.assert_summary_count(clean_output, "same_visible", 1)
        self.assert_summary_count(clean_output, "same_out_of_roster", 1)

        drift_group, _drift_unit = self.create_mapped_group("Audit Drift")
        self.create_user("audit_drift", group=drift_group)

        with self.assertRaisesMessage(CommandError, "progress_would_lose=1"):
            self.run_audit_command("--fail-on-drift")

    def test_verbose_limit_outputs_representative_rows(self):
        group, _unit = self.create_mapped_group("Audit Verbose Limit")
        first = self.create_user("audit_limit_one", group=group)
        self.create_user("audit_limit_two", group=group)
        self.create_reflection(group, user=first)

        output = self.run_audit_command("--verbose", "--limit", "1")

        self.assertIn("details (drift and risk categories only):", output)
        self.assertIn("(verbose output stopped at --limit 1)", output)
        self.assertEqual(output.count("classification=would_lose"), 1)
