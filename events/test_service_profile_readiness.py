import json
from datetime import datetime, time
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from events.models import ServiceEvent, ServiceEventAudienceScope, ServiceProfile
from events.service_profile_readiness import (
    SERVICE_PROFILE_READINESS_CONTRACT_VERSION,
    build_audit,
    build_expected_sundays,
    get_schema_readiness,
)
from accounts.models import ChurchStructureUnit


class ServiceProfileReadinessTests(TestCase):
    def setUp(self):
        self.profile = ServiceProfile.objects.create(
            key="bethany_0930_cm", name="Sunday", event_type=ServiceEvent.EVENT_SUNDAY_SERVICE
        )
        self.unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT, code="CHURCH", name="Church"
        )

    def local_datetime(self, day, at=time(9, 30)):
        return timezone.make_aware(
            datetime.combine(day, at), timezone.get_current_timezone()
        )

    def make_event(self, *, profile=None, day=None, at=time(9, 30), **overrides):
        values = {
            "title": "Sunday Service",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": self.local_datetime(day or build_expected_sundays(2026)[0], at),
            "status": ServiceEvent.STATUS_PUBLISHED,
            "service_profile": profile,
        }
        values.update(overrides)
        return ServiceEvent.objects.create(**values)

    def add_audience(self, event, unit=None):
        return ServiceEventAudienceScope.objects.create(
            service_event=event, unit=unit or self.unit
        )

    def audit(self, *, event_type=ServiceEvent.EVENT_SUNDAY_SERVICE):
        return build_audit(
            profile_key=self.profile.key,
            year=2026,
            target_time=time(9, 30),
            event_type=event_type,
        )

    @staticmethod
    def day(audit, value="2026-01-04"):
        return next(row for row in audit["sundays"] if row["date"] == value)

    def test_readiness_is_versioned_and_selects_only_by_fk(self):
        start = timezone.make_aware(datetime(2026, 1, 4, 9, 30))
        event = ServiceEvent.objects.create(
            title="Sunday", event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=start, status=ServiceEvent.STATUS_PUBLISHED,
            service_profile=self.profile,
        )
        ServiceEventAudienceScope.objects.create(service_event=event, unit=self.unit)
        ServiceEvent.objects.filter(pk=event.pk).update(service_profile_key="wrong.key")
        audit = build_audit(
            profile_key=self.profile.key, year=2026, target_time=time(9, 30),
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        self.assertEqual(audit["contract_version"], SERVICE_PROFILE_READINESS_CONTRACT_VERSION)
        self.assertEqual(audit["canonical_tagged_rows"][0]["service_profile_id"], self.profile.pk)
        self.assertNotIn("legacy_only_rows", audit)
        self.assertNotIn("compatibility_key", audit["canonical_tagged_rows"][0])

    def test_missing_profile_is_a_permanent_readiness_blocker(self):
        audit = build_audit(
            profile_key="missing.profile", year=2026, target_time=time(9, 30),
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        self.assertIn("requested_service_profile_missing", audit["profile_resolution"]["issues"])

    def test_schema_readiness_requires_current_0012_fk_prerequisites_only(self):
        schema = get_schema_readiness()
        checks = {check["migration"]: check for check in schema["checks"]}

        self.assertTrue(schema["ready"])
        self.assertEqual(
            set(checks),
            {
                "events.0009_serviceeventplannerassignment",
                "events.0010_serviceevent_scheduling_revision",
                "events.0012_serviceprofile_serviceevent_service_profile",
            },
        )
        fk_check = checks["events.0012_serviceprofile_serviceevent_service_profile"]
        self.assertTrue(fk_check["service_profile_table_present"])
        self.assertTrue(fk_check["service_profile_id_column_present"])
        self.assertNotIn("service_profile_key", json.dumps(schema, sort_keys=True))

    def test_expected_2026_sundays_are_complete_and_weekly(self):
        sundays = build_expected_sundays(2026)

        self.assertEqual(len(sundays), 52)
        self.assertEqual(sundays[0].isoformat(), "2026-01-04")
        self.assertEqual(sundays[-1].isoformat(), "2026-12-27")
        self.assertTrue(all(value.weekday() == 6 for value in sundays))
        self.assertTrue(
            all((right - left).days == 7 for left, right in zip(sundays, sundays[1:]))
        )

    def test_one_exact_fk_row_is_ready_but_year_remains_incomplete(self):
        event = self.make_event(profile=self.profile)
        self.add_audience(event)

        audit = self.audit()
        fact = audit["canonical_tagged_rows"][0]

        self.assertEqual(fact["classification"], "EXACT READY MATCH")
        self.assertTrue(fact["row_ready"])
        self.assertEqual(audit["summary"]["ready_exact_matches"], 1)
        self.assertEqual(audit["summary"]["missing_canonical_profile_sundays"], 51)
        self.assertNotEqual(audit["recommendation"], "PROFILE SETUP READY")

    def test_all_52_exact_fk_rows_are_profile_setup_ready(self):
        for sunday in build_expected_sundays(2026):
            event = self.make_event(profile=self.profile, day=sunday)
            self.add_audience(event)

        audit = self.audit()

        self.assertEqual(audit["summary"]["canonical_tagged_rows"], 52)
        self.assertEqual(audit["summary"]["ready_exact_matches"], 52)
        self.assertEqual(audit["summary"]["missing_canonical_profile_sundays"], 0)
        self.assertEqual(audit["recommendation"], "PROFILE SETUP READY")

    def test_inactive_and_wrong_type_requested_profiles_fail_closed(self):
        self.profile.is_active = False
        self.profile.save()
        inactive = self.audit()
        self.assertIn(
            "requested_service_profile_inactive", inactive["profile_resolution"]["issues"]
        )

        self.profile.is_active = True
        self.profile.event_type = ServiceEvent.EVENT_BIBLE_STUDY
        self.profile.save()
        wrong_type = self.audit()
        self.assertIn(
            "requested_service_profile_event_type_mismatch",
            wrong_type["profile_resolution"]["issues"],
        )

    def test_missing_exact_time_candidate_is_reported(self):
        row = self.day(self.audit())

        self.assertEqual(row["classification"], "NO 09:30 CANDIDATE")
        self.assertEqual(row["untagged_exact_time_candidates"], 0)
        self.assertEqual(row["event_profile_type_mismatch_count"], 0)

    def test_profileless_exact_time_candidate_requires_human_review(self):
        event = ServiceEvent.objects.create(
            title="Unprofiled Sunday",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.make_aware(datetime(2026, 1, 4, 9, 30)),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        ServiceEventAudienceScope.objects.create(service_event=event, unit=self.unit)

        audit = build_audit(
            profile_key=self.profile.key,
            year=2026,
            target_time=time(9, 30),
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        row = next(row for row in audit["sundays"] if row["date"] == "2026-01-04")

        self.assertEqual(
            row["classification"],
            "UNTAGGED CANDIDATE / HUMAN REVIEW REQUIRED",
        )
        self.assertEqual(row["untagged_exact_time_candidates"], 1)
        self.assertEqual(row["event_profile_type_mismatch_count"], 0)
        self.assertEqual(row["candidates"][0]["id"], event.pk)

    def test_event_profile_type_mismatch_is_not_an_untagged_candidate(self):
        mismatched_profile = ServiceProfile.objects.create(
            key="weekday.study",
            name="Weekday Study",
            event_type=ServiceEvent.EVENT_BIBLE_STUDY,
        )
        event = ServiceEvent.objects.create(
            title="Drifted exact-time event",
            event_type=ServiceEvent.EVENT_BIBLE_STUDY,
            start_datetime=timezone.make_aware(datetime(2026, 1, 4, 9, 30)),
            status=ServiceEvent.STATUS_PUBLISHED,
            service_profile=mismatched_profile,
        )
        ServiceEvent.objects.filter(pk=event.pk).update(
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE
        )
        ServiceEventAudienceScope.objects.create(service_event=event, unit=self.unit)

        audit = build_audit(
            profile_key=self.profile.key,
            year=2026,
            target_time=time(9, 30),
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        row = next(row for row in audit["sundays"] if row["date"] == "2026-01-04")

        self.assertEqual(
            row["classification"], "EVENT/PROFILE TYPE MISMATCH — NOT READY"
        )
        self.assertEqual(row["event_profile_type_mismatch_count"], 1)
        self.assertEqual(row["untagged_exact_time_candidates"], 0)

    def test_multiple_profileless_candidates_require_human_selection(self):
        first = self.make_event(title="First candidate")
        second = self.make_event(title="Second candidate")
        self.add_audience(first)
        self.add_audience(second)

        row = self.day(self.audit())

        self.assertEqual(
            row["classification"],
            "MULTIPLE UNTAGGED CANDIDATES — HUMAN SELECTION REQUIRED",
        )
        self.assertEqual(row["untagged_exact_time_candidates"], 2)
        self.assertEqual([item["id"] for item in row["candidates"]], [first.pk, second.pk])

    def test_requested_event_type_controls_profileless_candidate_discovery(self):
        special_profile = ServiceProfile.objects.create(
            key="special.meeting",
            name="Special Meeting",
            event_type=ServiceEvent.EVENT_SPECIAL_MEETING,
        )
        sunday = self.make_event(title="Sunday candidate")
        special = self.make_event(
            title="Special candidate",
            event_type=ServiceEvent.EVENT_SPECIAL_MEETING,
        )
        self.add_audience(sunday)
        self.add_audience(special)

        audit = build_audit(
            profile_key=special_profile.key,
            year=2026,
            target_time=time(9, 30),
            event_type=ServiceEvent.EVENT_SPECIAL_MEETING,
        )
        row = self.day(audit)

        self.assertEqual(row["untagged_exact_time_candidates"], 1)
        self.assertEqual([item["id"] for item in row["candidates"]], [special.pk])
        self.assertNotIn(sunday.pk, [item["id"] for item in row["candidates"]])

    def test_other_profile_evidence_is_not_a_candidate_and_counts_stay_distinct(self):
        candidate = self.make_event(title="Candidate")
        other_profile = ServiceProfile.objects.create(
            key="sunday.other",
            name="Other Sunday",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        other_event = self.make_event(profile=other_profile, title="Parallel event")
        self.add_audience(candidate)
        self.add_audience(other_event)

        audit = self.audit()
        row = self.day(audit)

        self.assertEqual(row["untagged_exact_time_candidates"], 1)
        self.assertEqual(row["other_profile_exact_time_count"], 1)
        self.assertEqual([item["id"] for item in row["candidates"]], [candidate.pk])
        self.assertEqual(
            [item["id"] for item in row["other_profile_exact_time_events"]],
            [other_event.pk],
        )
        self.assertTrue(
            row["other_profile_exact_time_events"][0]["classification"].endswith(
                "NOT A CANDIDATE"
            )
        )

    def test_duplicate_wrong_time_and_wrong_date_canonical_rows_fail_readiness(self):
        first = self.make_event(profile=self.profile, title="First")
        second = self.make_event(profile=self.profile, title="Second")
        self.add_audience(first)
        self.add_audience(second)
        duplicate = self.audit()
        self.assertEqual(self.day(duplicate)["classification"], "DUPLICATE CANONICAL PROFILE ROWS")
        self.assertEqual(duplicate["summary"]["duplicate_canonical_sundays"], 1)

        ServiceEvent.objects.all().delete()
        wrong_time = self.make_event(profile=self.profile, at=time(11, 30))
        wrong_date = self.make_event(profile=self.profile, day=build_expected_sundays(2026)[0].replace(year=2027))
        self.add_audience(wrong_time)
        self.add_audience(wrong_date)
        audit = self.audit()
        issues = [fact["identity_issues"] for fact in audit["canonical_tagged_rows"]]
        self.assertTrue(any("wrong_local_time" in value for value in issues))
        self.assertTrue(any("wrong_year_or_date" in value for value in issues))

    def test_lifecycle_published_and_completed_are_ready_but_draft_and_cancelled_block(self):
        for status, issue, ready in (
            (ServiceEvent.STATUS_PUBLISHED, None, True),
            (ServiceEvent.STATUS_COMPLETED, None, True),
            (ServiceEvent.STATUS_DRAFT, "draft", False),
            (ServiceEvent.STATUS_CANCELLED, "cancelled", False),
        ):
            with self.subTest(status=status):
                event = self.make_event(profile=self.profile, status=status)
                self.add_audience(event)
                fact = self.audit()["canonical_tagged_rows"][0]
                self.assertEqual(fact["row_ready"], ready)
                if issue:
                    self.assertIn(issue, fact["readiness_issues"])
                ServiceEvent.objects.all().delete()

    def test_zero_inactive_and_overlapping_audiences_fail_closed(self):
        event = self.make_event(profile=self.profile)
        zero = self.audit()["canonical_tagged_rows"][0]
        self.assertIn("zero_audience_rows", zero["readiness_issues"])

        child = ChurchStructureUnit.objects.create(
            parent=self.unit,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="Chinese Ministry",
        )
        self.add_audience(event, child)
        ChurchStructureUnit.objects.filter(pk=child.pk).update(is_active=False)
        inactive = self.audit()["canonical_tagged_rows"][0]
        self.assertIn("inactive_audience_units", inactive["readiness_issues"])

        ChurchStructureUnit.objects.filter(pk=child.pk).update(is_active=True)
        ServiceEventAudienceScope.objects.bulk_create(
            [ServiceEventAudienceScope(service_event=event, unit=self.unit)]
        )
        overlap = self.audit()["canonical_tagged_rows"][0]
        self.assertIn("ancestor_descendant_overlap", overlap["readiness_issues"])

    def test_command_outputs_v3_current_semantics_without_legacy_evidence(self):
        event = self.make_event(profile=self.profile)
        self.add_audience(event)
        json_output = StringIO()
        text_output = StringIO()

        call_command("audit_service_profile_readiness", "--json", stdout=json_output)
        call_command("audit_service_profile_readiness", stdout=text_output)
        payload = json.loads(json_output.getvalue())

        self.assertEqual(payload["contract_version"], SERVICE_PROFILE_READINESS_CONTRACT_VERSION)
        self.assertEqual(payload["canonical_tagged_rows"][0]["service_profile_id"], self.profile.pk)
        self.assertNotIn("compatibility_key", json_output.getvalue())
        self.assertNotIn("legacy_only", json_output.getvalue())
        self.assertIn(SERVICE_PROFILE_READINESS_CONTRACT_VERSION, text_output.getvalue())
