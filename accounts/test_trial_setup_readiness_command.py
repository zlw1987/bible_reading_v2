"""Tests for the read-only pre-user-trial setup readiness audit.

SETUP-READINESS.1A. The ``audit_trial_setup_readiness`` command must be strictly
read-only: it has no ``--apply``, mutates nothing, and only reports blockers /
warnings / info. It must classify display-name-only serving slots as warnings
(never blockers) and only fail ``--fail-on-blockers`` when blockers > 0.
"""

from io import StringIO

from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from accounts.trial_setup_readiness import run_audit
from events.models import ServiceEvent, ServiceEventAudienceScope
from ministry.models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from studies.models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudyMeetingRole,
    BibleStudySeries,
)


class TrialSetupReadinessCommandTests(TestCase):
    COMMAND = "audit_trial_setup_readiness"

    def setUp(self):
        self.now = timezone.now()
        self.future = self.now + timezone.timedelta(days=3)
        self.root_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.root_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RAINBOW4",
            name="Rainbow 4",
            name_en="Rainbow 4",
        )

    # ----- helpers ----------------------------------------------------------

    def run_command(self, *args):
        out = StringIO()
        call_command(self.COMMAND, *args, stdout=out)
        return out.getvalue()

    def make_staff(self, username="trial_staff"):
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pw",
            is_staff=True,
        )

    def make_published_event(self, **overrides):
        data = {
            "title": "主日崇拜",
            "title_en": "Sunday Service",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": self.future,
            "status": ServiceEvent.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return ServiceEvent.objects.create(**data)

    def make_visible_meeting(self):
        series = BibleStudySeries.objects.create(
            title="约翰福音查经",
            title_en="John Bible Study",
            status=BibleStudySeries.STATUS_PUBLISHED,
        )
        lesson = BibleStudyLesson.objects.create(
            series=series,
            title="约翰十五章",
            title_en="John 15",
            lesson_date=timezone.localdate() + timezone.timedelta(days=3),
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        return BibleStudyMeeting.objects.create(
            lesson=lesson,
            meeting_datetime=self.future,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )

    def section(self, audit, key):
        for section in audit["sections"]:
            if section.key == key:
                return section
        raise AssertionError(f"section {key!r} not found")

    # ----- existence / read-only -------------------------------------------

    def test_minimal_database_runs_without_crashing(self):
        output = self.run_command()
        self.assertIn(
            "Pre-user-trial setup readiness audit (SETUP-READINESS.1A, read-only)",
            output,
        )
        self.assertIn("blockers: 0", output)
        self.assertIn("recommendation:", output)
        # With no users at all, the only expected setup warning is "no admin".
        self.assertIn(
            "no active staff or superuser account exists", output
        )

    def test_output_states_read_only_and_no_apply(self):
        output = self.run_command()
        self.assertIn("mode: read-only (no --apply exists; no data was changed)", output)
        self.assertIn("No --apply mode exists.", output)
        self.assertIn("NOT a production-deployment claim", output)

    def test_no_apply_option_exists(self):
        from accounts.management.commands.audit_trial_setup_readiness import Command

        parser = Command().create_parser("manage.py", self.COMMAND)
        dests = {action.dest for action in parser._actions}
        self.assertNotIn("apply", dests)
        self.assertIn("fail_on_blockers", dests)
        self.assertIn("verbose", dests)
        self.assertIn("limit", dests)

    def test_command_is_read_only_snapshot_counts(self):
        self.make_staff()
        event = self.make_published_event()
        ServiceEventAudienceScope.objects.create(
            service_event=event, unit=self.group_unit
        )
        models = [
            User,
            ChurchStructureUnit,
            ChurchStructureMembership,
            ServiceEvent,
            ServiceEventAudienceScope,
            MinistryTeam,
            TeamAssignment,
            TeamAssignmentMember,
            BibleStudyMeeting,
            BibleStudyMeetingRole,
        ]
        before = {m.__name__: m.objects.count() for m in models}
        self.run_command("--verbose")
        after = {m.__name__: m.objects.count() for m in models}
        self.assertEqual(before, after)

    # ----- blockers ---------------------------------------------------------

    def test_zero_audience_published_event_is_blocker(self):
        self.make_staff()
        self.make_published_event()  # no audience rows -> fail closed

        audit = run_audit()
        section = self.section(audit, "audience_visibility")
        self.assertEqual(
            section.blockers["upcoming_published_events_zero_audience"], 1
        )
        self.assertGreater(audit["blocker_count"], 0)

        with self.assertRaises(CommandError):
            self.run_command("--fail-on-blockers")

    def test_zero_audience_visible_meeting_is_blocker(self):
        self.make_staff()
        self.make_visible_meeting()  # member-visible, no audience rows

        audit = run_audit()
        section = self.section(audit, "audience_visibility")
        self.assertEqual(
            section.blockers["upcoming_visible_meetings_zero_audience"], 1
        )
        with self.assertRaises(CommandError):
            self.run_command("--fail-on-blockers")

    # ----- warnings do not fail --------------------------------------------

    def test_warning_only_exits_zero_with_fail_on_blockers(self):
        # A staff user (so no "no admin" warning) plus a regular active user with
        # no active primary membership -> exactly one warning, zero blockers.
        self.make_staff()
        User.objects.create_user(
            username="regular", email="regular@example.com", password="pw"
        )
        audit = run_audit()
        self.assertEqual(audit["blocker_count"], 0)
        self.assertGreater(audit["warning_count"], 0)
        # Must not raise.
        self.run_command("--fail-on-blockers")

    def test_display_name_only_team_member_is_warning_not_blocker(self):
        self.make_staff()
        event = self.make_published_event()
        ServiceEventAudienceScope.objects.create(
            service_event=event, unit=self.group_unit
        )
        team = MinistryTeam.objects.create(
            name="灯光", name_en="Lighting", is_assignable=True
        )
        membership = TeamMembership.objects.create(
            team=team, display_name="访客王", role=TeamMembership.ROLE_MEMBER
        )
        assignment = TeamAssignment.objects.create(
            service_event=event, ministry_team=team
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment, membership=membership
        )

        audit = run_audit()
        section = self.section(audit, "team_serving")
        self.assertEqual(
            section.warnings["team_assignment_members_display_name_only"], 1
        )
        # It must not be a blocker anywhere.
        self.assertEqual(section.blocker_count, 0)
        # No audience blocker either (event has an audience row).
        self.assertEqual(
            self.section(audit, "audience_visibility").blocker_count, 0
        )

    def test_display_name_only_meeting_role_is_warning_not_blocker(self):
        self.make_staff()
        meeting = self.make_visible_meeting()
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting, unit=self.group_unit
        )
        BibleStudyMeetingRole.objects.create(
            meeting=meeting,
            role=BibleStudyMeetingRole.ROLE_WORSHIP_LEAD,
            display_name="同工李",
        )

        audit = run_audit()
        section = self.section(audit, "bible_study_serving")
        self.assertEqual(
            section.warnings["bible_study_meeting_roles_display_name_only"], 1
        )
        self.assertEqual(section.blocker_count, 0)
        # Meeting has an audience row, so no audience blocker.
        self.assertEqual(
            self.section(audit, "audience_visibility").blocker_count, 0
        )

    # ----- MODULAR-CORE.5A module-owned readiness providers ----------------

    ALL_SECTION_KEYS = [
        "church_structure",
        "ministry_structure",
        "team_serving",
        "bible_study_serving",
        "audience_visibility",
        "permission_admin",
    ]
    CORE_SECTION_KEYS = [
        "church_structure",
        "audience_visibility",
        "permission_admin",
    ]

    def section_keys(self, audit):
        return [section.key for section in audit["sections"]]

    def test_default_all_modules_enabled_has_all_six_sections_in_order(self):
        # Default settings enable every module: the aggregated report is
        # identical to the pre-provider six-section layout and order.
        self.assertEqual(self.section_keys(run_audit()), self.ALL_SECTION_KEYS)

    @override_settings(
        CMS_ENABLED_MODULES=["reading", "prayers", "studies", "events"]
    )
    def test_disabling_ministry_skips_ministry_owned_sections(self):
        # ministry disabled (events still enabled -> dependency-valid): the
        # ministry-owned sections drop; Core and studies sections stay.
        keys = self.section_keys(run_audit())
        self.assertNotIn("ministry_structure", keys)
        self.assertNotIn("team_serving", keys)
        for key in self.CORE_SECTION_KEYS:
            self.assertIn(key, keys)
        self.assertIn("bible_study_serving", keys)

    @override_settings(
        CMS_ENABLED_MODULES=["reading", "prayers", "events", "ministry"]
    )
    def test_disabling_studies_skips_studies_owned_serving_section(self):
        keys = self.section_keys(run_audit())
        self.assertNotIn("bible_study_serving", keys)
        # Core sections (including audience visibility) still run.
        for key in self.CORE_SECTION_KEYS:
            self.assertIn(key, keys)

    @override_settings(
        CMS_ENABLED_MODULES=["reading", "prayers", "events", "ministry"]
    )
    def test_studies_disabled_still_flags_zero_audience_meeting_blocker(self):
        # The zero-audience meeting blocker lives in the always-run Core
        # audience-visibility section, so fail-closed checks survive disabling
        # the studies module.
        self.make_staff()
        self.make_visible_meeting()  # member-visible, no audience rows

        audit = run_audit()
        section = self.section(audit, "audience_visibility")
        self.assertEqual(
            section.blockers["upcoming_visible_meetings_zero_audience"], 1
        )
        self.assertGreater(audit["blocker_count"], 0)

    @override_settings(CMS_ENABLED_MODULES=[])
    def test_all_modules_disabled_keeps_only_core_sections(self):
        keys = self.section_keys(run_audit())
        self.assertEqual(keys, self.CORE_SECTION_KEYS)

    @override_settings(CMS_ENABLED_MODULES=["ministry"])
    def test_invalid_dependency_configuration_raises(self):
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            run_audit()
