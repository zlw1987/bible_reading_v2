from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from ministry.models import TeamAssignment, TeamAssignmentMember
from studies.models import BibleStudyMeetingRole

from .models import Announcement, AnnouncementAudienceScope
from .visibility import visible_announcements_for

User = get_user_model()


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
