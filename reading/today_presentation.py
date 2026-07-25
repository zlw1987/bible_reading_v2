"""Pure presentation adapters for the member-facing Today page.

The functions in this module only reshape values already returned by registered
Today providers. They perform no database queries and do not widen visibility,
serving, confirmation, scheduling, or editing permissions.
"""

from django.urls import reverse


SECONDARY_READING_CAP = 3
ATTENTION_CAP = 6


def _primary_sort_key(entry):
    index, item = entry
    if not item.get("has_configured_days", True):
        tier = 3
    elif item["is_reading_day"] and not item["is_checked"]:
        tier = 0
    elif item["is_reading_day"] and item["is_checked"]:
        tier = 1
    else:
        # Rest day (the only remaining in-progress state).
        tier = 2
    return (tier, index)


def _compact_from_today_item(item):
    if not item.get("has_configured_days", True):
        status_kind = "not_configured"
    elif item["is_rest_day"]:
        status_kind = "rest"
    elif item["is_checked"]:
        status_kind = "checked"
    else:
        status_kind = "not_checked"
    return {
        "active_plan": item["active_plan"],
        "current_day_number": item["current_day_number"],
        "checked_days": item["checked_days"],
        "total_reading_days": item["total_reading_days"],
        "progress_percent": item["progress_percent"],
        "status_kind": status_kind,
    }


def _compact_from_other_item(item):
    status_kind = (
        "not_configured"
        if not item.get("has_configured_days", True)
        else "not_started"
    )
    return {
        "active_plan": item["active_plan"],
        "current_day_number": item["current_day_number"],
        "checked_days": item["checked_days"],
        "total_reading_days": item["total_reading_days"],
        "progress_percent": item["progress_percent"],
        "status_kind": status_kind,
    }


def build_reading_presentation(context):
    """Return ``{"primary_reading", "secondary_reading_items"}`` for the home page.

    ``primary_reading`` is the full hero item (or ``None``). Secondary rows are
    only returned when a hero exists; otherwise the home template's existing
    no-hero empty state applies.
    """
    today_items = list(context.get("today_items") or [])
    other_plan_items = list(context.get("other_plan_items") or [])

    upcoming_items = [item for item in other_plan_items if item["is_not_started"]]
    nearest_upcoming = (
        min(upcoming_items, key=lambda item: item["active_plan"].start_date)
        if upcoming_items
        else None
    )
    if not today_items:
        return {
            "primary_reading": None,
            "upcoming_reading": (
                _compact_from_other_item(nearest_upcoming)
                if nearest_upcoming is not None
                else None
            ),
            "secondary_reading_items": [],
            "secondary_reading_remaining_count": 0,
        }

    ordered = sorted(enumerate(today_items), key=_primary_sort_key)
    primary_index, primary_item = ordered[0]

    in_progress_secondary = [
        _compact_from_today_item(item)
        for index, item in ordered
        if index != primary_index
    ]
    secondary_candidates = list(in_progress_secondary)
    if nearest_upcoming is not None:
        secondary_candidates.append(_compact_from_other_item(nearest_upcoming))
    secondary = secondary_candidates[:SECONDARY_READING_CAP]

    return {
        "primary_reading": primary_item,
        "upcoming_reading": None,
        "secondary_reading_items": secondary,
        "secondary_reading_remaining_count": max(
            len(secondary_candidates) - len(secondary),
            0,
        ),
    }


def _copy(language, english, chinese):
    return chinese if language == "zh" else english


def _bible_study_role_labels(roles, language):
    labels = {
        "en": {
            "discussion_leader": "Discussion Leader",
            "worship_lead": "Worship Lead",
            "pianist": "Pianist",
            "support": "Support",
            "host": "Host",
        },
        "zh": {
            "discussion_leader": "查经带领",
            "worship_lead": "敬拜带领",
            "pianist": "伴奏",
            "support": "配搭",
            "host": "接待",
        },
    }
    selected = labels.get(language, labels["en"])
    return " · ".join(
        selected.get(role.role, role.get_role_display())
        for role in roles
    )


def build_attention_presentation(context, language):
    """Normalize every real pending action into one shared row contract."""
    items = []
    serving_summary = context.get("serving_summary")
    if serving_summary and serving_summary.get("is_pending"):
        for serving_item in serving_summary.get("items", []):
            if serving_item["kind"] == "bible_study":
                roles = _bible_study_role_labels(serving_item["roles"], language)
                items.append(
                    {
                        "kind": "bible_study_confirmation",
                        "title": serving_item["meeting"].lesson.get_title(language),
                        "detail": " · ".join(
                            part
                            for part in (
                                _copy(
                                    language,
                                    "Bible Study serving",
                                    "查经服事",
                                ),
                                roles,
                            )
                            if part
                        ),
                        "status_label": _copy(
                            language,
                            "Pending confirmation",
                            "等待确认",
                        ),
                        "status_tone": "warning",
                        "action_label": _copy(
                            language,
                            "Confirm in My Serving",
                            "去「我的服事」确认",
                        ),
                        "action_url": reverse("my_serving"),
                        "when": serving_item["starts_at"],
                    }
                )
            else:
                assignment = serving_item["assignment"]
                items.append(
                    {
                        "kind": "team_confirmation",
                        "title": assignment.service_event.get_title(language),
                        "detail": assignment.ministry_team.get_name(language),
                        "status_label": _copy(
                            language,
                            "Pending confirmation",
                            "等待确认",
                        ),
                        "status_tone": "warning",
                        "action_label": _copy(
                            language,
                            "Confirm in My Serving",
                            "去「我的服事」确认",
                        ),
                        "action_url": reverse("my_serving"),
                        "when": serving_item["starts_at"],
                    }
                )

    leader_summary = context.get("leader_summary")
    if leader_summary:
        for row in leader_summary.get("items", []):
            items.append(
                {
                    "kind": "leader_scheduling_gap",
                    "title": row["event"].get_title(language),
                    "detail": row["team"].get_name(language),
                    "status_label": row["issue_label"],
                    "status_tone": "warning",
                    "action_label": _copy(
                        language,
                        "Review coverage",
                        "查看排班",
                    ),
                    "action_url": row["action_url"],
                    "when": row["event"].start_datetime,
                }
            )

    for activity in context.get("community_activity_creator_attention_items") or []:
        items.append(
            {
                "kind": "community_activity_changes",
                "title": activity.get_title(language),
                "detail": _copy(
                    language,
                    "Community Activity",
                    "群体活动",
                ),
                "status_label": _copy(
                    language,
                    "Changes requested",
                    "需要修改",
                ),
                "status_tone": "warning",
                "action_label": _copy(
                    language,
                    "Edit and resubmit",
                    "修改并重新提交",
                ),
                "action_url": reverse("community_activity_edit", args=[activity.id]),
                "when": activity.start_datetime,
            }
        )
    priority = {
        "team_confirmation": 0,
        "bible_study_confirmation": 0,
        "leader_scheduling_gap": 1,
        "community_activity_changes": 2,
    }
    return [
        item
        for _, item in sorted(
            enumerate(items),
            key=lambda entry: (
                priority[entry[1]["kind"]],
                entry[1]["when"] is None,
                entry[1]["when"].isoformat() if entry[1]["when"] else "",
                entry[0],
            ),
        )
    ]


