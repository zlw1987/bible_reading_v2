from .module_registry import (
    get_enabled_module_keys,
    get_enabled_nav_items,
    get_enabled_primary_nav_entries,
)


def module_context(request):
    """Expose CMS module enablement to templates (MODULAR-CORE.1A).

    ``enabled_modules`` is a frozenset of enabled module keys so templates
    can gate module surfaces with ``{% if "prayers" in enabled_modules %}``.
    ``enabled_primary_nav_entries`` is the ordered flat registry metadata for
    the ordinary authenticated-user module links (kept for callers that want
    the flat list). ``enabled_nav_items`` is the grouped top-level nav
    structure (UX-MEMBER-JOURNEY.1A) the header renders. Core, staff, and
    account links remain outside these lists.
    """
    return {
        "enabled_modules": get_enabled_module_keys(),
        "enabled_primary_nav_entries": get_enabled_primary_nav_entries(),
        "enabled_nav_items": get_enabled_nav_items(),
    }
