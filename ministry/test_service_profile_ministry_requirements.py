"""Focused GENERIC-DEPLOYMENT-CONFIG.6A foundation tests."""

import importlib
from io import StringIO

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.db import migrations, models
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from accounts.trial_setup_readiness import run_audit as run_trial_readiness
from events.admin import ServiceProfileAdmin
from events.forms import RecurringServiceEventForm, ServiceEventForm
from events.models import (
    ServiceEvent,
    ServiceEventRequiredTeam,
    ServiceProfile,
)
from notifications.models import Notification

from .admin import (
    ServiceProfileMinistryRequirementAdmin,
    ServiceProfileMinistryRequirementAdminForm,
)
from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    ServiceProfileMinistryRequirement,
    TeamAssignment,
)
from .service_profile_ministry_requirements import (
    RequirementValidationReason,
    RequirementValidationState,
    inspect_service_profile_ministry_requirements,
)
from .services.worship_governance import (
    resolve_worship_rotation_pool_for_team,
)


def profile_values(**overrides):
    values = {
        "key": "sunday.standard",
        "name": "Standard Sunday",
        "name_en": "Standard Sunday",
        "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
    }
    values.update(overrides)
    return values


class RequirementFixtureMixin:
    def setUp(self):
        super().setUp()
        self.profile = ServiceProfile.objects.create(**profile_values())
        self.team = MinistryTeam.objects.create(
            name="Production Team",
            name_en="Production Team",
            team_key="production.team",
            is_active=True,
            is_assignable=True,
        )

    def create_requirement(self, **overrides):
        values = {
            "service_profile": self.profile,
            "ministry_team": self.team,
        }
        values.update(overrides)
        return ServiceProfileMinistryRequirement.objects.create(**values)

    def create_worship_pool_and_child(self):
        pool = MinistryTeam.objects.create(
            name="Rotation Pool",
            name_en="Rotation Pool",
            team_key="rotation.pool",
            is_active=True,
            is_assignable=False,
            is_worship_rotation_pool=True,
        )
        child = MinistryTeam.objects.create(
            name="Rotation Child",
            name_en="Rotation Child",
            team_key="rotation.child",
            is_active=True,
            is_assignable=True,
        )
        MinistryTeamParentLink.objects.create(
            child_team=child,
            parent_team=pool,
            is_primary=True,
            is_active=True,
        )
        return pool, child


