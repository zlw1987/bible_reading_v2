"""Model-free Church Calendar range-provider contract and aggregation.

CHURCH-CALENDAR.1A foundation. This is the calendar counterpart of the Today
provider registry (``core/today_providers.py``), but range-based: each enabled
source module may register exactly one provider that, given the signed-in user
and an aware, half-open local-time range ``[range_start, range_end)``, returns
normalized :class:`CalendarItem` values overlapping that range.

Deliberately explicit and small, like the module and Today registries — not a
plugin-discovery framework, and it must not make source modules import one
another. No database model is defined or queried here. The four real source
providers (ServiceEvent, BibleStudyMeeting, Announcement, CommunityActivity)
and their member-safe visibility adapters are integrated in
CHURCH-CALENDAR.1B, not this slice; the registry is intentionally empty until
then.

MEMBER-SAFE VISIBILITY IS MANDATORY (plan section 6). A registered provider
MUST return only items the signed-in viewer can see under their *ordinary
current audience / belonging* visibility. Staff, superuser, manager, creator,
and co-organizer accounts receive no management bypass on the member calendar.
Providers therefore MUST NOT use manager-bypass helpers such as
``get_visible_service_events``, ``ServiceEvent.can_be_seen_by``,
``can_manage_service_events``, ``BibleStudyMeeting.can_be_seen_by``,
``visible_announcements_for``, ``visible_community_activities_for``, or
``CommunityActivity.can_be_seen_by`` as the final calendar authority. They must
apply the member-safe range adapters added in CHURCH-CALENDAR.1B, which fail
closed for unauthenticated users, absent/ambiguous active primary membership,
zero audience rows, and nonmatching audience.

The aggregator reinforces (never replaces) that contract: it fails closed for
unauthenticated viewers, skips providers of disabled source modules entirely,
and validates each returned item's shape and ownership before the calendar
sorts or groups it. A provider error surfaces (fails closed) rather than
silently degrading to an unfiltered result.

CHURCH-CALENDAR.2A adds a personal ``my_serving`` overlay owned by the
``ministry`` module. Its visibility axis is *explicit personal serving*, not
audience/belonging: an item exists only when the signed-in viewer has an
explicit ``TeamAssignmentMember`` row (current My Serving semantics), and never
from ``ChurchStructureMembership``, audience scopes, event/meeting visibility,
or staff/manager authority. It is read-only "my serving schedule", not a team
or staff scheduling dashboard, and it shows only the viewer's own serving.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Optional

from django.utils import timezone

from core.module_registry import get_enabled_module_keys, get_module

# --- Item taxonomy (plan section 5) -----------------------------------------

ITEM_TYPE_SERVICE_EVENT = "service_event"
ITEM_TYPE_BIBLE_STUDY_MEETING = "bible_study_meeting"
ITEM_TYPE_ANNOUNCEMENT = "announcement"
ITEM_TYPE_COMMUNITY_ACTIVITY = "community_activity"
# CHURCH-CALENDAR.2A: the signed-in viewer's own explicit serving schedule. This
# is a personal, read-only overlay ("my serving"), never a team/staff scheduling
# dashboard. It comes only from explicit personal assignment rows
# (``TeamAssignmentMember``) and is never inferred from membership, audience
# scopes, or event/meeting visibility.
ITEM_TYPE_MY_SERVING = "my_serving"

VALID_ITEM_TYPES = frozenset(
    {
        ITEM_TYPE_SERVICE_EVENT,
        ITEM_TYPE_BIBLE_STUDY_MEETING,
        ITEM_TYPE_ANNOUNCEMENT,
        ITEM_TYPE_COMMUNITY_ACTIVITY,
        ITEM_TYPE_MY_SERVING,
    }
)

# item_type -> (label_en, label_zh). Shared by the type legend and day detail so
# templates never hard-code taxonomy copy.
ITEM_TYPE_LABELS = {
    ITEM_TYPE_SERVICE_EVENT: ("Church Gathering", "教会聚会"),
    ITEM_TYPE_BIBLE_STUDY_MEETING: ("Bible Study", "查经"),
    ITEM_TYPE_COMMUNITY_ACTIVITY: ("Activity", "活动"),
    ITEM_TYPE_MY_SERVING: ("My Serving", "我的服事"),
    ITEM_TYPE_ANNOUNCEMENT: ("Announcement", "公告"),
}

# Stable display order for the legend / grouping (timed types first, then the
# active-communication announcement type).
ITEM_TYPE_ORDER = (
    ITEM_TYPE_SERVICE_EVENT,
    ITEM_TYPE_BIBLE_STUDY_MEETING,
    ITEM_TYPE_COMMUNITY_ACTIVITY,
    ITEM_TYPE_MY_SERVING,
    ITEM_TYPE_ANNOUNCEMENT,
)

# ``timed`` items are true appointments; ``active_window`` items (announcements)
# are active-window communication, not appointments (plan section 5).
DISPLAY_TIMED = "timed"
DISPLAY_ACTIVE_WINDOW = "active_window"
VALID_DISPLAY_MODES = frozenset({DISPLAY_TIMED, DISPLAY_ACTIVE_WINDOW})

# Which source module owns which item_type. Used both to reject registration of
# an unknown source and to enforce provider ownership of returned items, so one
# module can never emit another module's item type.
MODULE_ITEM_TYPES = {
    "events": frozenset({ITEM_TYPE_SERVICE_EVENT}),
    "studies": frozenset({ITEM_TYPE_BIBLE_STUDY_MEETING}),
    "announcements": frozenset({ITEM_TYPE_ANNOUNCEMENT}),
    "community_events": frozenset({ITEM_TYPE_COMMUNITY_ACTIVITY}),
    # CHURCH-CALENDAR.2A: ministry owns the personal serving overlay. Serving is
    # explicit (``TeamAssignmentMember``), so the ministry provider is the only
    # source allowed to emit ``my_serving`` items.
    "ministry": frozenset({ITEM_TYPE_MY_SERVING}),
}


@dataclass(frozen=True)
class CalendarItem:
    """One normalized, presentation-only calendar item.

    No calendar item is stored; providers construct these per request from
    their own member-safe queries. Identity is ``(item_type, source_id)`` and
    must be unique within a single provider's output for a range.
    """

    item_type: str
    source_id: Any
    # Localized, display-ready title chosen by the owning provider.
    title: str
    # Aware start datetime. For active-window announcements this is the window
    # start; for timed items it is the appointment start.
    start: datetime
    # Owning member-facing detail URL (never an edit/management URL).
    detail_url: str
    display_mode: str = DISPLAY_TIMED
    # Optional aware end datetime (multi-day event / activity, or announcement
    # window end). ``None`` means point-in-time or open-ended.
    end: Optional[datetime] = None
    # Optional localized location text.
    location: str = ""

    @property
    def identity(self):
        return (self.item_type, self.source_id)


# ``provide(user, range_start, range_end) -> Iterable[CalendarItem]``.
CalendarProviderCallable = Callable[[Any, datetime, datetime], Iterable[CalendarItem]]


@dataclass(frozen=True)
class CalendarRangeProvider:
    """One source module's registered calendar range contribution."""

    module_key: str
    provide: CalendarProviderCallable


