import re

from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import ChurchRoleAssignment, District, MinistryContext, SmallGroup
from accounts.permissions import (
    CAP_PUBLISH_READING_GUIDES,
    CAP_VIEW_ALL_GROUP_PROGRESS,
    CAP_VIEW_DISTRICT_PROGRESS,
    CAP_VIEW_GROUP_PROGRESS,
    get_accessible_progress_groups,
    has_capability,
)

class AccountProfileTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")
        self.other_group = SmallGroup.objects.create(name="Rainbow 5")

        self.user = User.objects.create_user(
            username="levin",
            email="",
            password="OldPass123!",
        )

        self.user.profile.small_group = self.group
        self.user.profile.preferred_language = "zh"
        self.user.profile.save()

        self.staff = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="StaffPass123!",
            is_staff=True,
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def assert_active_nav_href(self, response, url_name):
        content = response.content.decode()
        expected_href = reverse(url_name)

        self.assertEqual(content.count('class="nav-link active"'), 1)
        self.assertRegex(
            content,
            r'class="nav-link active"\s+href="%s"' % re.escape(expected_href),
        )

    def test_profile_requires_login(self):
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_profile_page_shows_user_info(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "levin")
        self.assertContains(response, "Rainbow 4")

    def test_user_can_update_profile_without_email(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "",
                "small_group": self.other_group.id,
                "preferred_language": "en",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("profile"))

        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()

        self.assertEqual(self.user.email, "")
        self.assertEqual(self.user.profile.small_group, self.other_group)
        self.assertEqual(self.user.profile.preferred_language, "en")
        self.assertEqual(self.client.session["language"], "en")

    def test_user_can_update_email(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "levin@example.com",
                "small_group": self.group.id,
                "preferred_language": "zh",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "levin@example.com")

    def test_password_change_page_requires_login(self):
        response = self.client.get(reverse("password_change"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_user_can_change_password(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "OldPass123!",
                "new_password1": "NewStrongPass123!",
                "new_password2": "NewStrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("password_change_done"))

        self.client.logout()

        login_success = self.client.login(
            username="levin",
            password="NewStrongPass123!",
        )

        self.assertTrue(login_success)

    def test_normal_english_user_sees_simple_primary_nav(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Today")
        self.assertContains(response, "Reading")
        self.assertContains(response, "Bible Study")
        self.assertContains(response, "Prayer")
        self.assertContains(response, "My Serving")
        self.assertContains(response, "Profile")
        self.assertNotContains(response, "Reading Plan Admin")
        self.assertNotContains(response, "Bible Study Admin")
        self.assertNotContains(response, "Bible Study Schedules")
        self.assertNotContains(response, "Legacy Bible Study Sessions")
        self.assertNotContains(response, "Weekly Bible Study Guides")
        self.assertNotContains(response, "Small Group Meetings")
        self.assertNotContains(response, "User Admin")
        self.assertNotContains(response, "Reflection Reports")
        self.assertNotContains(response, "Prayer Reports")
        self.assertNotContains(response, "Ministry Teams")
        self.assertNotContains(response, "Team Assignments")
        self.assertNotContains(response, "Django Admin")
        self.assertNotContains(response, "Staff")

    def test_normal_english_user_nav_excludes_global_clutter(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Calendar")
        self.assertNotContains(response, "Reflection Wall")
        self.assertNotContains(response, "Prayer Wall")
        self.assertNotContains(response, "Group Progress")

    def test_staff_english_user_sees_staff_menu_links(self):
        self.set_language("en")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("profile"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff")
        self.assertIn('<details class="nav-staff-menu">', content)
        self.assertIn('<div class="nav-staff-menu-panel">', content)
        self.assertIn('(hover: hover) and (pointer: fine)', content)
        self.assertIn('menu.addEventListener("mouseenter"', content)
        self.assertIn("menu.contains(event.relatedTarget)", content)
        self.assertIn("nav-menu-open", content)
        self.assertIn("lockBodyScroll", content)
        self.assertIn("unlockBodyScroll", content)
        self.assertIn("site-header--hidden", content)
        self.assertIn("mobileHeader", content)
        self.assertIn("updateHeaderVisibility", content)
        self.assertIn("keepHeaderVisible", content)
        self.assertIn('window.addEventListener("scroll"', content)
        self.assertIn("--staff-menu-top", content)
        self.assertIn("--staff-menu-left", content)
        self.assertIn("--staff-menu-width", content)
        self.assertIn("summaryRect.bottom + 8", content)
        self.assertIn("viewportWidth * 0.82", content)
        self.assertIn("closeMenuFromOutside", content)
        self.assertIn('document.addEventListener("click"', content)
        self.assertIn("lockedMenu.contains(event.target)", content)
        self.assertContains(response, "Content Management")
        self.assertContains(response, "Reading Plan Admin")
        self.assertContains(response, "Bible Study Schedules")
        self.assertContains(response, "Weekly Bible Study Guides")
        self.assertContains(response, "Small Group Meetings")
        self.assertNotContains(response, "Bible Study Admin")
        self.assertNotContains(response, "Legacy Bible Study Sessions")
        self.assertLess(
            content.index("Bible Study Schedules"),
            content.index("Weekly Bible Study Guides"),
        )
        self.assertLess(
            content.index("Weekly Bible Study Guides"),
            content.index("Small Group Meetings"),
        )
        self.assertContains(response, "Ministry Operations")
        self.assertContains(response, "Service Events")
        self.assertContains(response, "Ministry Teams")
        self.assertContains(response, "Team Assignments")
        self.assertContains(response, "Lighting Pilot Import")
        self.assertContains(response, "Users and Review")
        self.assertContains(response, "User Admin")
        self.assertContains(response, "Reflection Reports")
        self.assertContains(response, "Prayer Reports")
        self.assertContains(response, "Django Admin")

    def test_normal_chinese_user_sees_simple_primary_nav(self):
        self.set_language("zh")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "今日")
        self.assertContains(response, "读经")
        self.assertContains(response, "查经")
        self.assertContains(response, "代祷")
        self.assertContains(response, "我的服事")
        self.assertContains(response, "个人资料")

    def test_staff_chinese_user_sees_staff_menu_links(self):
        self.set_language("zh")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "同工管理")
        self.assertContains(response, "内容管理")
        self.assertContains(response, "读经计划管理")
        self.assertContains(response, "查经安排")
        self.assertContains(response, "每周查经指引")
        self.assertContains(response, "小组查经聚会")
        self.assertNotContains(response, "旧版查经安排")
        self.assertNotContains(response, "查经管理")
        content = response.content.decode()
        self.assertLess(content.index("查经安排"), content.index("每周查经指引"))
        self.assertLess(content.index("每周查经指引"), content.index("小组查经聚会"))
        self.assertContains(response, "事工运作")
        self.assertContains(response, "聚会事件")
        self.assertContains(response, "事工团队")
        self.assertContains(response, "服事排班")
        self.assertContains(response, "灯光试点导入")
        self.assertContains(response, "用户与审核")
        self.assertContains(response, "用户管理")
        self.assertContains(response, "默想举报")
        self.assertContains(response, "代祷举报")

    def test_core_logged_in_pages_still_render(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        for url_name in [
            "home",
            "my_plans",
            "study_session_list",
            "prayer_list",
            "my_serving",
            "profile",
        ]:
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 200)

    def test_today_page_marks_today_nav_active(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assert_active_nav_href(response, "home")

    def test_reading_page_marks_reading_nav_active(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 200)
        self.assert_active_nav_href(response, "my_plans")

    def test_bible_study_page_marks_bible_study_nav_active(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assert_active_nav_href(response, "study_session_list")

    def test_prayer_page_marks_prayer_nav_active(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("prayer_list"))

        self.assertEqual(response.status_code, 200)
        self.assert_active_nav_href(response, "prayer_list")

    def test_my_serving_page_marks_my_serving_nav_active(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assert_active_nav_href(response, "my_serving")

    def test_profile_page_marks_profile_nav_active(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assert_active_nav_href(response, "profile")

    def test_staff_management_page_marks_staff_nav_active(self):
        self.set_language("en")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_user_list"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.count('class="nav-link active"'), 1)
        self.assertIn('<summary class="nav-link active">', content)


    def test_normal_chinese_user_sees_my_serving_in_top_nav(self):
        self.set_language("zh")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "我的服事")


class MinistryContextBridgeTests(TestCase):
    def test_ministry_context_can_be_created(self):
        context = MinistryContext.objects.create(
            code="CM",
            name="Chinese Ministry",
            name_en="Chinese Ministry",
            description="Chinese ministry context",
            description_en="Chinese ministry context",
            sort_order=10,
        )

        self.assertEqual(context.code, "CM")
        self.assertEqual(str(context), "CM - Chinese Ministry")
        self.assertTrue(context.is_active)

    def test_ministry_context_code_is_normalized_to_uppercase(self):
        context = MinistryContext.objects.create(
            code="em",
            name="English Ministry",
        )

        self.assertEqual(context.code, "EM")

    def test_district_can_be_linked_to_ministry_context(self):
        context = MinistryContext.objects.create(code="CM", name="Chinese Ministry")
        district = District.objects.create(
            name="District 1",
            ministry_context=context,
        )

        self.assertEqual(district.ministry_context, context)
        self.assertIn(district, context.districts.all())

    def test_existing_district_without_ministry_context_remains_valid(self):
        district = District.objects.create(name="District without context")

        district.full_clean()
        self.assertIsNone(district.ministry_context)

    def test_small_group_still_belongs_to_district(self):
        district = District.objects.create(name="District 1")
        group = SmallGroup.objects.create(name="Rainbow 4", district=district)

        self.assertEqual(group.district, district)
        self.assertIn(group, district.small_groups.all())

    def test_profile_small_group_behavior_is_unchanged(self):
        district = District.objects.create(name="District 1")
        group = SmallGroup.objects.create(name="Rainbow 4", district=district)
        user = User.objects.create_user(
            username="member_context",
            password="TestPass123!",
        )

        user.profile.small_group = group
        user.profile.save()

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group, group)
        self.assertIn(user.profile, group.members.all())

    def test_church_structure_unit_model_is_not_introduced(self):
        model_names = {model.__name__ for model in apps.get_models()}

        self.assertNotIn("ChurchStructureUnit", model_names)


class ChurchRolePermissionTests(TestCase):
    def setUp(self):
        self.district = District.objects.create(name="North")
        self.other_district = District.objects.create(name="South")
        self.group = SmallGroup.objects.create(name="Rainbow 4", district=self.district)
        self.other_group = SmallGroup.objects.create(
            name="Rainbow 5",
            district=self.other_district,
        )
        self.user = User.objects.create_user(
            username="member",
            password="TestPass123!",
        )
        self.staff = User.objects.create_user(
            username="staff_roles",
            password="TestPass123!",
            is_staff=True,
        )

    def test_district_can_be_created_and_assigned_to_small_group(self):
        self.assertEqual(str(self.district), "North")
        self.assertEqual(self.group.district, self.district)
        self.assertIn(self.group, self.district.small_groups.all())

    def test_global_scope_rejects_district_or_small_group(self):
        assignment = ChurchRoleAssignment(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
            district=self.district,
            small_group=self.group,
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_district_scope_requires_district(self):
        assignment = ChurchRoleAssignment(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_small_group_scope_requires_small_group(self):
        assignment = ChurchRoleAssignment(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_staff_has_all_capabilities(self):
        self.assertTrue(has_capability(self.staff, CAP_PUBLISH_READING_GUIDES))
        self.assertTrue(has_capability(self.staff, CAP_VIEW_ALL_GROUP_PROGRESS))
        self.assertTrue(has_capability(self.staff, CAP_VIEW_DISTRICT_PROGRESS))
        self.assertTrue(has_capability(self.staff, CAP_VIEW_GROUP_PROGRESS))

    def test_regular_user_without_role_has_no_capabilities(self):
        self.assertFalse(has_capability(self.user, CAP_PUBLISH_READING_GUIDES))
        self.assertFalse(has_capability(self.user, CAP_VIEW_ALL_GROUP_PROGRESS))

    def test_pastor_assignment_grants_expected_capabilities(self):
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        self.assertTrue(has_capability(self.user, CAP_PUBLISH_READING_GUIDES))
        self.assertTrue(has_capability(self.user, CAP_VIEW_ALL_GROUP_PROGRESS))

    def test_district_leader_gets_only_assigned_district_groups(self):
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            district=self.district,
        )

        groups = list(get_accessible_progress_groups(self.user))

        self.assertIn(self.group, groups)
        self.assertNotIn(self.other_group, groups)

    def test_group_leader_gets_only_assigned_small_group(self):
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )

        groups = list(get_accessible_progress_groups(self.user))

        self.assertEqual(groups, [self.group])

    def test_regular_user_gets_own_profile_small_group(self):
        self.user.profile.small_group = self.group
        self.user.profile.save()

        groups = list(get_accessible_progress_groups(self.user))

        self.assertEqual(groups, [self.group])


class StaffPasswordResetTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")

        self.staff = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="StaffPass123!",
            is_staff=True,
        )

        self.user = User.objects.create_user(
            username="elder",
            email="",
            password="OldPass123!",
        )

        self.user.profile.small_group = self.group
        self.user.profile.save()

    def test_staff_user_list_requires_staff(self):
        self.client.login(username="elder", password="OldPass123!")

        response = self.client.get(reverse("staff_user_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_can_access_user_list(self):
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Admin")
        self.assertContains(response, "elder")

    def test_chinese_staff_user_list_uses_chinese_labels(self):
        session = self.client.session
        session["language"] = "zh"
        session.save()
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "用户管理")
        self.assertContains(response, "搜索用户，并为无法使用邮件找回密码的成员重置密码")
        self.assertContains(response, "搜索")
        self.assertContains(response, "用户名")
        self.assertContains(response, "邮箱")
        self.assertContains(response, "小组")
        self.assertContains(response, "语言")
        self.assertContains(response, "密码状态")
        self.assertContains(response, "操作")
        self.assertContains(response, "重置密码")
        self.assertContains(response, "正常")
        self.assertNotContains(response, "User Admin")
        self.assertNotContains(response, "Reset Password")

    def test_staff_can_search_user_list(self):
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_user_list"), {"q": "Rainbow"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "elder")

    def test_staff_can_reset_user_password(self):
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.post(
            reverse("staff_user_password_reset", args=[self.user.id]),
            {
                "new_password1": "TempPass123!",
                "new_password2": "TempPass123!",
                "require_password_change": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("staff_user_list"))

        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()

        self.assertTrue(self.user.check_password("TempPass123!"))
        self.assertTrue(self.user.profile.must_change_password)

    def test_user_with_must_change_password_is_redirected(self):
        self.user.profile.must_change_password = True
        self.user.profile.save()

        self.client.login(username="elder", password="OldPass123!")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("password_change"))

    def test_password_change_clears_must_change_password_flag(self):
        self.user.set_password("TempPass123!")
        self.user.save()

        self.user.profile.must_change_password = True
        self.user.profile.save()

        self.client.login(username="elder", password="TempPass123!")

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "TempPass123!",
                "new_password1": "NewStrongPass123!",
                "new_password2": "NewStrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("password_change_done"))

        self.user.profile.refresh_from_db()

        self.assertFalse(self.user.profile.must_change_password)

        self.client.logout()

        login_success = self.client.login(
            username="elder",
            password="NewStrongPass123!",
        )

        self.assertTrue(login_success)

class AccountSignupLanguageTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")

    def test_signup_does_not_require_email(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "elder_user",
                "email": "",
                "small_group": self.group.id,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)

        user = User.objects.get(username="elder_user")
        self.assertEqual(user.email, "")
        self.assertEqual(user.profile.small_group, self.group)

    def test_language_switch_updates_session(self):
        response = self.client.post(
            reverse("change_language"),
            {
                "language": "en",
                "next": reverse("login"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))
        self.assertEqual(self.client.session["language"], "en")

    def test_signup_page_can_render_chinese_labels(self):
        self.client.post(
            reverse("change_language"),
            {
                "language": "zh",
                "next": reverse("signup"),
            },
        )

        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email（可选）")
        self.assertContains(response, "小组")

    def test_signup_page_can_render_english_labels(self):
        self.client.post(
            reverse("change_language"),
            {
                "language": "en",
                "next": reverse("signup"),
            },
        )

        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email (optional)")
        self.assertContains(response, "Small group")
