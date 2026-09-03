"""Explicit opt-in registry for deployment-specific CMS integrations.

Unlike the module registry, deployment integrations are disabled unless a
deployment names them in ``CMS_ENABLED_INTEGRATIONS``. Registry metadata is
static and deliberately contains no adapter modules or callables.
"""

from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .module_registry import get_enabled_module_keys


@dataclass(frozen=True)
class CmsIntegration:
    """Static metadata for one deployment-specific integration."""

    key: str
    required_modules: tuple[str, ...]


class IntegrationDisabled(LookupError):
    """A registered deployment integration is not enabled."""


_REGISTERED_INTEGRATIONS = (
    CmsIntegration(
        key="svca_bethany_2026_worship_xlsx",
        required_modules=("events", "ministry"),
    ),
    CmsIntegration(
        key="svca_lighting_pilot_csv",
        required_modules=("events", "ministry"),
    ),
)

_INTEGRATIONS_BY_KEY = {
    integration.key: integration for integration in _REGISTERED_INTEGRATIONS
}


def get_registered_integrations():
    """All registered integrations, in stable registration order."""

    return _REGISTERED_INTEGRATIONS


def get_registered_integration_keys():
    return tuple(integration.key for integration in _REGISTERED_INTEGRATIONS)


def get_integration(key):
    try:
        return _INTEGRATIONS_BY_KEY[key]
    except KeyError:
        raise KeyError(
            f"Unregistered CMS integration key {key!r}. Registered keys: "
            f"{', '.join(_INTEGRATIONS_BY_KEY)}"
        )


def validate_enabled_integrations(enabled_keys=None):
    """Validate configured integration keys and module dependencies.

    ``None`` means no integrations. This is intentionally different from
    ``validate_enabled_modules(None)``, where ``None`` preserves the historic
    all-modules-enabled behavior.
    """

    enabled = frozenset(() if enabled_keys is None else enabled_keys)
    unknown = sorted(enabled - set(_INTEGRATIONS_BY_KEY))
    if unknown:
        raise ImproperlyConfigured(
            "CMS_ENABLED_INTEGRATIONS contains unregistered integration keys: "
            f"{', '.join(unknown)}. Registered keys: "
            f"{', '.join(_INTEGRATIONS_BY_KEY)}"
        )

    if not enabled:
        return enabled

    enabled_modules = get_enabled_module_keys()
    missing_dependencies = []
    for key in sorted(enabled):
        for module_key in _INTEGRATIONS_BY_KEY[key].required_modules:
            if module_key not in enabled_modules:
                missing_dependencies.append(
                    f"integration {key!r} requires module {module_key!r} "
                    "to be enabled"
                )
    if missing_dependencies:
        raise ImproperlyConfigured(
            "CMS_ENABLED_INTEGRATIONS has unmet module dependencies: "
            f"{'; '.join(missing_dependencies)}."
        )

    return enabled


def get_enabled_integration_keys():
    """Return the current validated enabled keys without configuration cache."""

    configured = getattr(settings, "CMS_ENABLED_INTEGRATIONS", None)
    return validate_enabled_integrations(configured)


def get_enabled_integrations():
    """Enabled integrations, in stable registration order."""

    enabled_keys = get_enabled_integration_keys()
    return tuple(
        integration
        for integration in _REGISTERED_INTEGRATIONS
        if integration.key in enabled_keys
    )


def is_integration_enabled(key):
    """Whether a registered integration is enabled; raise on unknown keys."""

    get_integration(key)
    return key in get_enabled_integration_keys()


def require_integration_enabled(key):
    """Return registered metadata or fail when the integration is disabled."""

    integration = get_integration(key)
    if key not in get_enabled_integration_keys():
        raise IntegrationDisabled(f"CMS integration {key!r} is not enabled.")
    return integration