# module_key -> CalendarRangeProvider, in registration order (dicts preserve it).
_RANGE_PROVIDERS = {}


def register_range_provider(module_key, provide):
    """Register ``provide`` as the calendar range provider for a source module.

    ``module_key`` must be a registered CMS module (typo protection) that is a
    known calendar source (``events`` / ``studies`` / ``announcements`` /
    ``community_events``). A non-callable ``provide`` or a duplicate
    registration raises ``ValueError``. Registration alone never enables the
    provider: the aggregator still skips it when its module is disabled.
    """
    get_module(module_key)  # raises KeyError on unregistered keys

    if module_key not in MODULE_ITEM_TYPES:
        raise ValueError(
            f"Module {module_key!r} is not a known Church Calendar source. "
            f"Known sources: {', '.join(sorted(MODULE_ITEM_TYPES))}."
        )

    if not callable(provide):
        raise ValueError(
            f"Calendar range provider for module {module_key!r} must be "
            f"callable, got {type(provide).__name__}."
        )

    if module_key in _RANGE_PROVIDERS:
        raise ValueError(
            f"A calendar range provider is already registered for module "
            f"{module_key!r}."
        )

    _RANGE_PROVIDERS[module_key] = CalendarRangeProvider(
        module_key=module_key,
        provide=provide,
    )


