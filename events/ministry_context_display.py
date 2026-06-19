"""Structure-native host/language ("ministry context") display derivation.

``ServiceEvent.ministry_context`` and ``ServiceEvent.host_language_unit`` are
display-only host/language labels, not audience authority. As the legacy
``MinistryContext`` FK is retired, member/staff UI still needs a safe fallback
when no explicit structure-native display unit is stored. This module derives
that fallback from the event's ``ServiceEventAudienceScope`` rows using
``ChurchStructureUnit.parent`` ancestry.

Source of hierarchy is ``ChurchStructureUnit.parent`` only. It never consults
``District.ministry_context`` or ``SmallGroup.district`` (those legacy parent
links have been cleared) and never changes audience visibility.
"""

from accounts.models import ChurchStructureUnit


def nearest_ministry_context_unit(unit):
    """Return the nearest ``ministry_context`` unit for ``unit``.

    Walks ``ChurchStructureUnit.parent`` upward, including ``unit`` itself. A
    ``ministry_context`` unit resolves to itself; a small-group/district/etc.
    unit resolves up to its first ministry-context ancestor. Returns ``None``
    when no ministry-context ancestor exists (e.g. root/global units or units
    in a branch without a ministry-context node).
    """
    if unit is None:
        return None

    for node in [unit, *reversed(unit.get_ancestors())]:
        if node.unit_type == ChurchStructureUnit.UNIT_MINISTRY_CONTEXT:
            return node
    return None


def derive_ministry_context_units(units):
    """Derive the distinct ministry-context units for a set of audience units.

    ``units`` is an iterable of ``ChurchStructureUnit`` audience rows. Returns a
    list of distinct ministry-context ancestor units (deduplicated by primary
    key) ordered by ``code`` then ``name`` for stable display. Audience units
    with no ministry-context ancestor contribute nothing.
    """
    found = {}
    for unit in units:
        context_unit = nearest_ministry_context_unit(unit)
        if context_unit is not None and context_unit.pk not in found:
            found[context_unit.pk] = context_unit
    return sorted(found.values(), key=lambda unit: (unit.code or "", unit.name or ""))


def ministry_context_unit_label(unit, language):
    """Render a single ministry-context unit as a host/language label."""
    name = unit.display_name(language)
    if unit.code:
        return f"{unit.code} - {name}"
    return name


def multiple_contexts_label(language):
    """Generic label when audience rows span several ministry contexts."""
    return "多个事工/语言范围" if language == "zh" else "Multiple ministry contexts"