class ServiceProfileMinistryRequirementModelTests(
    RequirementFixtureMixin, TestCase
):
    def test_frozen_fields_foreign_keys_and_constraint(self):
        fields = {
            field.name: field
            for field in ServiceProfileMinistryRequirement._meta.fields
        }
        self.assertEqual(
            set(fields),
            {
                "id",
                "service_profile",
                "ministry_team",
                "is_active",
                "sort_order",
                "created_at",
                "updated_at",
            },
        )
        self.assertIs(fields["service_profile"].remote_field.on_delete, models.CASCADE)
        self.assertEqual(
            fields["service_profile"].remote_field.related_name,
            "ministry_requirements",
        )
        self.assertIs(fields["ministry_team"].remote_field.on_delete, models.PROTECT)
        self.assertEqual(
            fields["ministry_team"].remote_field.related_name,
            "service_profile_requirement_links",
        )
        self.assertTrue(fields["is_active"].default)
        self.assertEqual(fields["sort_order"].default, 0)
        constraints = ServiceProfileMinistryRequirement._meta.constraints
        self.assertEqual(len(constraints), 1)
        self.assertEqual(
            tuple(constraints[0].fields),
            ("service_profile", "ministry_team"),
        )

    def test_migration_is_schema_only_with_exact_foundation_dependencies(self):
        migration_module = importlib.import_module(
            "ministry.migrations.0007_serviceprofileministryrequirement"
        )
        self.assertEqual(
            set(migration_module.Migration.dependencies),
            {
                (
                    "events",
                    "0012_serviceprofile_serviceevent_service_profile",
                ),
                ("ministry", "0006_ministryteam_team_key"),
            },
        )
        self.assertEqual(len(migration_module.Migration.operations), 1)
        self.assertIsInstance(
            migration_module.Migration.operations[0],
            migrations.CreateModel,
        )

    def test_valid_active_requirement_succeeds(self):
        requirement = self.create_requirement()
        self.assertTrue(requirement.is_active)
        self.assertEqual(requirement.sort_order, 0)

    def test_profile_and_team_creation_create_no_default_requirement(self):
        self.assertEqual(ServiceProfileMinistryRequirement.objects.count(), 0)

    def test_active_requirement_rejects_inactive_profile(self):
        self.profile.is_active = False
        self.profile.save()
        with self.assertRaises(ValidationError) as raised:
            self.create_requirement()
        self.assertEqual(
            raised.exception.error_dict["service_profile"][0].code,
            RequirementValidationReason.PROFILE_INACTIVE.value,
        )

    def test_active_requirement_rejects_inactive_team(self):
        self.team.is_active = False
        self.team.save()
        with self.assertRaises(ValidationError) as raised:
            self.create_requirement()
        self.assertEqual(
            raised.exception.error_dict["ministry_team"][0].code,
            RequirementValidationReason.TEAM_INACTIVE.value,
        )

    def test_active_requirement_rejects_non_assignable_team(self):
        self.team.is_assignable = False
        self.team.save()
        with self.assertRaises(ValidationError) as raised:
            self.create_requirement()
        codes = {
            error.code
            for error in raised.exception.error_dict["ministry_team"]
        }
        self.assertIn(
            RequirementValidationReason.TEAM_NON_ASSIGNABLE.value,
            codes,
        )

    def test_active_requirement_rejects_worship_pool_itself(self):
        pool, _child = self.create_worship_pool_and_child()
        with self.assertRaises(ValidationError) as raised:
            self.create_requirement(ministry_team=pool)
        codes = {
            error.code
            for error in raised.exception.error_dict["ministry_team"]
        }
        self.assertIn(
            RequirementValidationReason.TEAM_WORSHIP_ROTATION_POOL.value,
            codes,
        )

    def test_active_requirement_rejects_canonical_worship_child(self):
        _pool, child = self.create_worship_pool_and_child()
        self.assertIsNotNone(
            resolve_worship_rotation_pool_for_team(child).pool
        )
        with self.assertRaises(ValidationError) as raised:
            self.create_requirement(ministry_team=child)
        self.assertEqual(
            raised.exception.error_dict["ministry_team"][0].code,
            RequirementValidationReason.TEAM_UNDER_WORSHIP_ROTATION_POOL.value,
        )

    def test_unrelated_active_assignable_team_succeeds(self):
        self.assertIsNone(
            resolve_worship_rotation_pool_for_team(self.team).pool
        )
        requirement = self.create_requirement()
        self.assertEqual(requirement.ministry_team, self.team)

    def test_inactive_history_may_retain_now_invalid_profile_and_team(self):
        requirement = self.create_requirement(is_active=False)
        ServiceProfile.objects.filter(pk=self.profile.pk).update(is_active=False)
        MinistryTeam.objects.filter(pk=self.team.pk).update(
            is_active=False,
            is_assignable=False,
            is_worship_rotation_pool=True,
        )
        requirement.refresh_from_db()
        requirement.sort_order = 7
        requirement.save()
        self.assertFalse(requirement.is_active)
        self.assertEqual(requirement.sort_order, 7)

    def test_reactivating_invalid_history_fails_closed(self):
        requirement = self.create_requirement(is_active=False)
        ServiceProfile.objects.filter(pk=self.profile.pk).update(is_active=False)
        requirement.refresh_from_db()
        requirement.is_active = True
        with self.assertRaises(ValidationError):
            requirement.save()
        requirement.refresh_from_db()
        self.assertFalse(requirement.is_active)

    def test_duplicate_pair_fails_for_active_or_inactive_existing_row(self):
        for existing_active in (True, False):
            with self.subTest(existing_active=existing_active):
                ServiceProfileMinistryRequirement.objects.all().delete()
                self.create_requirement(is_active=existing_active)
                for proposed_active in (True, False):
                    with self.subTest(proposed_active=proposed_active):
                        with self.assertRaises(ValidationError):
                            self.create_requirement(is_active=proposed_active)

    def test_team_delete_is_protected_for_active_and_inactive_rows(self):
        for active in (True, False):
            with self.subTest(active=active):
                profile = ServiceProfile.objects.create(
                    **profile_values(
                        key=f"sunday.{active}",
                        name=f"Profile {active}",
                    )
                )
                team = MinistryTeam.objects.create(name=f"Static Team {active}")
                ServiceProfileMinistryRequirement.objects.create(
                    service_profile=profile,
                    ministry_team=team,
                    is_active=active,
                )
                with self.assertRaises(ProtectedError):
                    team.delete()
                self.assertTrue(MinistryTeam.objects.filter(pk=team.pk).exists())

    def test_protected_team_delete_rolls_back_scheduling_revision(self):
        requirement = self.create_requirement()
        event = ServiceEvent.objects.create(
            title="Revision guard event",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=3),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        event.refresh_from_db()
        before_revision = event.scheduling_revision

        with self.assertRaises(ProtectedError):
            requirement.ministry_team.delete()

        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, before_revision)

    def test_unreferenced_profile_delete_cascades_owned_requirements(self):
        requirement = self.create_requirement()
        profile_id = self.profile.pk
        requirement_id = requirement.pk
        self.profile.delete()
        self.assertFalse(ServiceProfile.objects.filter(pk=profile_id).exists())
        self.assertFalse(
            ServiceProfileMinistryRequirement.objects.filter(
                pk=requirement_id
            ).exists()
        )

    def test_requirement_reference_makes_profile_identity_immutable(self):
        self.create_requirement(is_active=False)
        self.profile.key = "changed.key"
        with self.assertRaises(ValidationError) as key_error:
            self.profile.save()
        self.assertEqual(
            key_error.exception.error_dict["key"][0].code,
            "referenced_service_profile_key_immutable",
        )

        self.profile.refresh_from_db()
        self.profile.event_type = ServiceEvent.EVENT_BIBLE_STUDY
        with self.assertRaises(ValidationError) as type_error:
            self.profile.save()
        self.assertEqual(
            type_error.exception.error_dict["event_type"][0].code,
            "referenced_service_profile_event_type_immutable",
        )

    def test_requirement_reference_allows_profile_labels_and_lifecycle(self):
        self.create_requirement()
        self.profile.name = "Updated profile"
        self.profile.name_en = "Updated profile English"
        self.profile.description = "Updated description"
        self.profile.description_en = "Updated description English"
        self.profile.is_active = False
        self.profile.save()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.name, "Updated profile")
        self.assertEqual(self.profile.description, "Updated description")
        self.assertFalse(self.profile.is_active)

    def test_sort_order_and_requirement_mutations_materialize_nothing(self):
        event = ServiceEvent.objects.create(
            title="No materialization event",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            service_profile_key=self.profile.key,
            service_profile=self.profile,
            start_datetime=timezone.now() + timezone.timedelta(days=4),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        before_revision = event.scheduling_revision
        before_required = ServiceEventRequiredTeam.objects.count()
        before_events = ServiceEvent.objects.count()
        before_assignments = TeamAssignment.objects.count()
        before_notifications = Notification.objects.count()

        requirement = self.create_requirement(sort_order=1)
        requirement.sort_order = 99
        requirement.save()
        requirement.is_active = False
        requirement.save()
        requirement.delete()

        event.refresh_from_db()
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), before_required)
        self.assertEqual(ServiceEvent.objects.count(), before_events)
        self.assertEqual(TeamAssignment.objects.count(), before_assignments)
        self.assertEqual(Notification.objects.count(), before_notifications)
        self.assertEqual(event.scheduling_revision, before_revision)
        self.assertIsNone(event.rotation_anchor_team_id)


