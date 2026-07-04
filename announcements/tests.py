from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from community_events.models import ActivitySignup, CommunityActivity
from core.module_registry import get_registered_module_keys
from core.today_providers import get_registered_today_provider_keys
from events.models import ServiceEvent
from ministry.models import TeamAssignment, TeamAssignmentMember
from studies.models import BibleStudyMeeting, BibleStudyMeetingRole

from .forms import AnnouncementForm
from .models import Announcement, AnnouncementAudienceScope
from .visibility import (
    member_visible_announcements_for,
    visible_announcements_for,
)

User = get_user_model()
MODULES_WITHOUT_ANNOUNCEMENTS = tuple(
    key for key in get_registered_module_keys() if key != "announcements"
)


class AnnouncementFoundationTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        self.parent = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="NORTH",
            name="北区",
            name_en="North",
        )
        self.child = ChurchStructureUnit.objects.create(
            parent=self.parent,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="NORTH-1",
            name="北区一组",
            name_en="North 1",
        )
        self.sibling = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SOUTH-1",
            name="南区一组",
            name_en="South 1",
        )
        self.exact_member = self.create_member("exact_member", self.parent)
        self.descendant_member = self.create_member(
            "descendant_member",
            self.child,
        )
        self.nonmatching_member = self.create_member(
            "nonmatching_member",
            self.sibling,
        )

    def create_member(self, username, unit, **membership_overrides):
        user = User.objects.create_user(
            username=username,
            password="testpass123",
        )
        membership_data = {
            "user": user,
            "unit": unit,
            "status": ChurchStructureMembership.STATUS_ACTIVE,
            "is_primary": True,
            "start_date": timezone.localdate() - timezone.timedelta(days=1),
        }
        membership_data.update(membership_overrides)
        ChurchStructureMembership.objects.create(**membership_data)
        return user

    def create_announcement(self, **overrides):
        data = {
            "title": "主日聚会安排",
            "title_en": "Sunday Gathering Update",
            "body": "请留意本周聚会安排。",
            "body_en": "Please note this week's gathering schedule.",
            "status": Announcement.STATUS_PUBLISHED,
            "priority": Announcement.PRIORITY_NORMAL,
            "publish_start": self.now - timezone.timedelta(hours=1),
        }
        data.update(overrides)
        return Announcement.objects.create(**data)

    def add_audience(self, announcement, unit):
        return AnnouncementAudienceScope.objects.create(
            announcement=announcement,
            structure_unit=unit,
        )

    def visible_ids(self, user):
        return set(
            visible_announcements_for(user, at=self.now).values_list(
                "id",
                flat=True,
            )
        )

    def test_status_and_priority_choices_are_constrained(self):
        self.assertEqual(
            set(dict(Announcement._meta.get_field("status").choices)),
            {
                Announcement.STATUS_DRAFT,
                Announcement.STATUS_PUBLISHED,
                Announcement.STATUS_ARCHIVED,
            },
        )
        self.assertEqual(
            set(dict(Announcement._meta.get_field("priority").choices)),
            {
                Announcement.PRIORITY_NORMAL,
                Announcement.PRIORITY_IMPORTANT,
            },
        )

        with self.assertRaises(ValidationError):
            self.create_announcement(status="invalid")
        with self.assertRaises(ValidationError):
            self.create_announcement(priority="urgent")

    def test_english_content_falls_back_to_canonical_default_content(self):
        announcement = self.create_announcement(title_en="", body_en="")

        self.assertEqual(announcement.get_title("zh"), announcement.title)
        self.assertEqual(announcement.get_body("zh"), announcement.body)
        self.assertEqual(announcement.get_title("en"), announcement.title)
        self.assertEqual(announcement.get_body("en"), announcement.body)

        announcement.title_en = "English title"
        announcement.body_en = "English body"
        self.assertEqual(announcement.get_title("en"), "English title")
        self.assertEqual(announcement.get_body("en"), "English body")

    def test_publish_end_must_be_later_than_publish_start(self):
        for publish_end in (
            self.now - timezone.timedelta(hours=2),
            self.now - timezone.timedelta(hours=1),
        ):
            with self.subTest(publish_end=publish_end):
                with self.assertRaises(ValidationError):
                    self.create_announcement(
                        publish_start=self.now - timezone.timedelta(hours=1),
                        publish_end=publish_end,
                    )

    def test_active_published_announcement_matches_exact_and_descendant_units(self):
        announcement = self.create_announcement()
        self.add_audience(announcement, self.parent)

        self.assertIn(announcement.id, self.visible_ids(self.exact_member))
        self.assertIn(announcement.id, self.visible_ids(self.descendant_member))

    def test_draft_and_archived_announcements_are_not_visible(self):
        for status in (
            Announcement.STATUS_DRAFT,
            Announcement.STATUS_ARCHIVED,
        ):
            with self.subTest(status=status):
                announcement = self.create_announcement(status=status)
                self.add_audience(announcement, self.parent)
                self.assertNotIn(
                    announcement.id,
                    self.visible_ids(self.exact_member),
                )

    def test_not_yet_started_announcement_is_not_visible(self):
        announcement = self.create_announcement(
            publish_start=self.now + timezone.timedelta(minutes=1),
        )
        self.add_audience(announcement, self.parent)

        self.assertNotIn(announcement.id, self.visible_ids(self.exact_member))

    def test_expired_announcement_is_not_visible(self):
        announcement = self.create_announcement(
            publish_start=self.now - timezone.timedelta(hours=2),
            publish_end=self.now,
        )
        self.add_audience(announcement, self.parent)

        self.assertNotIn(announcement.id, self.visible_ids(self.exact_member))

    def test_zero_audience_rows_fail_closed(self):
        announcement = self.create_announcement()

        self.assertNotIn(announcement.id, self.visible_ids(self.exact_member))

    def test_unauthenticated_user_fails_closed(self):
        announcement = self.create_announcement()
        self.add_audience(announcement, self.root)

        self.assertFalse(
            visible_announcements_for(
                AnonymousUser(),
                at=self.now,
            ).exists()
        )

    def test_missing_inactive_nonprimary_and_nonmatching_membership_fail_closed(self):
        announcement = self.create_announcement()
        self.add_audience(announcement, self.parent)
        missing = User.objects.create_user(
            username="missing_membership",
            password="testpass123",
        )
        inactive = self.create_member(
            "inactive_member",
            self.parent,
            status=ChurchStructureMembership.STATUS_ENDED,
            is_primary=False,
            end_date=timezone.localdate() - timezone.timedelta(days=1),
        )
        nonprimary = self.create_member(
            "nonprimary_member",
            self.parent,
            is_primary=False,
        )

        for user in (
            missing,
            inactive,
            nonprimary,
            self.nonmatching_member,
        ):
            with self.subTest(user=user.username):
                self.assertNotIn(announcement.id, self.visible_ids(user))

    def test_audience_requires_active_unit_and_unique_announcement_unit_pair(self):
        announcement = self.create_announcement()
        self.add_audience(announcement, self.parent)

        with self.assertRaises(ValidationError):
            self.add_audience(announcement, self.parent)

        self.sibling.is_active = False
        self.sibling.save()
        with self.assertRaises(ValidationError):
            self.add_audience(announcement, self.sibling)

    def test_membership_and_audience_grant_no_staff_or_serving_authority(self):
        announcement = self.create_announcement()
        self.add_audience(announcement, self.parent)

        self.assertIn(announcement.id, self.visible_ids(self.descendant_member))
        self.assertFalse(self.descendant_member.is_staff)
        self.assertFalse(self.descendant_member.is_superuser)
        self.assertFalse(
            self.descendant_member.has_perm("announcements.add_announcement")
        )
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(BibleStudyMeetingRole.objects.count(), 0)
        self.assertNotIn(
            "service_event",
            {field.name for field in Announcement._meta.get_fields()},
        )


