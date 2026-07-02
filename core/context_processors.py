from .module_registry import get_enabled_module_keys


def module_context(request):
    """Expose CMS module enablement to templates (MODULAR-CORE.1A).

    ``enabled_modules`` is a frozenset of enabled module keys so templates
    can gate module surfaces with ``{% if "prayers" in enabled_modules %}``.
    """
    return {"enabled_modules": get_enabled_module_keys()}
