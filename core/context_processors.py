from .module_registry import (
    get_enabled_module_keys,
    get_enabled_primary_nav_entries,
)


def module_context(request):
    """Expose CMS module enablement to templates (MODULAR-CORE.1A).

    ``enabled_modules`` is a frozenset of enabled module keys so templates
    can gate module surfaces with ``{% if "prayers" in enabled_modules %}``.
    ``enabled_primary_nav_entries`` is the ordered registry metadata for the
    ordinary authenticated-user module links. Core, staff, and account links
    remain outside that list.
    """
    return {
        "enabled_modules": get_enabled_module_keys(),
        "enabled_primary_nav_entries": get_enabled_primary_nav_entries(),
    }