class AnnouncementMemberSurfaceTests(TestCase):
    password = "MemberPass123!"

    def setUp(self):
        self.now = timezone.now()
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH-SURFACE",
            name="全教会",
            name_en="Whole Church",
        )
        self.member_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SURFACE-1",
            name="公告一组",
            name_en="Announcements Group",
        )
        self.other_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SURFACE-2",
            name="公告二组",
            name_en="Other Group",
        )
        self.member = self.create_member("announcement_member", self.member_unit)
        self.staff = self.create_member(
            "announcement_staff",
            self.member_unit,
            is_staff=True,
        )

    def create_member(self, username, unit, is_staff=False):
        user = User.objects.create_user(
            username=username,
            password=self.password,
            is_staff=is_staff,
        )
        ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate() - timezone.timedelta(days=1),
        )
        return user

    def create_announcement(self, audience_unit=None, **overrides):
        data = {
            "title": "默认公告标题",
            "title_en": "Announcement title",
            "body": "默认公告内容。",
            "body_en": "Announcement body.",
            "status": Announcement.STATUS_PUBLISHED,
            "priority": Announcement.PRIORITY_NORMAL,
            "publish_start": self.now - timezone.timedelta(hours=1),
        }
        data.update(overrides)
        announcement = Announcement.objects.create(**data)
        if audience_unit is not None:
            AnnouncementAudienceScope.objects.create(
                announcement=announcement,
                structure_unit=audience_unit,
            )
        return announcement

    def login(self, user=None, language="en"):
        user = user or self.member
        self.client.force_login(user)
        session = self.client.session
        session["language"] = language
        session.save()

    def test_member_list_orders_visible_active_published_announcements_only(self):
        visible_older = self.create_announcement(
            self.member_unit,
            title_en="Visible older",
            publish_start=self.now - timezone.timedelta(hours=2),
        )
        visible_newer = self.create_announcement(
            self.root,
            title_en="Visible newer",
            publish_start=self.now - timezone.timedelta(minutes=30),
        )
        hidden = {
            "Draft": self.create_announcement(
                self.root,
                title_en="Draft",
                status=Announcement.STATUS_DRAFT,
            ),
            "Archived": self.create_announcement(
                self.root,
                title_en="Archived",
                status=Announcement.STATUS_ARCHIVED,
            ),
            "Future": self.create_announcement(
                self.root,
                title_en="Future",
                publish_start=self.now + timezone.timedelta(minutes=1),
            ),
            "Expired": self.create_announcement(
                self.root,
                title_en="Expired",
                publish_start=self.now - timezone.timedelta(hours=2),
                publish_end=self.now - timezone.timedelta(minutes=1),
            ),
            "Zero audience": self.create_announcement(
                title_en="Zero audience",
            ),
            "Nonmatching": self.create_announcement(
                self.other_unit,
                title_en="Nonmatching",
            ),
        }
        self.login()

        response = self.client.get(reverse("announcement_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["announcements"]),
            [visible_newer, visible_older],
        )
        self.assertEqual(response.context["active_nav"], "announcements")
        content = response.content.decode()
        for title in ("Visible newer", "Visible older"):
            self.assertIn(title, content)
        for title in hidden:
            self.assertNotIn(title, content)

    def test_detail_allows_visible_record_and_404s_every_hidden_state(self):
        visible = self.create_announcement(
            self.root,
            title_en="Visible detail",
        )
        hidden = [
            self.create_announcement(
                self.root,
                status=Announcement.STATUS_DRAFT,
            ),
            self.create_announcement(
                self.root,
                status=Announcement.STATUS_ARCHIVED,
            ),
            self.create_announcement(
                self.root,
                publish_start=self.now + timezone.timedelta(minutes=1),
            ),
            self.create_announcement(
                self.root,
                publish_start=self.now - timezone.timedelta(hours=2),
                publish_end=self.now - timezone.timedelta(minutes=1),
            ),
            self.create_announcement(),
            self.create_announcement(self.other_unit),
        ]
        self.login()

        response = self.client.get(
            reverse("announcement_detail", args=[visible.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible detail")
        self.assertEqual(response.context["active_nav"], "announcements")
        for announcement in hidden:
            with self.subTest(announcement_id=announcement.id):
                response = self.client.get(
                    reverse("announcement_detail", args=[announcement.id])
                )
                self.assertEqual(response.status_code, 404)

    def test_staff_member_routes_do_not_use_management_bypass(self):
        visible = self.create_announcement(
            self.root,
            title_en="Staff-visible published",
        )
        draft = self.create_announcement(
            self.root,
            title_en="Staff-hidden draft",
            status=Announcement.STATUS_DRAFT,
        )
        archived = self.create_announcement(
            self.root,
            title_en="Staff-hidden archived",
            status=Announcement.STATUS_ARCHIVED,
        )
        future = self.create_announcement(
            self.root,
            title_en="Staff-hidden future",
            publish_start=self.now + timezone.timedelta(minutes=1),
        )
        expired = self.create_announcement(
            self.root,
            title_en="Staff-hidden expired",
            publish_start=self.now - timezone.timedelta(hours=2),
            publish_end=self.now - timezone.timedelta(minutes=1),
        )
        self.assertIn(draft, visible_announcements_for(self.staff))
        self.assertNotIn(draft, member_visible_announcements_for(self.staff))
        self.login(self.staff)

        response = self.client.get(reverse("announcement_list"))

        self.assertContains(response, visible.title_en)
        self.assertNotContains(response, draft.title_en)
        self.assertNotContains(response, archived.title_en)
        self.assertNotContains(response, future.title_en)
        self.assertNotContains(response, expired.title_en)
        for announcement in (draft, archived, future, expired):
            response = self.client.get(
                reverse("announcement_detail", args=[announcement.id])
            )
            self.assertEqual(response.status_code, 404)

    def test_list_and_detail_use_bilingual_content_with_english_fallback(self):
        localized = self.create_announcement(
            self.root,
            title="中文标题",
            title_en="English title",
            body="中文内容。",
            body_en="English body.",
        )
        fallback = self.create_announcement(
            self.root,
            title="回退标题",
            title_en="",
            body="回退内容。",
            body_en="",
            publish_start=self.now - timezone.timedelta(minutes=30),
        )
        self.login(language="en")

        response = self.client.get(reverse("announcement_list"))
        self.assertContains(response, "English title")
        self.assertContains(response, "English body.")
        self.assertContains(response, "回退标题")
        self.assertContains(response, "回退内容。")
        response = self.client.get(
            reverse("announcement_detail", args=[localized.id])
        )
        self.assertContains(response, "English title")
        self.assertContains(response, "English body.")

        self.login(language="zh")
        response = self.client.get(reverse("announcement_list"))
        self.assertContains(response, "中文标题")
        self.assertContains(response, "中文内容。")
        response = self.client.get(
            reverse("announcement_detail", args=[fallback.id])
        )
        self.assertContains(response, "回退标题")
        self.assertContains(response, "回退内容。")

    def test_important_badge_does_not_widen_visibility(self):
        visible = self.create_announcement(
            self.root,
            title_en="Visible important",
            priority=Announcement.PRIORITY_IMPORTANT,
        )
        hidden = self.create_announcement(
            title_en="Hidden important",
            priority=Announcement.PRIORITY_IMPORTANT,
        )
        self.login()

        response = self.client.get(reverse("announcement_list"))

        self.assertContains(response, "Visible important")
        self.assertContains(response, "Important")
        self.assertNotContains(response, "Hidden important")
        response = self.client.get(
            reverse("announcement_detail", args=[visible.id])
        )
        self.assertContains(response, "Important")
        response = self.client.get(
            reverse("announcement_detail", args=[hidden.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_member_reads_create_no_cross_module_or_serving_state(self):
        announcement = self.create_announcement(self.root)
        self.login()
        before = {
            "team_assignments": TeamAssignment.objects.count(),
            "team_assignment_members": TeamAssignmentMember.objects.count(),
            "bible_study_roles": BibleStudyMeetingRole.objects.count(),
            "community_activities": CommunityActivity.objects.count(),
            "service_events": ServiceEvent.objects.count(),
        }

        self.client.get(reverse("announcement_list"))
        self.client.get(
            reverse("announcement_detail", args=[announcement.id])
        )

        self.assertEqual(TeamAssignment.objects.count(), before["team_assignments"])
        self.assertEqual(
            TeamAssignmentMember.objects.count(),
            before["team_assignment_members"],
        )
        self.assertEqual(
            BibleStudyMeetingRole.objects.count(),
            before["bible_study_roles"],
        )
        self.assertEqual(
            CommunityActivity.objects.count(),
            before["community_activities"],
        )
        self.assertEqual(ServiceEvent.objects.count(), before["service_events"])


class AnnouncementStaffWorkflowTests(TestCase):
    password = "StaffWorkflowPass123!"

    def setUp(self):
        self.now = timezone.localtime(timezone.now()).replace(
            second=0,
            microsecond=0,
        )
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="ANN-WORKFLOW",
            name="全教会",
            name_en="Whole Church",
        )
        self.parent = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="ANN-NORTH",
            name="北区",
            name_en="North",
        )
        self.child = ChurchStructureUnit.objects.create(
            parent=self.parent,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="ANN-NORTH-1",
            name="北区一组",
            name_en="North 1",
        )
        self.sibling = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="ANN-SOUTH-1",
            name="南区一组",
            name_en="South 1",
        )
        self.inactive = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="ANN-INACTIVE",
            name="停用小组",
            name_en="Inactive Group",
            is_active=False,
        )
        self.member = User.objects.create_user(
            username="announcement_workflow_member",
            password=self.password,
        )
        ChurchStructureMembership.objects.create(
            user=self.member,
            unit=self.child,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate() - timezone.timedelta(days=1),
        )
        self.staff = User.objects.create_user(
            username="announcement_workflow_staff",
            password=self.password,
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            username="announcement_workflow_superuser",
            password=self.password,
            email="superuser@example.com",
        )

    def dt_value(self, value):
        return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")

    def form_data(self, **overrides):
        data = {
            "title": "同工公告",
            "title_en": "Staff announcement",
            "body": "公告正文。",
            "body_en": "Announcement body.",
            "priority": "on",
            "publish_start": self.dt_value(self.now),
            "publish_end": self.dt_value(
                self.now + timezone.timedelta(days=2)
            ),
            "audience_units": [str(self.parent.id)],
        }
        data.update(overrides)
        return data

    def create_announcement(self, audience_units=(), **overrides):
        data = {
            "title": "已有公告",
            "title_en": "Existing announcement",
            "body": "已有正文。",
            "body_en": "Existing body.",
            "status": Announcement.STATUS_DRAFT,
            "priority": Announcement.PRIORITY_NORMAL,
            "publish_start": self.now,
            "created_by": self.staff,
        }
        data.update(overrides)
        announcement = Announcement.objects.create(**data)
        for unit in audience_units:
            AnnouncementAudienceScope.objects.create(
                announcement=announcement,
                structure_unit=unit,
            )
        return announcement

    def login(self, user, language="en"):
        self.client.force_login(user)
        session = self.client.session
        session["language"] = language
        session.save()

    def management_routes(self, announcement):
        return [
            ("get", reverse("staff_announcement_list")),
            ("get", reverse("create_announcement")),
            ("get", reverse("edit_announcement", args=[announcement.id])),
            ("post", reverse("publish_announcement", args=[announcement.id])),
            ("post", reverse("archive_announcement", args=[announcement.id])),
        ]

    def test_anonymous_and_matching_member_cannot_access_staff_workflow(self):
        announcement = self.create_announcement([self.parent])
        for method, url in self.management_routes(announcement):
            with self.subTest(viewer="anonymous", method=method, url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 302)

        self.login(self.member)
        for method, url in self.management_routes(announcement):
            with self.subTest(viewer="member", method=method, url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 302)
        announcement.refresh_from_db()
        self.assertEqual(announcement.status, Announcement.STATUS_DRAFT)

    def test_staff_and_superuser_can_access_management_list_with_all_statuses(self):
        announcements = [
            self.create_announcement(
                [self.parent],
                title_en="Draft management item",
            ),
            self.create_announcement(
                [self.parent],
                title_en="Published management item",
                status=Announcement.STATUS_PUBLISHED,
            ),
            self.create_announcement(
                [self.parent],
                title_en="Archived management item",
                status=Announcement.STATUS_ARCHIVED,
            ),
        ]
        for user in (self.staff, self.superuser):
            with self.subTest(user=user.username):
                self.login(user)
                response = self.client.get(reverse("staff_announcement_list"))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["active_nav"], "staff")
                content = response.content.decode()
                for announcement in announcements:
                    self.assertIn(announcement.title_en, content)

    def test_create_saves_draft_fields_window_and_normalized_audience_rows(self):
        self.login(self.staff)
        data = self.form_data(
            audience_units=[
                str(self.parent.id),
                str(self.sibling.id),
                str(self.parent.id),
            ],
        )

        response = self.client.post(reverse("create_announcement"), data)

        self.assertEqual(response.status_code, 302)
        announcement = Announcement.objects.get(title_en="Staff announcement")
        self.assertEqual(announcement.status, Announcement.STATUS_DRAFT)
        self.assertEqual(announcement.created_by, self.staff)
        self.assertEqual(announcement.priority, Announcement.PRIORITY_IMPORTANT)
        self.assertEqual(announcement.publish_start, self.now)
        self.assertEqual(
            announcement.publish_end,
            self.now + timezone.timedelta(days=2),
        )
        self.assertEqual(
            set(
                announcement.audience_scope_links.values_list(
                    "structure_unit_id",
                    flat=True,
                )
            ),
            {self.parent.id, self.sibling.id},
        )
        self.assertIsNone(announcement.published_by)
        self.assertIsNone(announcement.published_at)

    def test_create_with_important_unchecked_saves_normal_priority(self):
        self.login(self.staff)
        data = self.form_data(title_en="Normal checkbox announcement")
        data.pop("priority")

        response = self.client.post(reverse("create_announcement"), data)

        self.assertEqual(response.status_code, 302)
        announcement = Announcement.objects.get(
            title_en="Normal checkbox announcement"
        )
        self.assertEqual(announcement.priority, Announcement.PRIORITY_NORMAL)

    def test_edit_updates_fields_and_replaces_audience_without_publishing(self):
        announcement = self.create_announcement([self.parent])
        self.login(self.staff)

        response = self.client.post(
            reverse("edit_announcement", args=[announcement.id]),
            self.form_data(
                title="更新公告",
                title_en="Updated announcement",
                body="更新正文。",
                body_en="Updated body.",
                priority="on",
                audience_units=[str(self.sibling.id)],
            ),
        )

        self.assertEqual(response.status_code, 302)
        announcement.refresh_from_db()
        self.assertEqual(announcement.title, "更新公告")
        self.assertEqual(announcement.title_en, "Updated announcement")
        self.assertEqual(announcement.body_en, "Updated body.")
        self.assertEqual(announcement.priority, Announcement.PRIORITY_IMPORTANT)
        self.assertEqual(announcement.status, Announcement.STATUS_DRAFT)
        self.assertEqual(
            list(
                announcement.audience_scope_links.values_list(
                    "structure_unit_id",
                    flat=True,
                )
            ),
            [self.sibling.id],
        )

    def test_edit_from_important_to_normal_with_unchecked_checkbox(self):
        announcement = self.create_announcement(
            [self.parent],
            priority=Announcement.PRIORITY_IMPORTANT,
        )
        self.login(self.staff)
        data = self.form_data(title_en="Now normal")
        data.pop("priority")

        response = self.client.post(
            reverse("edit_announcement", args=[announcement.id]),
            data,
        )

        self.assertEqual(response.status_code, 302)
        announcement.refresh_from_db()
        self.assertEqual(announcement.priority, Announcement.PRIORITY_NORMAL)

    def test_priority_and_audience_help_are_bilingual_and_picker_is_unchanged(self):
        expected_copy = {
            "en": (
                "Important announcements may appear on users’ Today page when "
                "they are published, active, and visible to that user.",
                "Audience controls who can see this announcement. Important "
                "does not bypass audience visibility.",
            ),
            "zh": (
                "重要公告在发布、生效、且用户可见时，可能显示在用户的「今日」页面。",
                "适用范围决定哪些用户可以看到这条公告；重要公告不会绕过适用范围。",
            ),
        }
        for language, (priority_help, audience_help) in expected_copy.items():
            with self.subTest(language=language):
                self.login(self.staff, language=language)
                response = self.client.get(reverse("create_announcement"))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, priority_help)
                self.assertContains(response, audience_help)
                self.assertContains(response, 'type="checkbox"')
                self.assertContains(response, 'name="priority"')
                self.assertNotContains(response, '<select name="priority"')
                self.assertContains(response, "data-audience-picker")
                self.assertContains(response, 'name="audience_units"')

    def test_edit_fields_and_audience_replacement_are_atomic(self):
        announcement = self.create_announcement([self.parent])
        form = AnnouncementForm(
            self.form_data(
                title_en="Must roll back",
                audience_units=[str(self.sibling.id)],
            ),
            instance=announcement,
            language="en",
        )
        self.assertTrue(form.is_valid(), form.errors)

        with patch(
            "announcements.forms.AnnouncementAudienceScope.objects.create",
            side_effect=RuntimeError("simulated audience write failure"),
        ):
            with self.assertRaises(RuntimeError):
                form.save_with_audience()

        announcement.refresh_from_db()
        self.assertEqual(announcement.title_en, "Existing announcement")
        self.assertEqual(
            list(
                announcement.audience_scope_links.values_list(
                    "structure_unit_id",
                    flat=True,
                )
            ),
            [self.parent.id],
        )

    def test_form_rejects_invalid_window_inactive_unknown_and_overlapping_units(self):
        invalid_cases = {
            "window": self.form_data(
                publish_end=self.dt_value(
                    self.now - timezone.timedelta(minutes=1)
                )
            ),
            "inactive": self.form_data(
                audience_units=[str(self.inactive.id)]
            ),
            "unknown": self.form_data(audience_units=["999999"]),
            "overlap": self.form_data(
                audience_units=[str(self.parent.id), str(self.child.id)]
            ),
        }
        for case, data in invalid_cases.items():
            with self.subTest(case=case):
                form = AnnouncementForm(data, language="en")
                self.assertFalse(form.is_valid())
                expected_field = (
                    "publish_end" if case == "window" else "audience_units"
                )
                self.assertIn(expected_field, form.errors)

    def test_publish_is_post_only_and_requires_active_audience(self):
        announcement = self.create_announcement()
        self.login(self.staff)
        publish_url = reverse("publish_announcement", args=[announcement.id])

        self.assertEqual(self.client.get(publish_url).status_code, 405)
        response = self.client.post(publish_url, follow=True)

        self.assertEqual(response.status_code, 200)
        announcement.refresh_from_db()
        self.assertEqual(announcement.status, Announcement.STATUS_DRAFT)
        self.assertIsNone(announcement.published_by)
        self.assertContains(
            response,
            "Choose at least one active audience unit before publishing.",
        )

    def test_publish_records_actor_and_time_and_allows_scheduled_start(self):
        future_start = self.now + timezone.timedelta(days=1)
        announcement = self.create_announcement(
            [self.parent],
            publish_start=future_start,
        )
        self.login(self.staff)

        response = self.client.post(
            reverse("publish_announcement", args=[announcement.id])
        )

        self.assertEqual(response.status_code, 302)
        announcement.refresh_from_db()
        self.assertEqual(announcement.status, Announcement.STATUS_PUBLISHED)
        self.assertEqual(announcement.published_by, self.staff)
        self.assertIsNotNone(announcement.published_at)
        self.login(self.member)
        self.assertNotContains(
            self.client.get(reverse("announcement_list")),
            announcement.title_en,
        )
        self.assertEqual(
            self.client.get(
                reverse("announcement_detail", args=[announcement.id])
            ).status_code,
            404,
        )

    def test_publish_rejects_invalid_window_and_archived_transition(self):
        invalid = self.create_announcement([self.parent])
        Announcement.objects.filter(id=invalid.id).update(
            publish_end=self.now - timezone.timedelta(minutes=1)
        )
        archived = self.create_announcement(
            [self.parent],
            status=Announcement.STATUS_ARCHIVED,
        )
        self.login(self.staff)

        invalid_response = self.client.post(
            reverse("publish_announcement", args=[invalid.id]),
            follow=True,
        )
        archived_response = self.client.post(
            reverse("publish_announcement", args=[archived.id]),
            follow=True,
        )

        invalid.refresh_from_db()
        archived.refresh_from_db()
        self.assertEqual(invalid.status, Announcement.STATUS_DRAFT)
        self.assertEqual(archived.status, Announcement.STATUS_ARCHIVED)
        self.assertContains(
            invalid_response,
            "Fix the announcement fields and publish window before publishing.",
        )
        self.assertContains(
            archived_response,
            "Archived announcements cannot be published.",
        )

    def test_archive_is_post_only_hides_member_detail_and_preserves_audience(self):
        announcement = self.create_announcement(
            [self.parent],
            status=Announcement.STATUS_PUBLISHED,
            publish_start=self.now - timezone.timedelta(hours=1),
        )
        archive_url = reverse("archive_announcement", args=[announcement.id])
        self.login(self.staff)

        self.assertEqual(self.client.get(archive_url).status_code, 405)
        self.assertEqual(self.client.post(archive_url).status_code, 302)

        announcement.refresh_from_db()
        self.assertEqual(announcement.status, Announcement.STATUS_ARCHIVED)
        self.assertEqual(announcement.audience_scope_links.count(), 1)
        self.login(self.member)
        self.assertNotContains(
            self.client.get(reverse("announcement_list")),
            announcement.title_en,
        )
        self.assertEqual(
            self.client.get(
                reverse("announcement_detail", args=[announcement.id])
            ).status_code,
            404,
        )

    def test_staff_lifecycle_creates_no_cross_module_or_today_state(self):
        self.login(self.staff)
        before = {
            "team_assignments": TeamAssignment.objects.count(),
            "team_assignment_members": TeamAssignmentMember.objects.count(),
            "bible_study_meetings": BibleStudyMeeting.objects.count(),
            "bible_study_roles": BibleStudyMeetingRole.objects.count(),
            "community_activities": CommunityActivity.objects.count(),
            "activity_signups": ActivitySignup.objects.count(),
            "service_events": ServiceEvent.objects.count(),
        }
        response = self.client.post(
            reverse("create_announcement"),
            self.form_data(),
        )
        announcement = Announcement.objects.get(title_en="Staff announcement")
        self.client.post(
            reverse("publish_announcement", args=[announcement.id])
        )
        self.client.post(
            reverse("archive_announcement", args=[announcement.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(TeamAssignment.objects.count(), before["team_assignments"])
        self.assertEqual(
            TeamAssignmentMember.objects.count(),
            before["team_assignment_members"],
        )
        self.assertEqual(
            BibleStudyMeeting.objects.count(),
            before["bible_study_meetings"],
        )
        self.assertEqual(
            BibleStudyMeetingRole.objects.count(),
            before["bible_study_roles"],
        )
        self.assertEqual(
            CommunityActivity.objects.count(),
            before["community_activities"],
        )
        self.assertEqual(
            ActivitySignup.objects.count(),
            before["activity_signups"],
        )
        self.assertEqual(ServiceEvent.objects.count(), before["service_events"])
        self.assertNotIn(
            "announcements",
            get_registered_today_provider_keys(),
        )

    def staff_nav_href(self):
        return 'href="%s"' % reverse("staff_announcement_list")

    def test_staff_dropdown_link_is_module_gated_and_staff_only(self):
        self.login(self.staff)
        enabled_response = self.client.get(reverse("profile"))
        self.assertContains(enabled_response, self.staff_nav_href())
        self.assertContains(enabled_response, "Announcement Admin")

        with override_settings(
            CMS_ENABLED_MODULES=MODULES_WITHOUT_ANNOUNCEMENTS
        ):
            disabled_response = self.client.get(reverse("profile"))
        self.assertNotContains(disabled_response, self.staff_nav_href())

        self.login(self.member)
        member_response = self.client.get(reverse("profile"))
        self.assertNotContains(member_response, self.staff_nav_href())
