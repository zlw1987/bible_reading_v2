"""The single explicit Church Calendar source-provider registration site.

Mirrors the Today registration pattern (``reading.views`` is the one explicit
site for ``core.today_providers``): exactly one place imports each source
module's ``calendar_provider`` module and calls its ``register()`` in a fixed,
deterministic order. There is no app auto-discovery, and the source modules
never import one another — each source ``calendar_provider`` imports only its own
app (plus, for ministry, its declared ``events`` dependency) and the
``church_calendar`` provider contract.

CHURCH-CALENDAR.2A adds the ``ministry`` personal serving overlay provider here;
like every provider it is gated by its own module's enablement at request time.

Registration is independent of module enablement: every provider is registered
here, and :func:`church_calendar.providers.collect_calendar_items` skips the
providers of disabled source modules at request time. Each source ``register()``
is idempotent, so running this at app ``ready()`` is safe.
"""

# Deterministic registration order: events, studies, announcements,
# community_events, then the CHURCH-CALENDAR.2A personal serving overlay
# (ministry). Registration order does not imply enablement; the aggregator still
# skips the ministry provider when the ministry module is disabled.
_SOURCE_PROVIDER_MODULES = (
    "events.calendar_provider",
    "studies.calendar_provider",
    "announcements.calendar_provider",
    "community_events.calendar_provider",
    "ministry.calendar_provider",
)


def register_calendar_source_providers():
    """Import each source calendar provider and register it, in order."""
    from importlib import import_module

    for module_path in _SOURCE_PROVIDER_MODULES:
        import_module(module_path).register()
