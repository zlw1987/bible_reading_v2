"""Setup/readiness check provider registry and aggregation (MODULAR-CORE.5A).

This is the module-owned setup/readiness foundation described in
``docs/MODULE_BOUNDARIES.md`` (boundary rule 4). It mirrors the Today provider
foundation (``core/today_providers.py``): instead of the central trial setup
audit hard-coding every module's checks in one place, each module can register
a readiness provider against its registered module key, and the central runner
asks :func:`build_readiness_sections` for the merged, ordered section list.

Like the module and Today registries, this is deliberately explicit and small —
not a plugin framework. There is no app auto-discovery: provider bodies live in
their owning modules' ``setup_readiness_provider`` modules, and
``accounts.trial_setup_readiness`` (the audit runner's module) calls each
module's ``register()`` explicitly, in a fixed order, when it is imported (so
the registry is always populated before ``run_audit`` builds the report).

Enablement is a surface gate only, exactly as elsewhere:

* Core providers (``module_key=None``) always run — Church Structure and
  permission/admin readiness are Core and are never gated.
* Module providers (``module_key="studies"`` etc.) run only when the module is
  enabled in ``settings.CMS_ENABLED_MODULES``. Reading the enabled set enforces
  ``core.module_registry`` dependency validation, so an invalid configuration
  raises ``ImproperlyConfigured`` here just as it does for nav / Today.

The audit stays strictly read-only: providers only read data and return
report sections. Belonging (``ChurchStructureMembership``) is never treated as
serving; serving stays explicit (``TeamAssignmentMember`` / linked-user
``BibleStudyMeetingRole``).
"""

from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from core.module_registry import get_enabled_module_keys, get_module


class ReadinessSection:
    """A single labelled readiness report section with severity-classified counters.

    Moved from ``accounts.trial_setup_readiness._Section`` (MODULAR-CORE.5A) so
    core and module-owned providers share one section type. The public shape
    (``key``, ``title``, ``blockers`` / ``warnings`` / ``info`` mappings,
    ``details`` lists, and the ``blocker_count`` / ``warning_count`` sums) is
    unchanged.
    """

    def __init__(self, key, title):
        self.key = key
        self.title = title
        self.blockers = OrderedDict()
        self.warnings = OrderedDict()
        self.info = OrderedDict()
        self.details = defaultdict(list)

    def blocker(self, key, count):
        self.blockers[key] = count

    def warning(self, key, count):
        self.warnings[key] = count

    def add_info(self, key, count):
        self.info[key] = count

    def detail(self, key, line):
        self.details[key].append(line)

    @property
    def blocker_count(self):
        return sum(self.blockers.values())

    @property
    def warning_count(self):
        return sum(self.warnings.values())


@dataclass(frozen=True)
class ReadinessContext:
    """Shared inputs handed to every readiness provider's ``build``.

    ``now`` is the timezone-aware audit instant; ``target_date`` is the local
    date used for active-membership windows. Providers must treat both as
    read-only.
    """

    now: Any
    target_date: Any


# ``build(context) -> sequence of ReadinessSection``. Called only when the
# provider's module is enabled (core providers always run).
ReadinessBuildCallable = Callable[[ReadinessContext], Sequence[ReadinessSection]]


@dataclass(frozen=True)
class ReadinessProvider:
    """One registered readiness contribution."""

    name: str
    build: ReadinessBuildCallable
    # None => Core provider (always runs). Otherwise a registered module key,
    # run only when that module is enabled.
    module_key: Optional[str]


# name -> ReadinessProvider, in registration order (dicts preserve it).
_READINESS_PROVIDERS = {}


def register_readiness_provider(name, build, *, module_key=None):
    """Register ``build`` as a readiness provider under a unique ``name``.

    ``module_key=None`` marks a Core provider that always runs. A non-None
    ``module_key`` must be a registered module (same typo protection as
    ``is_module_enabled``); its provider runs only when the module is enabled.
    A non-callable ``build`` or a duplicate ``name`` raises ``ValueError``;
    an unregistered ``module_key`` raises ``KeyError``.
    """
    if not callable(build):
        raise ValueError(
            f"Readiness provider {name!r} must be callable, got "
            f"{type(build).__name__}."
        )

    if name in _READINESS_PROVIDERS:
        raise ValueError(
            f"A readiness provider is already registered under name {name!r}."
        )

    if module_key is not None:
        get_module(module_key)  # raises KeyError on unregistered keys

    _READINESS_PROVIDERS[name] = ReadinessProvider(
        name=name,
        build=build,
        module_key=module_key,
    )


def get_registered_readiness_provider_names():
    """Registered provider names, in registration order."""
    return tuple(_READINESS_PROVIDERS)


def build_readiness_sections(context):
    """Ordered readiness sections from every applicable provider.

    Core providers always contribute; a module provider contributes only when
    its module is enabled. Reading the enabled set enforces registry dependency
    validation, so an invalid ``CMS_ENABLED_MODULES`` raises
    ``ImproperlyConfigured`` here just as it does elsewhere. Section order
    follows provider registration order.
    """
    enabled_keys = get_enabled_module_keys()

    sections = []
    for provider in _READINESS_PROVIDERS.values():
        if provider.module_key is not None and provider.module_key not in enabled_keys:
            continue
        sections.extend(provider.build(context))
    return sections