class ServiceProfileMinistryRequirementInspectionTests(
    RequirementFixtureMixin, TestCase
):
    def test_zero_rows_is_ready_without_blocker(self):
        inspection = inspect_service_profile_ministry_requirements()
        self.assertEqual(inspection.rows, ())
        self.assertEqual(inspection.integrity_blockers, 0)

    def test_valid_active_and_inactive_invalid_classification(self):
        valid = self.create_requirement()
        other_profile = ServiceProfile.objects.create(
            **profile_values(key="sunday.other", name="Other profile")
        )
        other_team = MinistryTeam.objects.create(name="Usher Team")
        history = ServiceProfileMinistryRequirement.objects.create(
            service_profile=other_profile,
            ministry_team=other_team,
            is_active=False,
        )
        ServiceProfile.objects.filter(pk=other_profile.pk).update(is_active=False)
        MinistryTeam.objects.filter(pk=other_team.pk).update(
            is_active=False,
            is_assignable=False,
            is_worship_rotation_pool=True,
        )

        inspection = inspect_service_profile_ministry_requirements()
        by_id = {row.requirement_id: row for row in inspection.rows}
        self.assertEqual(
            by_id[valid.pk].validation_state,
            RequirementValidationState.VALID_ACTIVE,
        )
        self.assertEqual(
            by_id[history.pk].validation_state,
            RequirementValidationState.INACTIVE_HISTORY,
        )
        self.assertEqual(
            set(by_id[history.pk].validation_reasons),
            {
                RequirementValidationReason.PROFILE_INACTIVE,
                RequirementValidationReason.TEAM_INACTIVE,
                RequirementValidationReason.TEAM_NON_ASSIGNABLE,
                RequirementValidationReason.TEAM_WORSHIP_ROTATION_POOL,
            },
        )
        self.assertEqual(inspection.valid_active_requirements, 1)
        self.assertEqual(inspection.inactive_requirements, 1)
        self.assertEqual(inspection.integrity_blockers, 0)

    def test_each_active_drift_reason_is_a_blocker(self):
        scenarios = (
            (
                RequirementValidationReason.PROFILE_INACTIVE,
                lambda: ServiceProfile.objects.filter(pk=self.profile.pk).update(
                    is_active=False
                ),
            ),
            (
                RequirementValidationReason.TEAM_INACTIVE,
                lambda: MinistryTeam.objects.filter(pk=self.team.pk).update(
                    is_active=False
                ),
            ),
            (
                RequirementValidationReason.TEAM_NON_ASSIGNABLE,
                lambda: MinistryTeam.objects.filter(pk=self.team.pk).update(
                    is_assignable=False
                ),
            ),
            (
                RequirementValidationReason.TEAM_WORSHIP_ROTATION_POOL,
                lambda: MinistryTeam.objects.filter(pk=self.team.pk).update(
                    is_assignable=False,
                    is_worship_rotation_pool=True,
                ),
            ),
        )
        for reason, mutate in scenarios:
            with self.subTest(reason=reason):
                self.profile.refresh_from_db()
                self.team.refresh_from_db()
                ServiceProfile.objects.filter(pk=self.profile.pk).update(
                    is_active=True
                )
                MinistryTeam.objects.filter(pk=self.team.pk).update(
                    is_active=True,
                    is_assignable=True,
                    is_worship_rotation_pool=False,
                )
                self.profile.refresh_from_db()
                self.team.refresh_from_db()
                ServiceProfileMinistryRequirement.objects.all().delete()
                requirement = self.create_requirement()
                mutate()
                row = inspect_service_profile_ministry_requirements().rows[0]
                self.assertEqual(requirement.pk, row.requirement_id)
                self.assertEqual(
                    row.validation_state,
                    RequirementValidationState.INVALID_ACTIVE,
                )
                self.assertIn(reason, row.validation_reasons)

    def test_worship_child_active_drift_is_blocker(self):
        requirement = self.create_requirement()
        pool = MinistryTeam.objects.create(
            name="Rotation Container",
            is_assignable=False,
            is_worship_rotation_pool=True,
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.team,
            parent_team=pool,
            is_primary=True,
        )
        row = inspect_service_profile_ministry_requirements().rows[0]
        self.assertEqual(row.requirement_id, requirement.pk)
        self.assertIn(
            RequirementValidationReason.TEAM_UNDER_WORSHIP_ROTATION_POOL,
            row.validation_reasons,
        )
        self.assertEqual(
            inspect_service_profile_ministry_requirements().integrity_blockers,
            1,
        )

    def test_audit_command_is_read_only_and_preserves_timestamps(self):
        requirement = self.create_requirement()
        before = (
            ServiceProfileMinistryRequirement.objects.values(
                "created_at", "updated_at"
            ).get(pk=requirement.pk)
        )
        counts = {
            model.__name__: model.objects.count()
            for model in (
                ServiceProfile,
                ServiceProfileMinistryRequirement,
                ServiceEvent,
                ServiceEventRequiredTeam,
                TeamAssignment,
            )
        }
        output = StringIO()
        call_command(
            "audit_service_profile_ministry_requirements",
            stdout=output,
        )
        after = (
            ServiceProfileMinistryRequirement.objects.values(
                "created_at", "updated_at"
            ).get(pk=requirement.pk)
        )
        self.assertEqual(before, after)
        self.assertEqual(
            counts,
            {
                model.__name__: model.objects.count()
                for model in (
                    ServiceProfile,
                    ServiceProfileMinistryRequirement,
                    ServiceEvent,
                    ServiceEventRequiredTeam,
                    TeamAssignment,
                )
            },
        )
        self.assertIn("mode: read-only", output.getvalue())
        self.assertIn("valid_active_requirements: 1", output.getvalue())

    def test_zero_row_command_reports_ready_not_warning(self):
        output = StringIO()
        call_command(
            "audit_service_profile_ministry_requirements",
            stdout=output,
        )
        self.assertIn(
            "READY / NO PROFILE MINISTRY DEFAULTS CONFIGURED",
            output.getvalue(),
        )

    def test_audit_command_has_no_apply_option(self):
        from .management.commands.audit_service_profile_ministry_requirements import (
            Command,
        )

        parser = Command().create_parser(
            "manage.py",
            "audit_service_profile_ministry_requirements",
        )
        self.assertNotIn("apply", {action.dest for action in parser._actions})

    def test_profile_key_filter_is_exact_and_missing_fails_cleanly(self):
        self.create_requirement()
        similar = ServiceProfile.objects.create(
            **profile_values(key="sunday.standard.extra", name="Similar")
        )
        ServiceProfileMinistryRequirement.objects.create(
            service_profile=similar,
            ministry_team=MinistryTeam.objects.create(name="Static Team"),
        )
        output = StringIO()
        call_command(
            "audit_service_profile_ministry_requirements",
            "--profile-key",
            self.profile.key,
            stdout=output,
        )
        self.assertIn(f"profile_id={self.profile.pk}", output.getvalue())
        self.assertNotIn(f"profile_id={similar.pk}", output.getvalue())
        with self.assertRaises(CommandError):
            call_command(
                "audit_service_profile_ministry_requirements",
                "--profile-key",
                "SUNDAY.STANDARD",
                stdout=StringIO(),
            )