def _attention_workspace_links(items, language):
    """Return one clear owner-workspace route per represented action kind."""
    links = []
    kinds = {item["kind"] for item in items}
    has_confirmation = bool(
        kinds & {"team_confirmation", "bible_study_confirmation"}
    )
    has_leader_attention = "leader_scheduling_gap" in kinds
    if has_confirmation or has_leader_attention:
        if has_confirmation:
            label = _copy(
                language,
                "Open My Serving",
                "打开「我的服事」",
            )
        else:
            label = _copy(
                language,
                "Review leader attention",
                "查看组长待处理",
            )
        links.append(
            {
                "label": label,
                "url": (
                    f"{reverse('my_serving')}#leader-needs-attention"
                    if has_leader_attention
                    else reverse("my_serving")
                ),
            }
        )
    if "community_activity_changes" in kinds:
        links.append(
            {
                "label": _copy(
                    language,
                    "Open Community Activities",
                    "打开「群体活动」",
                ),
                "url": reverse("community_activity_list"),
            }
        )
    return links


def _provider_hidden_attention_count(context):
    """Count provider-owned actions intentionally summarized before Today."""
    hidden_count = 0
    serving_summary = context.get("serving_summary")
    if serving_summary and serving_summary.get("is_pending"):
        hidden_count += max(
            serving_summary.get("pending_count", 0)
            - len(serving_summary.get("items", [])),
            0,
        )
    leader_summary = context.get("leader_summary")
    if leader_summary:
        hidden_count += max(
            leader_summary.get("count", 0)
            - len(leader_summary.get("items", [])),
            0,
        )
    return hidden_count


def build_unrepresented_serving_presentation(context, language):
    """Confirmed personal serving not already shown on an agenda occurrence."""
    represented_event_ids = {
        row["event"].id
        for key in ("today_gatherings", "week_gatherings")
        for row in (context.get(key) or [])
    }
    represented_meeting_ids = {
        row["meeting"].id
        for key in ("today_study_meetings", "week_study_meetings")
        for row in (context.get(key) or [])
    }
    items = []
    for serving_item in context.get("personal_serving_items") or []:
        if serving_item["is_pending"]:
            continue
        if serving_item["kind"] == "team":
            assignment = serving_item["assignment"]
            if assignment.service_event_id in represented_event_ids:
                continue
            items.append(
                {
                    "kind": "team_serving",
                    "title": assignment.service_event.get_title(language),
                    "detail": assignment.ministry_team.get_name(language),
                    "status_label": _copy(language, "Confirmed", "已确认"),
                    "status_tone": "good",
                    "action_label": _copy(
                        language,
                        "View in My Serving",
                        "在「我的服事」中查看",
                    ),
                    "action_url": reverse("my_serving"),
                    "when": serving_item["starts_at"],
                }
            )
        else:
            meeting = serving_item["meeting"]
            if meeting.id in represented_meeting_ids:
                continue
            items.append(
                {
                    "kind": "bible_study_serving",
                    "title": meeting.lesson.get_title(language),
                    "detail": _bible_study_role_labels(
                        serving_item["roles"],
                        language,
                    ),
                    "status_label": _copy(language, "Confirmed", "已确认"),
                    "status_tone": "good",
                    "action_label": _copy(
                        language,
                        "View in My Serving",
                        "在「我的服事」中查看",
                    ),
                    "action_url": reverse("my_serving"),
                    "when": serving_item["starts_at"],
                }
            )
    return items


def build_today_presentation(context, language="en"):
    """Aggregate the pure Today view-models at one call site."""
    presentation = {}
    presentation.update(build_reading_presentation(context))
    all_attention_items = build_attention_presentation(
        context,
        language,
    )
    presentation["needs_attention_items"] = all_attention_items[:ATTENTION_CAP]
    presentation["needs_attention_remaining_count"] = (
        max(
            len(all_attention_items) - ATTENTION_CAP,
            0,
        )
        + _provider_hidden_attention_count(context)
    )
    presentation["needs_attention_workspace_links"] = (
        _attention_workspace_links(all_attention_items, language)
    )
    presentation["unrepresented_serving_items"] = (
        build_unrepresented_serving_presentation(context, language)
    )
    return presentation
