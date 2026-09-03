from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import ServiceEvent, ServiceProfile
from .service_profile_runtime import (
    ServiceProfileIdentityState,
    ServiceProfileMutationError,
    ServiceProfileMutationFailure,
    ServiceProfileResolutionError,
    ServiceProfileResolutionFailure,
    clear_service_event_profile,
    inspect_service_profile_identity,
    require_service_profile,
    set_service_event_profile,
)


def event_values(**overrides):
    values = {
        "title": "Runtime identity test",
        "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
        "start_datetime": timezone.now() + timezone.timedelta(days=7),
        "status": ServiceEvent.STATUS_PUBLISHED,
    }
    values.update(overrides)
    return values


def profile_values(**overrides):
    values = {
        "key": "local.sunday",
        "name": "Local Sunday Service",
        "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
    }
    values.update(overrides)
    return values


class ServiceProfileRuntimeInspectionTests(TestCase):
    def setUp(self):
        self.profile = ServiceProfile.objects.create(**profile_values())

    def test_profileless_is_valid_optional_identity_and_required_fails_closed(self):
        event = ServiceEvent.objects.create(**event_values())

        with self.assertNumQueries(0):
            identity = inspect_service_profile_identity(event)

        self.assertEqual(identity.state, ServiceProfileIdentityState.PROFILELESS)
        self.assertIsNone(identity.profile)
        self.assertFalse(identity.is_exact)
        with self.assertNumQueries(0), self.assertRaises(
            ServiceProfileResolutionError
        ) as raised:
            require_service_profile(event)
        self.assertEqual(
            raised.exception.reason,
            ServiceProfileResolutionFailure.IDENTITY_NOT_EXACT,
        )
        self.assertEqual(raised.exception.state, ServiceProfileIdentityState.PROFILELESS)

    def test_legacy_only_never_looks_up_profile_by_compatibility_key(self):
        event = ServiceEvent.objects.create(
            **event_values(service_profile_key=self.profile.key)
        )

        with self.assertNumQueries(0):
            identity = inspect_service_profile_identity(event)
            with self.assertRaises(ServiceProfileResolutionError) as raised:
                require_service_profile(event)

        self.assertEqual(identity.state, ServiceProfileIdentityState.LEGACY_ONLY)
        self.assertIsNone(identity.profile)
        self.assertEqual(raised.exception.state, ServiceProfileIdentityState.LEGACY_ONLY)

    def test_exact_active_uses_loaded_fk_profile(self):
        event = ServiceEvent.objects.create(
            **event_values(
                service_profile=self.profile,
                service_profile_key=self.profile.key,
            )
        )
        event = ServiceEvent.objects.select_related("service_profile").get(pk=event.pk)

        with self.assertNumQueries(0):
            identity = inspect_service_profile_identity(event)
            resolved = require_service_profile(event, require_active=True)

        self.assertEqual(identity.state, ServiceProfileIdentityState.EXACT)
        self.assertTrue(identity.is_exact)
        self.assertIs(identity.profile, event.service_profile)
        self.assertIs(resolved, event.service_profile)

    def test_exact_inactive_identity_is_exact_but_active_requirement_fails(self):
        event = ServiceEvent.objects.create(
            **event_values(
                service_profile=self.profile,
                service_profile_key=self.profile.key,
            )
        )
        self.profile.is_active = False
        self.profile.save()
        event = ServiceEvent.objects.select_related("service_profile").get(pk=event.pk)

        identity = inspect_service_profile_identity(event)

        self.assertEqual(identity.state, ServiceProfileIdentityState.EXACT)
        self.assertIs(require_service_profile(event), event.service_profile)
        with self.assertRaises(ServiceProfileResolutionError) as raised:
            require_service_profile(event, require_active=True)
        self.assertEqual(
            raised.exception.reason,
            ServiceProfileResolutionFailure.PROFILE_INACTIVE,
        )
        self.assertEqual(raised.exception.state, ServiceProfileIdentityState.EXACT)

    def assert_drift_state(self, updates, expected_state):
        event = ServiceEvent.objects.create(
            **event_values(
                service_profile=self.profile,
                service_profile_key=self.profile.key,
            )
        )
        ServiceEvent.objects.filter(pk=event.pk).update(**updates)
        event = ServiceEvent.objects.select_related("service_profile").get(pk=event.pk)

        identity = inspect_service_profile_identity(event)

        self.assertEqual(identity.state, expected_state)
        with self.assertRaises(ServiceProfileResolutionError) as raised:
            require_service_profile(event)
        self.assertEqual(raised.exception.state, expected_state)

    def test_fk_with_blank_compatibility_key_is_drift(self):
        self.assert_drift_state(
            {"service_profile_key": ""},
            ServiceProfileIdentityState.FK_BLANK_KEY,
        )

    def test_fk_key_mismatch_is_drift(self):
        self.assert_drift_state(
            {"service_profile_key": "other.profile"},
            ServiceProfileIdentityState.FK_KEY_MISMATCH,
        )

    def test_fk_event_type_mismatch_is_drift(self):
        self.assert_drift_state(
            {"event_type": ServiceEvent.EVENT_BIBLE_STUDY},
            ServiceProfileIdentityState.EVENT_TYPE_MISMATCH,
        )