class ServiceProfileMinistryRequirementReadinessTests(
    RequirementFixtureMixin, TestCase
):
    def ministry_section(self):
        for section in run_trial_readiness()["sections"]:
            if section.key == "ministry_structure":
                return section
        raise AssertionError("ministry_structure section missing")

    def test_zero_and_valid_defaults_add_no_blocker(self):
        section = self.ministry_section()
        self.assertEqual(
            section.blockers[
                "invalid_active_service_profile_ministry_requirements"
            ],
            0,
        )
        self.create_requirement()
        section = self.ministry_section()
        self.assertEqual(
            section.blockers[
                "invalid_active_service_profile_ministry_requirements"
            ],
            0,
        )

    def test_only_invalid_active_default_adds_blocker(self):
        active = self.create_requirement()
        ServiceProfileMinistryRequirement.objects.create(
            service_profile=ServiceProfile.objects.create(
                **profile_values(key="history.profile", name="History")
            ),
            ministry_team=MinistryTeam.objects.create(name="History Team"),
            is_active=False,
        )
        MinistryTeam.objects.filter(pk=self.team.pk).update(is_active=False)
        section = self.ministry_section()
        self.assertEqual(
            section.blockers[
                "invalid_active_service_profile_ministry_requirements"
            ],
            1,
        )
        self.assertIn(
            f"requirement_id={active.pk}",
            section.details[
                "invalid_active_service_profile_ministry_requirements"
            ][0],
        )

    @override_settings(
        CMS_ENABLED_MODULES=["reading", "prayers", "studies", "events"]
    )
    def test_disabling_ministry_preserves_provider_gate(self):
        self.create_requirement()
        keys = [section.key for section in run_trial_readiness()["sections"]]
        self.assertNotIn("ministry_structure", keys)
        self.assertNotIn("team_serving", keys)


