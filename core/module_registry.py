"""Central CMS module registry and feature gates (MODULAR-CORE.1A).

This is deliberately a small, explicit registry — not a plugin framework.
It gives the project one place that says which CMS modules exist, what
surfaces they contribute, and which are enabled, so nav / Today / setup
surfaces can stop hard-coding that knowledge.

Enablement is controlled by ``settings.CMS_ENABLED_MODULES``. When the
setting is absent, every registered module is enabled, which preserves
current behavior. Enablement is a surface gate only: it hides module
surfaces (nav links, Today cards) but does not unload the module's app,
models, or URLs. Direct URLs of a disabled module remain reachable and
stay protected only by their existing per-view permission/visibility
rules.

Module keys match the Django app labels of the module apps. ``accounts``
(identity, structure core, permissions) and ``comments`` (reflections,
a surface of the reading module) are core/support apps, not registered
modules — see ``docs/MODULE_BOUNDARIES.md``.
"""

from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

# Capability flags: descriptive metadata about which shared surfaces a
# module contributes to. They do not grant behavior by themselves yet;
# consumers opt in surface by surface.
CAPABILITY_NAV = "contributes_nav"
CAPABILITY_TODAY = "contributes_today"
CAPABILITY_SETUP_CHECKS = "contributes_setup_checks"
CAPABILITY_REQUIRES_STRUCTURE_CORE = "requires_structure_core"

KNOWN_CAPABILITIES = frozenset(
    {
        CAPABILITY_NAV,
        CAPABILITY_TODAY,
        CAPABILITY_SETUP_CHECKS,
        CAPABILITY_REQUIRES_STRUCTURE_CORE,
    }
)


@dataclass(frozen=True)
class PrimaryNavEntry:
    """One ordinary authenticated-user nav link contributed by a module."""

    url_name: str
    label_en: str
    label_zh: str
    active_nav: str
    order: int


@dataclass(frozen=True)
class CmsModule:
    """Static metadata for one CMS module. Not a Django model."""

    key: str
    label_en: str
    label_zh: str
    capabilities: frozenset
    # Other registered module keys this module reads at runtime.
    # Structure-core (accounts) is expressed via
    # CAPABILITY_REQUIRES_STRUCTURE_CORE, not listed here.
    depends_on: tuple = ()
    dependency_notes: str = ""
    primary_nav: Optional[PrimaryNavEntry] = None


_REGISTERED_MODULES = (
    CmsModule(
        key="reading",
        label_en="Daily Reading",
        label_zh="每日读经",
        capabilities=frozenset(
            {CAPABILITY_NAV, CAPABILITY_TODAY, CAPABILITY_REQUIRES_STRUCTURE_CORE}
        ),
        primary_nav=PrimaryNavEntry(
            url_name="my_plans",
            label_en="Reading",
            label_zh="读经",
            active_nav="reading",
            order=10,
        ),
        dependency_notes=(
            "Group progress and reflection visibility read structure "
            "snapshots plus active primary ChurchStructureMembership. "
            "The reflection surfaces live in the comments support app."
        ),
    ),
    CmsModule(
        key="prayers",
        label_en="Prayer",
        label_zh="代祷",
        capabilities=frozenset(
            {CAPABILITY_NAV, CAPABILITY_REQUIRES_STRUCTURE_CORE}
        ),
        primary_nav=PrimaryNavEntry(
            url_name="prayer_list",
            label_en="Prayer",
            label_zh="代祷",
            active_nav="prayer",
            order=30,
        ),
        dependency_notes=(
            "Group visibility uses PrayerRequest.structure_unit_at_post "
            "plus active primary ChurchStructureMembership."
        ),
    ),
    CmsModule(
        key="studies",
        label_en="Bible Study",
        label_zh="查经",
        capabilities=frozenset(
            {
                CAPABILITY_NAV,
                CAPABILITY_TODAY,
                CAPABILITY_SETUP_CHECKS,
                CAPABILITY_REQUIRES_STRUCTURE_CORE,
            }
        ),
        primary_nav=PrimaryNavEntry(
            url_name="study_session_list",
            label_en="Bible Study",
            label_zh="查经",
            active_nav="bible_study",
            order=20,
        ),
        dependency_notes=(
            "V2 visibility/generation uses structure audience rows "
            "(BibleStudySeriesAudienceScope / BibleStudyMeetingAudienceScope) "
            "plus active primary ChurchStructureMembership; zero-row "
            "meetings fail closed."
        ),
    ),
    CmsModule(
        key="events",
        label_en="Church Gatherings",
        label_zh="教会聚会",
        capabilities=frozenset(
            {
                CAPABILITY_NAV,
                CAPABILITY_TODAY,
                CAPABILITY_SETUP_CHECKS,
                CAPABILITY_REQUIRES_STRUCTURE_CORE,
            }
        ),
        primary_nav=PrimaryNavEntry(
            url_name="service_event_list",
            label_en="Church Gatherings",
            label_zh="教会聚会",
            active_nav="events",
            order=40,
        ),
        dependency_notes=(
            "Visibility uses ServiceEventAudienceScope rows plus active "
            "primary ChurchStructureMembership; zero-row events fail closed."
        ),
    ),
    CmsModule(
        key="ministry",
        label_en="Ministry Serving",
        label_zh="事工服事",
        capabilities=frozenset(
            {
                CAPABILITY_NAV,
                CAPABILITY_TODAY,
                CAPABILITY_SETUP_CHECKS,
                CAPABILITY_REQUIRES_STRUCTURE_CORE,
            }
        ),
        primary_nav=PrimaryNavEntry(
            url_name="my_serving",
            label_en="My Serving",
            label_zh="我的服事",
            active_nav="my_serving",
            order=50,
        ),
        depends_on=("events",),
        dependency_notes=(
            "TeamAssignment schedules serving against ServiceEvent rows. "
            "Serving is explicit TeamAssignmentMember / linked-user "
            "BibleStudyMeetingRole data; ChurchStructureMembership "
            "(belonging) never implies serving."
        ),
    ),
)