class ServiceProfileRuntimeMutationTests(TestCase):
    def setUp(self):
        self.profile = ServiceProfile.objects.create(**profile_values())

    def make_exact_event(self, profile=None):
        profile = profile or self.profile
        return ServiceEvent.objects.create(
            **event_values(
                service_profile=profile,
                service_profile_key=profile.key,
            )
        )

    def assert_persisted_identity(self, event, *, profile_id, key, revision):
        event.refresh_from_db()
        self.assertEqual(event.service_profile_id, profile_id)
        self.assertEqual(event.service_profile_key, key)
        self.assertEqual(event.scheduling_revision, revision)

    def test_assign_active_profile_to_profileless_existing_event_advances_once(self):
        event = ServiceEvent.objects.create(**event_values())

        changed = set_service_event_profile(event, self.profile)

        self.assertTrue(changed)
        self.assert_persisted_identity(
            event,
            profile_id=self.profile.pk,
            key=self.profile.key,
            revision=1,
        )

    def test_assign_explicit_matching_profile_to_legacy_only_advances_once(self):
        event = ServiceEvent.objects.create(
            **event_values(service_profile_key=self.profile.key)
        )

        changed = set_service_event_profile(event, self.profile)

        self.assertTrue(changed)
        self.assert_persisted_identity(
            event,
            profile_id=self.profile.pk,
            key=self.profile.key,
            revision=1,
        )

    def test_legacy_only_conflicting_supplied_profile_fails_without_write(self):
        event = ServiceEvent.objects.create(
            **event_values(service_profile_key="legacy.reviewed")
        )

        with self.assertRaises(ServiceProfileMutationError) as raised:
            set_service_event_profile(event, self.profile)

        self.assertEqual(
            raised.exception.reason,
            ServiceProfileMutationFailure.LEGACY_KEY_CONFLICT,
        )
        self.assert_persisted_identity(
            event,
            profile_id=None,
            key="legacy.reviewed",
            revision=0,
        )

    def test_wrong_event_type_profile_fails_without_write_or_revision(self):
        event = ServiceEvent.objects.create(**event_values())
        profile = ServiceProfile.objects.create(
            **profile_values(
                key="local.study",
                name="Local Study",
                event_type=ServiceEvent.EVENT_BIBLE_STUDY,
            )
        )

        with self.assertRaises(ServiceProfileMutationError) as raised:
            set_service_event_profile(event, profile)

        self.assertEqual(
            raised.exception.reason,
            ServiceProfileMutationFailure.EVENT_TYPE_MISMATCH,
        )
        self.assert_persisted_identity(event, profile_id=None, key="", revision=0)

    def test_inactive_new_assignment_fails_without_write_or_revision(self):
        event = ServiceEvent.objects.create(**event_values())
        self.profile.is_active = False
        self.profile.save()

        with self.assertRaises(ServiceProfileMutationError) as raised:
            set_service_event_profile(event, self.profile)

        self.assertEqual(
            raised.exception.reason,
            ServiceProfileMutationFailure.PROFILE_INACTIVE,
        )
        self.assert_persisted_identity(event, profile_id=None, key="", revision=0)

    def test_exact_same_profile_assignment_is_noop_even_when_historical(self):
        event = self.make_exact_event()
        self.profile.is_active = False
        self.profile.save()

        with patch.object(event, "save", wraps=event.save) as save:
            changed = set_service_event_profile(event, self.profile)

        self.assertFalse(changed)
        save.assert_not_called()
        self.assert_persisted_identity(
            event,
            profile_id=self.profile.pk,
            key=self.profile.key,
            revision=0,
        )

    def test_switch_exact_profile_updates_pair_and_advances_once(self):
        event = self.make_exact_event()
        replacement = ServiceProfile.objects.create(
            **profile_values(key="local.second", name="Second Sunday Service")
        )

        changed = set_service_event_profile(event, replacement)

        self.assertTrue(changed)
        self.assert_persisted_identity(
            event,
            profile_id=replacement.pk,
            key=replacement.key,
            revision=1,
        )

    def test_clear_exact_profile_clears_pair_and_advances_once(self):
        event = self.make_exact_event()

        changed = clear_service_event_profile(event)

        self.assertTrue(changed)
        self.assert_persisted_identity(event, profile_id=None, key="", revision=1)

    def test_clear_already_profileless_is_noop(self):
        event = ServiceEvent.objects.create(**event_values())

        with patch.object(event, "save", wraps=event.save) as save:
            changed = clear_service_event_profile(event)

        self.assertFalse(changed)
        save.assert_not_called()
        self.assert_persisted_identity(event, profile_id=None, key="", revision=0)

    def test_clear_legacy_only_refuses_to_erase_review_evidence(self):
        event = ServiceEvent.objects.create(
            **event_values(service_profile_key=self.profile.key)
        )

        with self.assertRaises(ServiceProfileMutationError) as raised:
            clear_service_event_profile(event)

        self.assertEqual(
            raised.exception.reason,
            ServiceProfileMutationFailure.INVALID_START_STATE,
        )
        self.assert_persisted_identity(
            event,
            profile_id=None,
            key=self.profile.key,
            revision=0,
        )

    def test_mutation_refuses_all_invalid_dual_states_without_repair(self):
        cases = (
            (
                {"service_profile_key": ""},
                ServiceProfileIdentityState.FK_BLANK_KEY,
            ),
            (
                {"service_profile_key": "other.profile"},
                ServiceProfileIdentityState.FK_KEY_MISMATCH,
            ),
            (
                {"event_type": ServiceEvent.EVENT_BIBLE_STUDY},
                ServiceProfileIdentityState.EVENT_TYPE_MISMATCH,
            ),
        )
        for index, (updates, state) in enumerate(cases):
            with self.subTest(state=state):
                event = self.make_exact_event()
                ServiceEvent.objects.filter(pk=event.pk).update(**updates)
                event = ServiceEvent.objects.select_related("service_profile").get(
                    pk=event.pk
                )
                before = ServiceEvent.objects.values(
                    "service_profile_id",
                    "service_profile_key",
                    "event_type",
                    "scheduling_revision",
                ).get(pk=event.pk)

                with self.assertRaises(ServiceProfileMutationError) as raised:
                    if index % 2:
                        clear_service_event_profile(event)
                    else:
                        set_service_event_profile(event, self.profile)

                self.assertEqual(raised.exception.state, state)
                self.assertEqual(
                    raised.exception.reason,
                    ServiceProfileMutationFailure.INVALID_START_STATE,
                )
                self.assertEqual(
                    ServiceEvent.objects.values(
                        "service_profile_id",
                        "service_profile_key",
                        "event_type",
                        "scheduling_revision",
                    ).get(pk=event.pk),
                    before,
                )

    def test_model_validation_failure_rolls_back_pair_and_revision(self):
        event = ServiceEvent.objects.create(**event_values())
        event.end_datetime = event.start_datetime - timezone.timedelta(hours=1)

        with self.assertRaises(ValidationError):
            set_service_event_profile(event, self.profile)

        self.assert_persisted_identity(event, profile_id=None, key="", revision=0)

    def test_unsaved_assignment_creates_exact_event_at_creation_revision(self):
        event = ServiceEvent(**event_values())

        changed = set_service_event_profile(event, self.profile)

        self.assertTrue(changed)
        self.assertIsNotNone(event.pk)
        self.assert_persisted_identity(
            event,
            profile_id=self.profile.pk,
            key=self.profile.key,
            revision=0,
        )
        self.assertEqual(
            inspect_service_profile_identity(event).state,
            ServiceProfileIdentityState.EXACT,
        )