class ServiceProfileMinistryRequirementAdminTests(
    RequirementFixtureMixin, TestCase
):
    def setUp(self):
        super().setUp()
        self.request = RequestFactory().get(
            "/admin/ministry/serviceprofileministryrequirement/"
        )

    def test_model_registered_and_keys_are_visible(self):
        self.assertTrue(admin.site.is_registered(ServiceProfileMinistryRequirement))
        model_admin = ServiceProfileMinistryRequirementAdmin(
            ServiceProfileMinistryRequirement,
            admin.site,
        )
        requirement = self.create_requirement()
        self.assertIn("service_profile_key", model_admin.list_display)
        self.assertIn("ministry_team_key", model_admin.list_display)
        self.assertEqual(
            model_admin.service_profile_key(requirement),
            self.profile.key,
        )
        self.assertEqual(
            model_admin.ministry_team_key(requirement),
            self.team.team_key,
        )

    def test_profile_admin_locks_identity_for_inactive_requirement_reference(self):
        self.create_requirement(is_active=False)
        model_admin = ServiceProfileAdmin(ServiceProfile, admin.site)
        readonly = model_admin.get_readonly_fields(self.request, self.profile)
        self.assertIn("key", readonly)
        self.assertIn("event_type", readonly)
        self.assertNotIn("name", readonly)
        self.assertNotIn("description", readonly)
        self.assertNotIn("is_active", readonly)

    def test_new_choices_exclude_inactive_and_worship_invalid_rows(self):
        inactive_profile = ServiceProfile.objects.create(
            **profile_values(
                key="inactive.profile",
                name="Inactive",
                is_active=False,
            )
        )
        inactive_team = MinistryTeam.objects.create(
            name="Inactive Team",
            is_active=False,
        )
        non_assignable = MinistryTeam.objects.create(
            name="Container Team",
            is_assignable=False,
        )
        pool, child = self.create_worship_pool_and_child()
        form = ServiceProfileMinistryRequirementAdminForm()
        self.assertNotIn(
            inactive_profile.pk,
            form.fields["service_profile"].queryset.values_list(
                "pk", flat=True
            ),
        )
        team_ids = set(
            form.fields["ministry_team"].queryset.values_list("pk", flat=True)
        )
        self.assertIn(self.team.pk, team_ids)
        self.assertNotIn(inactive_team.pk, team_ids)
        self.assertNotIn(non_assignable.pk, team_ids)
        self.assertNotIn(pool.pk, team_ids)
        self.assertNotIn(child.pk, team_ids)

    def test_worship_child_cannot_bypass_admin_validation(self):
        _pool, child = self.create_worship_pool_and_child()
        form = ServiceProfileMinistryRequirementAdminForm(
            data={
                "service_profile": self.profile.pk,
                "ministry_team": child.pk,
                "is_active": "on",
                "sort_order": 0,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("ministry_team", form.errors)

    def test_invalid_history_is_reviewable_and_can_be_deactivated(self):
        requirement = self.create_requirement()
        MinistryTeam.objects.filter(pk=self.team.pk).update(is_active=False)
        requirement.refresh_from_db()
        unbound = ServiceProfileMinistryRequirementAdminForm(
            instance=requirement
        )
        self.assertIn(
            self.team.pk,
            unbound.fields["ministry_team"].queryset.values_list("pk", flat=True),
        )
        deactivate = ServiceProfileMinistryRequirementAdminForm(
            data={
                "service_profile": self.profile.pk,
                "ministry_team": self.team.pk,
                "sort_order": requirement.sort_order,
            },
            instance=requirement,
        )
        self.assertTrue(deactivate.is_valid(), deactivate.errors)
        saved = deactivate.save()
        self.assertFalse(saved.is_active)

    def test_invalid_history_cannot_be_reactivated(self):
        requirement = self.create_requirement(is_active=False)
        MinistryTeam.objects.filter(pk=self.team.pk).update(is_active=False)
        requirement.refresh_from_db()
        form = ServiceProfileMinistryRequirementAdminForm(
            data={
                "service_profile": self.profile.pk,
                "ministry_team": self.team.pk,
                "is_active": "on",
                "sort_order": requirement.sort_order,
            },
            instance=requirement,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("ministry_team", form.errors)

    def test_ordinary_event_forms_expose_no_profile_default_control(self):
        for form in (ServiceEventForm(), RecurringServiceEventForm()):
            self.assertNotIn("ministry_requirements", form.fields)
            self.assertNotIn(
                "service_profile_ministry_requirements",
                form.fields,
            )

    def test_no_member_facing_ministry_route_was_added(self):
        from .urls import urlpatterns

        route_names = {pattern.name for pattern in urlpatterns}
        self.assertFalse(
            {
                "service_profile_ministry_requirements",
                "service_profile_ministry_requirement",
            }
            & route_names
        )
