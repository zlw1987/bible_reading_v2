"""Narrow directed-notification delivery port (NOTIFY.1A).

Source modules resolve one recipient and build the bounded payload. Core only
applies the notifications module gate, schedules post-commit delivery, and
invokes the single registered sink. Notification persistence remains owned by
the ``notifications`` app; this module deliberately imports no Notification
model or source-domain model.
"""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
import logging
from types import MappingProxyType
from typing import Any, Mapping, Optional

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils.http import url_has_allowed_host_and_scheme

from core.module_registry import is_module_enabled


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationPayload:
    """One already-directed notification request.

    ``recipient`` is intentionally an already-resolved user object. Nothing in
    Core or the persistence sink expands it through audience, belonging,
    serving, staff, role, source-object, or target-URL data.
    """

    recipient: Any
    source_module: str
    notification_type: str
    title: str
    body: str
    target_url: str
    dedupe_key: str
    source_model_label: str = ""
    source_object_id: str = ""
    actor: Optional[Any] = None
    severity: str = "info"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.recipient is None:
            raise ValueError("Notification recipient is required.")
        for field_name in (
            "source_module",
            "notification_type",
            "title",
            "target_url",
            "dedupe_key",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"Notification {field_name} is required.")
        if not self.target_url.startswith("/") or not url_has_allowed_host_and_scheme(
            self.target_url,
            allowed_hosts=set(),
        ):
            raise ValueError(
                "Notification target_url must be a relative internal path."
            )
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(deepcopy(dict(self.metadata or {}))),
        )


_notification_sink = None


def register_notification_sink(sink):
    """Register the one notification persistence sink.

    The first registration wins. Re-registering the identical callable is
    harmless for predictable Django app initialization; replacing it with a
    different callable is a configuration/programming error.
    """

    global _notification_sink

    if not callable(sink):
        raise ValueError("Notification sink must be callable.")
    if _notification_sink is None:
        _notification_sink = sink
        return sink
    if _notification_sink is sink:
        return sink
    raise ImproperlyConfigured(
        "A different notification persistence sink is already registered."
    )


@contextmanager
def notification_sink_override_for_tests(sink):
    """Temporarily isolate or replace sink state in focused tests only."""

    global _notification_sink

    if sink is not None and not callable(sink):
        raise ValueError("Notification test sink must be callable or None.")
    previous = _notification_sink
    _notification_sink = sink
    try:
        yield
    finally:
        _notification_sink = previous


def _diagnostic_context(payload):
    return {
        "notification_source_module": payload.source_module,
        "notification_type": payload.notification_type,
        "notification_recipient_id": getattr(payload.recipient, "pk", None),
        "notification_dedupe_key": payload.dedupe_key,
    }


def _deliver_now(payload, *, strict=False):
    """Invoke the registered sink now under strict or contained policy."""

    sink = _notification_sink
    if sink is None:
        error = ImproperlyConfigured(
            "Notifications is enabled but no notification sink is registered."
        )
        if strict:
            raise error
        logger.error(str(error), extra=_diagnostic_context(payload))
        return None

    try:
        return sink(payload)
    except Exception:
        if strict:
            raise
        logger.exception(
            "Notification delivery failed after the source transaction committed.",
            extra=_diagnostic_context(payload),
        )
        return None


def emit_notification(
    *,
    recipient,
    source_module,
    notification_type,
    title,
    body,
    target_url,
    dedupe_key,
    source_model_label="",
    source_object_id="",
    actor=None,
    severity="info",
    metadata=None,
):
    """Schedule one directed notification after the current transaction commits.

    Returns ``False`` when the registered Notifications module is disabled and
    no callback is registered. Returns ``True`` when delivery was scheduled
    (or immediately executed under Django's normal ``on_commit`` behavior when
    no transaction is active).
    """

    if not is_module_enabled("notifications"):
        return False

    payload = NotificationPayload(
        recipient=recipient,
        source_module=source_module,
        notification_type=notification_type,
        title=title,
        body=body,
        target_url=target_url,
        dedupe_key=dedupe_key,
        source_model_label=source_model_label,
        source_object_id=source_object_id,
        actor=actor,
        severity=severity,
        metadata=metadata or {},
    )
    transaction.on_commit(lambda payload=payload: _deliver_now(payload))
    return True