_MODULES_BY_KEY = {module.key: module for module in _REGISTERED_MODULES}


def get_registered_modules():
    """All registered modules, in stable registration order."""
    return _REGISTERED_MODULES


def get_registered_module_keys():
    return tuple(module.key for module in _REGISTERED_MODULES)


def get_module(key):
    try:
        return _MODULES_BY_KEY[key]
    except KeyError:
        raise KeyError(
            f"Unregistered CMS module key {key!r}. "
            f"Registered keys: {', '.join(_MODULES_BY_KEY)}"
        )


def validate_enabled_modules(enabled_keys=None):
    """Validate a set of enabled module keys and return it as a frozenset.

    Two invariants are enforced, both raising ``ImproperlyConfigured``:

    * Every key must be a registered module (catches typos / removed keys).
    * Every enabled module's declared ``depends_on`` modules must also be
      enabled (turns the registry's dependency metadata into a real
      invariant). Structure-core dependence is expressed via
      ``CAPABILITY_REQUIRES_STRUCTURE_CORE``, not ``depends_on``, and is
      not gateable, so it is intentionally not checked here.

    ``enabled_keys=None`` means "all registered modules", which is always
    valid (a module's dependencies are registered modules, so enabling
    everything cannot violate a dependency).
    """
    if enabled_keys is None:
        return frozenset(_MODULES_BY_KEY)

    enabled = frozenset(enabled_keys)

    unknown = sorted(enabled - set(_MODULES_BY_KEY))
    if unknown:
        raise ImproperlyConfigured(
            "CMS_ENABLED_MODULES contains unregistered module keys: "
            f"{', '.join(unknown)}. Registered keys: "
            f"{', '.join(_MODULES_BY_KEY)}"
        )

    missing_dependencies = []
    for key in sorted(enabled):
        for dependency in _MODULES_BY_KEY[key].depends_on:
            if dependency not in enabled:
                missing_dependencies.append(
                    f"module {key!r} requires {dependency!r} to be enabled"
                )
    if missing_dependencies:
        raise ImproperlyConfigured(
            "CMS_ENABLED_MODULES has unmet module dependencies: "
            f"{'; '.join(missing_dependencies)}."
        )

    return enabled


def get_enabled_module_keys():
    """Enabled module keys as a frozenset, validated against the registry.

    Reads ``settings.CMS_ENABLED_MODULES`` on every call so test-time
    ``override_settings`` works. Absent/None setting means all registered
    modules are enabled (current behavior preserved). Unknown keys and
    unmet ``depends_on`` dependencies both raise ``ImproperlyConfigured``.
    """
    configured = getattr(settings, "CMS_ENABLED_MODULES", None)
    if configured is None:
        return validate_enabled_modules(None)
    return validate_enabled_modules(configured)


def get_enabled_modules():
    """Enabled modules, in stable registration order."""
    enabled_keys = get_enabled_module_keys()
    return tuple(
        module for module in _REGISTERED_MODULES if module.key in enabled_keys
    )


def get_enabled_primary_nav_entries():
    """Enabled modules' ordinary primary-nav metadata, in display order."""
    entries = (
        module.primary_nav
        for module in get_enabled_modules()
        if module.primary_nav is not None
    )
    return tuple(sorted(entries, key=lambda entry: entry.order))


def is_module_enabled(key):
    """Whether a registered module is enabled. Raises on unregistered keys.

    Raising (instead of silently returning False) catches typos in code
    paths, since callers always pass literal registered keys.
    """
    get_module(key)
    return key in get_enabled_module_keys()


def module_has_capability(key, capability):
    """Whether a registered module declares a capability (metadata only —
    independent of whether the module is currently enabled)."""
    if capability not in KNOWN_CAPABILITIES:
        raise KeyError(
            f"Unknown CMS module capability {capability!r}. "
            f"Known capabilities: {', '.join(sorted(KNOWN_CAPABILITIES))}"
        )
    return capability in get_module(key).capabilities