def get_registered_range_providers():
    """Registered providers, in registration order."""
    return tuple(_RANGE_PROVIDERS.values())


def get_registered_range_provider_keys():
    """Module keys with a registered calendar range provider."""
    return tuple(_RANGE_PROVIDERS)


def _validate_range(range_start, range_end):
    if not (timezone.is_aware(range_start) and timezone.is_aware(range_end)):
        raise ValueError("Calendar range bounds must be timezone-aware.")
    if range_start >= range_end:
        raise ValueError(
            "Calendar range must be a non-empty half-open [range_start, "
            "range_end)."
        )


def _validate_item(item, provider):
    """Validate one provider-returned item enough to prevent malformed data."""
    if not isinstance(item, CalendarItem):
        raise ValueError(
            f"Calendar provider for module {provider.module_key!r} returned a "
            f"{type(item).__name__}, expected a CalendarItem."
        )
    if item.item_type not in VALID_ITEM_TYPES:
        raise ValueError(
            f"Calendar item has unknown item_type {item.item_type!r}."
        )
    # Provider ownership: a source module may only emit its own item type(s).
    if item.item_type not in MODULE_ITEM_TYPES[provider.module_key]:
        raise ValueError(
            f"Module {provider.module_key!r} may not emit calendar item type "
            f"{item.item_type!r}."
        )
    if item.source_id in (None, ""):
        raise ValueError("Calendar item is missing a stable source_id.")
    if not timezone.is_aware(item.start):
        raise ValueError("Calendar item start must be timezone-aware.")
    if item.end is not None:
        if not timezone.is_aware(item.end):
            raise ValueError("Calendar item end must be timezone-aware.")
        if item.end < item.start:
            raise ValueError("Calendar item end must not precede its start.")
    if not item.detail_url:
        raise ValueError("Calendar item is missing a detail_url.")
    if item.display_mode not in VALID_DISPLAY_MODES:
        raise ValueError(
            f"Calendar item has unknown display_mode {item.display_mode!r}."
        )


def collect_calendar_items(user, range_start, range_end, *, providers=None):
    """Aggregate validated member-safe calendar items for ``user`` in a range.

    ``range_start`` / ``range_end`` are the aware, half-open local-time bounds.
    Fails closed for unauthenticated viewers (returns an empty list without
    calling any provider), skips providers whose source module is disabled, and
    validates every returned item's shape and ownership before returning.

    ``providers`` defaults to the registered providers; it is an injection seam
    for tests and internal callers and is not part of the public provider API.
    """
    _validate_range(range_start, range_end)

    # Fail closed: there is no ordinary member visibility for an anonymous
    # viewer, so no provider is consulted.
    if user is None or not getattr(user, "is_authenticated", False):
        return []

    if providers is None:
        providers = get_registered_range_providers()

    enabled_keys = get_enabled_module_keys()

    items = []
    for provider in providers:
        # Disabled source modules must not be called or queried.
        if provider.module_key not in enabled_keys:
            continue

        seen_identities = set()
        for item in provider.provide(user, range_start, range_end):
            _validate_item(item, provider)
            if item.identity in seen_identities:
                raise ValueError(
                    f"Calendar provider for module {provider.module_key!r} "
                    f"returned a duplicate item identity {item.identity!r}."
                )
            seen_identities.add(item.identity)
            items.append(item)
    return items
