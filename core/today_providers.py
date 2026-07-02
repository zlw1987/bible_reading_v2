"""Today provider registry and aggregation (MODULAR-CORE.3A).

This is the provider-based Today aggregation foundation described in
``docs/MODULE_BOUNDARIES.md`` (boundary rule 2). Instead of
``reading.views.home`` inlining every module's aggregation, each module
registers one Today provider against its registered module key, and the
home view asks :func:`build_today_context` for the merged context.

Like the module registry, this is deliberately explicit and small — not a
plugin framework. There is no app auto-discovery: providers are registered
by plain module-level calls (currently all from ``reading.views``, which
already owns the Today helpers; moving provider bodies into their module
apps is a follow-up). Aggregation is a surface gate only: a disabled
module's provider is simply not called, and its declared safe defaults
(empty lists / ``None``) are used so ``reading/home.html`` renders without
that module's card, query, or crash. Enablement and dependency validation
come from ``core.module_registry`` (``settings.CMS_ENABLED_MODULES``);
invalid configurations raise ``ImproperlyConfigured`` when the enabled set
is read, exactly as before.

Providers contribute agenda/dashboard context only. The Today / My Serving
boundary is unchanged: personal serving stays explicit
(``TeamAssignmentMember`` / linked-user ``BibleStudyMeetingRole.user``),
and ``ChurchStructureMembership`` (belonging) never implies serving.
"""

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from core.module_registry import get_enabled_module_keys, get_module

# ``provide(request) -> mapping`` of context keys restricted to ``defaults``.
TodayProviderCallable = Callable[[Any], Mapping[str, Any]]


@dataclass(frozen=True)
class TodayProvider:
    """One module's registered Today contribution."""

    module_key: str
    # Callable ``provide(request) -> mapping``; called only when the module is
    # enabled, with keys restricted to ``defaults``.
    provide: TodayProviderCallable
    # Safe per-key fallback values (empty/None) used when the module is
    # disabled, so templates never see a missing key.
    defaults: Mapping[str, Any]


# module_key -> TodayProvider, in registration order (dicts preserve it).
_TODAY_PROVIDERS = {}


def register_today_provider(module_key, provide, *, defaults):
    """Register ``provide`` as the Today provider for a registered module.

    ``defaults`` declares every context key the provider may return, with
    the safe value used when the module is disabled. Keys are exclusive
    across providers so no module can silently overwrite another module's
    Today context. Unregistered module keys raise ``KeyError`` (same typo
    protection as ``is_module_enabled``); a non-callable ``provide`` and
    duplicate or overlapping registrations raise ``ValueError``.
    """
    get_module(module_key)  # raises KeyError on unregistered keys

    if not callable(provide):
        raise ValueError(
            f"Today provider for module {module_key!r} must be callable, got "
            f"{type(provide).__name__}."
        )

    if module_key in _TODAY_PROVIDERS:
        raise ValueError(
            f"A Today provider is already registered for module {module_key!r}."
        )

    if not defaults:
        raise ValueError(
            f"Today provider for module {module_key!r} must declare the "
            "context keys it contributes via non-empty defaults."
        )

    for existing in _TODAY_PROVIDERS.values():
        overlap = sorted(set(defaults) & set(existing.defaults))
        if overlap:
            raise ValueError(
                f"Today provider for module {module_key!r} declares context "
                f"keys already owned by module {existing.module_key!r}: "
                f"{', '.join(overlap)}."
            )

    _TODAY_PROVIDERS[module_key] = TodayProvider(
        module_key=module_key,
        provide=provide,
        defaults=dict(defaults),
    )


def get_registered_today_provider_keys():
    """Module keys with a registered Today provider, in registration order."""
    return tuple(_TODAY_PROVIDERS)


def _fresh_defaults(defaults):
    """Copy mutable default values so one request cannot leak into another."""
    return {
        key: value.copy() if isinstance(value, (list, dict, set)) else value
        for key, value in defaults.items()
    }


def build_today_context(request):
    """Merged Today context from every registered provider.

    Every provider's defaults are always present (so templates stay safe no
    matter which modules are off); a provider is called only when its module
    is enabled. Reading the enabled set enforces registry dependency
    validation, so an invalid ``CMS_ENABLED_MODULES`` raises
    ``ImproperlyConfigured`` here just as it does elsewhere.
    """
    enabled_keys = get_enabled_module_keys()

    context = {}
    for provider in _TODAY_PROVIDERS.values():
        context.update(_fresh_defaults(provider.defaults))
        if provider.module_key not in enabled_keys:
            continue

        provided = provider.provide(request)
        unexpected = sorted(set(provided) - set(provider.defaults))
        if unexpected:
            raise ValueError(
                f"Today provider for module {provider.module_key!r} returned "
                f"undeclared context keys: {', '.join(unexpected)}."
            )
        context.update(provided)
    return context
