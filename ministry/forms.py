from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from accounts.ordering import (
    order_team_memberships_by_visible_identity,
    order_users_by_visible_identity,
)
from accounts.structure_selectors import user_matches_structure_audience
from events.models import ServiceEvent

from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleProfile,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamMembership,
)


class ServiceEventChoiceField(forms.ModelChoiceField):
    def __init__(self, *args, language="en", **kwargs):
        self.language = language
        super().__init__(*args, **kwargs)

    def label_from_instance(self, event):
        title = event.get_title(self.language)
        start_time = timezone.localtime(event.start_datetime).strftime("%Y-%m-%d %H:%M")
        parts = [title, start_time]
        if event.location:
            parts.append(event.location)
        return " - ".join(parts)


class TeamMembershipChoiceField(forms.ModelMultipleChoiceField):
    def __init__(self, *args, language="en", **kwargs):
        self.language = language
        super().__init__(*args, **kwargs)

    def label_from_instance(self, membership):
        return membership.get_display_name()


TEAM_FORM_TEXT = {
    "en": {
        "name": "Team Name",
        "name_en": "English Name",
        "description": "Description",
        "description_en": "English Description",
        "email_alias": "Email Alias",
        "playbook_link": "Playbook Link",
        "is_active": "Active",
        "name_placeholder": "Lighting Team",
        "description_placeholder": "Short description of this ministry team.",
        "email_alias_placeholder": "team@example.org",
        "playbook_link_placeholder": "https://...",
    },
    "zh": {
        "name": "团队名称",
        "name_en": "英文名称",
        "description": "描述",
        "description_en": "英文描述",
        "email_alias": "邮件别名",
        "playbook_link": "服事手册链接",
        "is_active": "启用",
        "name_placeholder": "灯光团队",
        "description_placeholder": "简短描述这个事工团队。",
        "email_alias_placeholder": "team@example.org",
        "playbook_link_placeholder": "https://...",
    },
}


MEMBERSHIP_FORM_TEXT = {
    "en": {
        "user": "User",
        "display_name": "Display Name",
        "email": "Email",
        "role": "Role",
        "skill_level": "Skill Level",
        "notes": "Non-sensitive notes",
        "is_active": "Active",
        "member": "Member",
        "lead": "Lead",
        "coordinator": "Coordinator",
        "display_name_placeholder": "Name if no user account exists yet",
        "email_placeholder": "Optional email",
        "skill_level_placeholder": "Optional skill level",
        "notes_placeholder": "Do not store private counseling, prayer, or sensitive personal information here.",
        "notes_help": "Do not store private counseling, prayer, or sensitive personal information here.",
    },
    "zh": {
        "user": "用户",
        "display_name": "显示名称",
        "email": "邮箱",
        "role": "角色",
        "skill_level": "技能等级",
        "notes": "非敏感备注",
        "is_active": "启用",
        "member": "成员",
        "lead": "组长",
        "coordinator": "协调人",
        "display_name_placeholder": "如果还没有账号，请填写姓名",
        "email_placeholder": "可选邮箱",
        "skill_level_placeholder": "可选技能等级",
        "notes_placeholder": "不要在这里记录辅导、代祷或敏感私人信息。",
        "notes_help": "不要在这里记录辅导、代祷或敏感私人信息。",
    },
}


ASSIGNMENT_FORM_TEXT = {
    "en": {
        "service_event": "Service Event",
        "ministry_team": "Ministry Team",
        "assigned_members": "Assigned Members",
        "status": "Status",
        "notes": "Non-sensitive assignment notes",
        "scheduled": "Scheduled",
        "confirmed": "Confirmed",
        "prepared": "Prepared",
        "completed": "Completed",
        "cancelled": "Cancelled",
        "notes_placeholder": "Operational notes for this assignment.",
        "notes_help": "Do not store private counseling, prayer, or sensitive personal information here.",
        "confirmation_note": "Confirmation",
        "confirmation_placeholder": "Optional confirmation note.",
        "confirmation_help": "Do not store private counseling, prayer, or sensitive personal information here.",
        "audience_override_ack": "I understand and still want to assign this person.",
        "audience_override_help": (
            "Only needed when a selected member is outside this event's audience "
            "scope. Assigning them grants read-only serving-context visibility to "
            "this specific event; it does not add them to the audience."
        ),
        "audience_override_warning": (
            "This person is not currently in this event's audience scope. If you "
            "still assign them to serve, they will be able to view this specific "
            "event through My Serving / Calendar / Event detail for serving "
            "purposes."
        ),
    },
    "zh": {
        "service_event": "聚会事件",
        "ministry_team": "事工团队",
        "assigned_members": "已安排成员",
        "status": "状态",
        "notes": "非敏感排班备注",
        "scheduled": "已安排",
        "confirmed": "已确认",
        "prepared": "已准备",
        "completed": "已完成",
        "cancelled": "已取消",
        "notes_placeholder": "本次服事安排的操作备注。",
        "notes_help": "不要在这里记录辅导、代祷或敏感私人信息。",
        "confirmation_note": "确认",
        "confirmation_placeholder": "可选确认备注。",
        "confirmation_help": "不要在这里记录辅导、代祷或敏感私人信息。",
        "audience_override_ack": "我明白，仍要安排这位同工服事。",
        "audience_override_help": (
            "仅当所选成员不在此聚会的适用范围内时才需要勾选。安排后，他将获得对"
            "这场聚会详情的只读服事查看权限，但不会因此被加入适用范围。"
        ),
        "audience_override_warning": (
            "这位同工目前不在此聚会的适用范围内。如果仍然安排他服事，他将可以通过"
            "“我的服事 / 日历 / 聚会详情”查看这场聚会的必要信息，以便完成服事。"
        ),
    },
}


STRUCTURE_FORM_TEXT = {
    "en": {
        "team_kind": "Unit kind",
        "is_assignable": "Assignable (can be a serving assignment target)",
        "role_profile": "Role profile",
        "is_active": "Active",
        "role_profile_empty": "— No role profile —",
        "make_primary": "Set as primary parent",
        "parent_team": "Parent ministry unit",
        "parent_church_unit": "Church anchor",
        "parent_team_empty": "Select a parent ministry unit",
        "parent_church_unit_empty": "Select a church anchor",
    },
    "zh": {
        "team_kind": "单位类型",
        "is_assignable": "可排班（可作为服事安排对象）",
        "role_profile": "角色配置",
        "is_active": "启用",
        "role_profile_empty": "— 不设角色配置 —",
        "make_primary": "设为主要上级",
        "parent_team": "上级事工单位",
        "parent_church_unit": "教会锚点",
        "parent_team_empty": "选择一个上级事工单位",
        "parent_church_unit_empty": "选择一个教会锚点",
    },
}


ROLE_ASSIGNMENT_FORM_TEXT = {
    "en": {
        "role_type": "Ministry role",
        "user": "User",
        "start_date": "Start date",
        "end_date": "End date (optional)",
        "is_active": "Active",
        "notes": "Non-sensitive notes",
        "notes_placeholder": "Operational notes for this long-term role only.",
        "notes_help": (
            "Operational/non-sensitive notes only. Do not store counseling, "
            "pastoral, prayer, medical, financial, or private information."
        ),
    },
    "zh": {
        "role_type": "事工角色",
        "user": "用户",
        "start_date": "开始日期",
        "end_date": "结束日期（可选）",
        "is_active": "启用",
        "notes": "非敏感备注",
        "notes_placeholder": "仅记录此长期角色的操作备注。",
        "notes_help": "仅记录操作性、非敏感的备注。不要记录辅导、牧养、代祷、医疗、财务或私人信息。",
    },
}


def role_assignment_form_text(language):
    return ROLE_ASSIGNMENT_FORM_TEXT.get(language, ROLE_ASSIGNMENT_FORM_TEXT["en"])


def structure_form_text(language):
    return STRUCTURE_FORM_TEXT.get(language, STRUCTURE_FORM_TEXT["en"])


def team_form_text(language):
    return TEAM_FORM_TEXT.get(language, TEAM_FORM_TEXT["en"])


def membership_form_text(language):
    return MEMBERSHIP_FORM_TEXT.get(language, MEMBERSHIP_FORM_TEXT["en"])


def assignment_form_text(language):
    return ASSIGNMENT_FORM_TEXT.get(language, ASSIGNMENT_FORM_TEXT["en"])


class MinistryTeamForm(forms.ModelForm):
    class Meta:
        model = MinistryTeam
        fields = [
            "name",
            "name_en",
            "description",
            "description_en",
            "email_alias",
            "playbook_link",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "description_en": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        text = team_form_text(language)

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

        self.fields["name"].widget.attrs.update(
            {"placeholder": text["name_placeholder"]}
        )
        self.fields["description"].widget.attrs.update(
            {"placeholder": text["description_placeholder"]}
        )
        self.fields["email_alias"].widget.attrs.update(
            {"placeholder": text["email_alias_placeholder"]}
        )
        self.fields["playbook_link"].widget.attrs.update(
            {"placeholder": text["playbook_link_placeholder"]}
        )


class TeamMembershipForm(forms.ModelForm):
    # MINISTRY-ROLE-SOURCE.1D: the normal manage-members form no longer edits
    # ``role`` or ``can_lead``. After the 1C read switch neither field grants any
    # runtime team-management / scheduling permission (that authority is an
    # explicit active lead/coordinator ``MinistryTeamRoleAssignment``), so
    # exposing them here implied a permission source that no longer exists.
    # ``role`` is left off the form entirely: normal creates use the model
    # default (``member``) and existing legacy ``role`` values are preserved
    # untouched on edit. ``can_lead`` was already off the form; keeping it off
    # means a save never sets it True (a malicious ``can_lead=on`` POST is
    # ignored by the ModelForm). Long-term ministry roles are managed through
    # ``MinistryTeamRoleAssignment`` on the staff-only structure setup page.
    class Meta:
        model = TeamMembership
        fields = [
            "user",
            "display_name",
            "email",
            "skill_level",
            "notes",
            "is_active",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, language="en", team=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.team = team
        text = membership_form_text(language)

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

        self.fields["display_name"].widget.attrs.update(
            {"placeholder": text["display_name_placeholder"]}
        )
        self.fields["email"].widget.attrs.update(
            {"placeholder": text["email_placeholder"]}
        )
        self.fields["skill_level"].widget.attrs.update(
            {"placeholder": text["skill_level_placeholder"]}
        )
        self.fields["notes"].widget.attrs.update(
            {"placeholder": text["notes_placeholder"]}
        )
        self.fields["notes"].help_text = text["notes_help"]
        self.fields["user"].queryset = order_users_by_visible_identity(
            self.fields["user"].queryset
        )

    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data.get("user")
        is_active = cleaned_data.get("is_active")
        team = self.team or getattr(self.instance, "team", None)

        if user and team and is_active:
            duplicate_query = TeamMembership.objects.filter(
                team=team,
                user=user,
                is_active=True,
            )
            if self.instance.pk:
                duplicate_query = duplicate_query.exclude(pk=self.instance.pk)
            if duplicate_query.exists():
                self.add_error(
                    "user",
                    "This user already has an active membership in this team.",
                )

        return cleaned_data


class TeamAssignmentForm(forms.ModelForm):
    assigned_members = TeamMembershipChoiceField(
        queryset=TeamMembership.objects.none(),
        required=False,
    )
    service_event = ServiceEventChoiceField(queryset=ServiceEvent.objects.none())
    # SERVING-EVENT-VISIBILITY.1A: non-persistent scheduler acknowledgement for
    # assigning a member outside the event's audience scope. Not a model field, so
    # it is never stored; it only gates the save when an outside-audience member is
    # newly added.
    audience_override_ack = forms.BooleanField(required=False)

    class Meta:
        model = TeamAssignment
        fields = [
            "service_event",
            "ministry_team",
            "assigned_members",
            "status",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(
        self,
        *args,
        language="en",
        manageable_teams=None,
        selected_team_id=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        text = assignment_form_text(language)
        self.manageable_teams = manageable_teams
        self.fields["service_event"].language = language
        base_events = ServiceEvent.objects.select_related(
            "host_language_unit",
        )
        # Assignable operational events only: drop cancelled/draft/past events and
        # ServiceEvents linked from a small-group BibleStudyMeeting. This is a
        # display filter; it does not touch visibility, scope, or required teams.
        assignable_events = (
            base_events.filter(start_datetime__gte=timezone.now())
            .exclude(
                status__in=[
                    ServiceEvent.STATUS_CANCELLED,
                    ServiceEvent.STATUS_DRAFT,
                ]
            )
            .exclude(bible_study_meetings__isnull=False)
        )
        # When editing, keep the currently linked event selectable even if it would
        # otherwise be filtered out, so existing assignments stay viewable/editable.
        if self.instance and self.instance.pk and self.instance.service_event_id:
            assignable_events = assignable_events | base_events.filter(
                pk=self.instance.service_event_id
            )
        self.fields["service_event"].queryset = assignable_events.distinct().order_by(
            "start_datetime",
            "title",
        )
        self.fields["assigned_members"].language = language

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

        self.assignment_form_text = text
        self.fields["audience_override_ack"].help_text = text[
            "audience_override_help"
        ]

        if manageable_teams is not None:
            # MINISTRY-STRUCTURE.1F: new assignments may only target assignable
            # ministry units. When editing an existing assignment, keep its
            # current team selectable even if it became non-assignable so staff
            # can still view/cancel/repair it (the model backstop and clean()
            # below still block moving it onto a *different* non-assignable team
            # or reactivating a cancelled row onto a non-assignable one).
            assignable_teams = manageable_teams.filter(is_assignable=True)
            if (
                self.instance
                and self.instance.pk
                and self.instance.ministry_team_id
            ):
                assignable_teams = MinistryTeam.objects.filter(
                    Q(pk__in=assignable_teams.values("pk"))
                    | Q(pk=self.instance.ministry_team_id)
                ).order_by("name")
            self.fields["ministry_team"].queryset = assignable_teams

        team = None
        if self.is_bound:
            team_id = self.data.get(self.add_prefix("ministry_team"))
            if team_id:
                try:
                    team = MinistryTeam.objects.get(id=team_id)
                except (MinistryTeam.DoesNotExist, ValueError):
                    team = None
        elif selected_team_id:
            try:
                team = self.fields["ministry_team"].queryset.get(id=selected_team_id)
                self.fields["ministry_team"].initial = team
            except (MinistryTeam.DoesNotExist, ValueError):
                team = None
        elif self.instance and self.instance.pk:
            team = self.instance.ministry_team
            self.fields["assigned_members"].initial = self.instance.assigned_members.all()

        member_queryset = TeamMembership.objects.filter(is_active=True).select_related(
            "team",
            "user",
        )
        if self.is_bound and manageable_teams is not None:
            member_queryset = member_queryset.filter(team__in=manageable_teams)
        elif team:
            member_queryset = member_queryset.filter(team=team)
        elif manageable_teams is not None:
            member_queryset = member_queryset.none()
        self.fields["assigned_members"].queryset = (
            order_team_memberships_by_visible_identity(member_queryset)
        )

        self.fields["status"].choices = [
            (TeamAssignment.STATUS_SCHEDULED, text["scheduled"]),
            (TeamAssignment.STATUS_CONFIRMED, text["confirmed"]),
            (TeamAssignment.STATUS_PREPARED, text["prepared"]),
            (TeamAssignment.STATUS_COMPLETED, text["completed"]),
            (TeamAssignment.STATUS_CANCELLED, text["cancelled"]),
        ]
        self.fields["notes"].widget.attrs.update(
            {"placeholder": text["notes_placeholder"]}
        )
        self.fields["notes"].help_text = text["notes_help"]

    def clean(self):
        cleaned_data = super().clean()
        service_event = cleaned_data.get("service_event")
        team = cleaned_data.get("ministry_team")
        status = cleaned_data.get("status")
        assigned_members = cleaned_data.get("assigned_members")

        if team and self.manageable_teams is not None:
            if not self.manageable_teams.filter(id=team.id).exists():
                self.add_error("ministry_team", "You cannot manage assignments for this team.")

        # MINISTRY-STRUCTURE.1F: block editing an existing assignment onto a
        # *different* non-assignable team, or reactivating a previously cancelled
        # assignment onto a non-assignable team. New active assignments are
        # already rejected by TeamAssignment.clean() (model backstop); an
        # unchanged, already-active assignment whose team merely became
        # non-assignable is intentionally left editable so staff can repair or
        # cancel it.
        if (
            team
            and status != TeamAssignment.STATUS_CANCELLED
            and not team.is_assignable
            and self.instance
            and self.instance.pk
        ):
            original_team_id = self.instance.ministry_team_id
            original_status = self.instance.status
            moving_to_different_team = (
                original_team_id is not None and team.id != original_team_id
            )
            reactivating_cancelled = (
                original_status == TeamAssignment.STATUS_CANCELLED
            )
            if moving_to_different_team or reactivating_cancelled:
                self.add_error(
                    "ministry_team", TeamAssignment.NOT_ASSIGNABLE_ERROR
                )

        # Block duplicate active (non-cancelled) assignments for the same
        # ServiceEvent + MinistryTeam. A cancelled submission may always coexist
        # with other rows, and a cancelled historical row never blocks a new
        # active assignment. This is an app-level rule only (no DB constraint).
        if (
            service_event
            and team
            and status != TeamAssignment.STATUS_CANCELLED
        ):
            conflicting = TeamAssignment.objects.filter(
                service_event=service_event,
                ministry_team=team,
            ).exclude(status=TeamAssignment.STATUS_CANCELLED)
            if self.instance and self.instance.pk:
                conflicting = conflicting.exclude(pk=self.instance.pk)
            if conflicting.exists():
                self.add_error(
                    "ministry_team",
                    "An active assignment already exists for this service event "
                    "and team. Cancel or edit the existing assignment instead of "
                    "creating a duplicate.",
                )

        if team and assigned_members:
            invalid_members = [
                membership
                for membership in assigned_members
                if membership.team_id != team.id or not membership.is_active
            ]
            if invalid_members:
                self.add_error(
                    "assigned_members",
                    "Assigned members must be active members of the selected team.",
                )

        # SERVING-EVENT-VISIBILITY.1A (+ FU1): warn + require an explicit
        # acknowledgement when saving would grant a linked-user assigned member
        # read-only serving-context visibility to an event whose *defined* audience
        # scope excludes them. Assigning them never adds them to the audience; it
        # only unlocks read access to that one event detail. Display-name-only
        # (no linked user) members are skipped because there is no account to grant
        # visibility to, and zero-audience events are not nagged (no defined
        # audience to be "outside" of; the read grant still applies).
        #
        # FU1 widens *which* selected members are re-checked so an edit cannot
        # silently grant visibility to a newly reachable event:
        #   * new assignment                              -> check all selected
        #   * existing assignment, ServiceEvent changed   -> check all selected
        #   * existing assignment, reactivated (cancelled->active) -> check all
        #   * otherwise (notes/status/same-event edit)     -> only newly added
        # A submission whose status is cancelled grants no serving visibility, so
        # the acknowledgement is skipped entirely.
        if (
            service_event
            and assigned_members
            and status != TeamAssignment.STATUS_CANCELLED
        ):
            audience_units = list(service_event.get_audience_scope_units())
            if audience_units:
                is_existing = bool(self.instance and self.instance.pk)
                service_event_changed = (
                    is_existing
                    and self.instance.service_event_id != service_event.id
                )
                reactivated_from_cancelled = (
                    is_existing
                    and self.instance.status == TeamAssignment.STATUS_CANCELLED
                )
                check_all_selected = (
                    not is_existing
                    or service_event_changed
                    or reactivated_from_cancelled
                )
                if check_all_selected:
                    already_assigned_ids = set()
                else:
                    already_assigned_ids = set(
                        self.instance.assigned_members.values_list("id", flat=True)
                    )
                outside_members = [
                    membership
                    for membership in assigned_members
                    if membership.id not in already_assigned_ids
                    and membership.user_id
                    and not user_matches_structure_audience(
                        membership.user, audience_units
                    )
                ]
                if outside_members and not cleaned_data.get(
                    "audience_override_ack"
                ):
                    self.outside_audience_members = outside_members
                    self.add_error(
                        "audience_override_ack",
                        self.assignment_form_text["audience_override_warning"],
                    )

        return cleaned_data


class TeamScheduleAssignmentForm(forms.ModelForm):
    assigned_members = TeamMembershipChoiceField(
        queryset=TeamMembership.objects.none(),
        required=False,
    )
    # SERVING-EVENT-VISIBILITY.1B: non-persistent scheduler acknowledgement,
    # mirroring TeamAssignmentForm. This scheduler path can create/update a
    # TeamAssignment and sync its members, so assigning a linked-user member
    # outside the event's audience scope grants that user read-only serving
    # visibility to this one event. Not a model field; it only gates the save.
    audience_override_ack = forms.BooleanField(required=False)

    class Meta:
        model = TeamAssignment
        fields = [
            "assigned_members",
            "status",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(
        self,
        *args,
        language="en",
        team=None,
        suggestion_members=None,
        suggestion_status=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.team = team
        text = assignment_form_text(language)
        self.assignment_form_text = text

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]
        self.fields["audience_override_ack"].help_text = text[
            "audience_override_help"
        ]

        self.fields["assigned_members"].language = language
        self.fields["assigned_members"].queryset = (
            order_team_memberships_by_visible_identity(
                TeamMembership.objects.filter(team=team, is_active=True)
                .select_related("team", "user")
            )
        )
        if self.instance and self.instance.pk:
            self.fields["assigned_members"].initial = (
                self.instance.assigned_members.filter(is_active=True)
            )
        if suggestion_members is not None:
            self.fields["assigned_members"].initial = suggestion_members

        self.fields["status"].choices = [
            (TeamAssignment.STATUS_SCHEDULED, text["scheduled"]),
            (TeamAssignment.STATUS_CONFIRMED, text["confirmed"]),
            (TeamAssignment.STATUS_PREPARED, text["prepared"]),
            (TeamAssignment.STATUS_COMPLETED, text["completed"]),
            (TeamAssignment.STATUS_CANCELLED, text["cancelled"]),
        ]
        if suggestion_status:
            self.fields["status"].initial = suggestion_status
        self.fields["notes"].widget.attrs.update(
            {"placeholder": text["notes_placeholder"]}
        )
        self.fields["notes"].help_text = text["notes_help"]

    def clean(self):
        cleaned_data = super().clean()
        assigned_members = cleaned_data.get("assigned_members")
        status = cleaned_data.get("status")

        if assigned_members:
            invalid_members = [
                membership
                for membership in assigned_members
                if membership.team_id != self.team.id or not membership.is_active
            ]
            if invalid_members:
                self.add_error(
                    "assigned_members",
                    "Assigned members must be active members of the selected team.",
                )

        # SERVING-EVENT-VISIBILITY.1B: mirror the TeamAssignmentForm
        # outside-audience acknowledgement on the scheduler path. The
        # ServiceEvent is fixed by the instance here (it is not an editable
        # field on this form), so there is no "event changed" case to guard;
        # we re-check all selected members on a new assignment or on
        # reactivation (cancelled -> active), otherwise only newly added
        # members. Display-name-only members (no linked user) and
        # zero-audience events are skipped, and a cancelled submission grants
        # no serving visibility so the acknowledgement is not required.
        service_event = (
            self.instance.service_event
            if self.instance.service_event_id
            else None
        )
        if (
            service_event
            and assigned_members
            and status != TeamAssignment.STATUS_CANCELLED
        ):
            audience_units = list(service_event.get_audience_scope_units())
            if audience_units:
                is_existing = bool(self.instance and self.instance.pk)
                reactivated_from_cancelled = (
                    is_existing
                    and self.instance.status == TeamAssignment.STATUS_CANCELLED
                )
                check_all_selected = (
                    not is_existing or reactivated_from_cancelled
                )
                if check_all_selected:
                    already_assigned_ids = set()
                else:
                    already_assigned_ids = set(
                        self.instance.assigned_members.values_list("id", flat=True)
                    )
                outside_members = [
                    membership
                    for membership in assigned_members
                    if membership.id not in already_assigned_ids
                    and membership.user_id
                    and not user_matches_structure_audience(
                        membership.user, audience_units
                    )
                ]
                if outside_members and not cleaned_data.get(
                    "audience_override_ack"
                ):
                    self.outside_audience_members = outside_members
                    self.add_error(
                        "audience_override_ack",
                        self.assignment_form_text["audience_override_warning"],
                    )

        return cleaned_data


class TeamAssignmentConfirmForm(forms.Form):
    confirmation_note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        text = assignment_form_text(language)
        self.fields["confirmation_note"].label = text["confirmation_note"]
        self.fields["confirmation_note"].widget.attrs.update(
            {"placeholder": text["confirmation_placeholder"]}
        )
        self.fields["confirmation_note"].help_text = text["confirmation_help"]


# ---------------------------------------------------------------------------
# MINISTRY-STRUCTURE.1D-A — staff-only ministry-structure setup forms.
#
# These edit ministry-structure *display/organization* metadata and parent
# links only. They never create/update TeamMembership, TeamAssignment,
# TeamAssignmentMember, ChurchStructureMembership, ChurchStructureUnitRoleAssignment,
# or any role assignment, and a parent link (ministry unit or church anchor)
# never grants membership, visibility, serving, or permissions. The views that
# use them are staff/superuser-only.
# ---------------------------------------------------------------------------


class MinistryTeamStructureForm(forms.ModelForm):
    """Edit ministry-structure metadata on an existing ``MinistryTeam``.

    Scope is the structure-display fields only (``team_kind``,
    ``is_assignable``, ``role_profile``, ``is_active``). Name/bilingual fields
    stay on the existing ministry-team edit form. ``role_profile`` lists only
    existing active profiles; this slice seeds/creates none.
    """

    class Meta:
        model = MinistryTeam
        fields = [
            "team_kind",
            "is_assignable",
            "role_profile",
            "is_active",
        ]

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        text = structure_form_text(language)

        # Import locally to avoid any import-order coupling with structure_map.
        from .structure_map import team_kind_options

        self.fields["team_kind"].choices = team_kind_options(language)
        self.fields["role_profile"].queryset = MinistryTeamRoleProfile.objects.filter(
            is_active=True
        ).order_by("sort_order", "code")
        self.fields["role_profile"].empty_label = text["role_profile_empty"]

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]


class _BaseParentLinkForm(forms.Form):
    """Shared add-parent-link behavior. Subclasses declare the parent field.

    Validation defers to ``MinistryTeamParentLink.full_clean()`` (exactly-one
    target, self-parent, cycle, duplicate-active, primary rules) so the UI never
    bypasses model validation. Model errors are mapped back onto the form.
    """

    make_primary = forms.BooleanField(required=False)

    parent_field_name = ""

    def __init__(self, *args, language="en", child_team=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language
        self.child_team = child_team
        text = structure_form_text(language)
        self.fields["make_primary"].label = text["make_primary"]
        self._configure_parent_field(text)

    def _configure_parent_field(self, text):  # pragma: no cover - overridden
        raise NotImplementedError

    def build_link(self):
        """Return an unsaved ``MinistryTeamParentLink`` from cleaned data.

        ``is_primary`` is always ``False`` here; the view promotes the primary
        explicitly so model validation never sees two active primaries at once.
        """
        link = MinistryTeamParentLink(
            child_team=self.child_team,
            is_primary=False,
            is_active=True,
        )
        setattr(
            link,
            self.parent_field_name,
            self.cleaned_data[self.parent_field_name],
        )
        return link

    def apply_model_errors(self, error):
        """Map a model ``ValidationError`` onto this form's fields."""
        message_dict = getattr(error, "message_dict", None)
        if message_dict is None:
            self.add_error(None, error.messages)
            return
        for field, messages in message_dict.items():
            target = field if field == self.parent_field_name else None
            for message in messages:
                self.add_error(target, message)


class MinistryTeamParentTeamLinkForm(_BaseParentLinkForm):
    parent_field_name = "parent_team"

    def _configure_parent_field(self, text):
        queryset = MinistryTeam.objects.filter(is_active=True).order_by("name")
        if self.child_team is not None and self.child_team.pk:
            queryset = queryset.exclude(pk=self.child_team.pk)
        self.fields[self.parent_field_name] = forms.ModelChoiceField(
            queryset=queryset,
            label=text["parent_team"],
            empty_label=text["parent_team_empty"],
        )


class MinistryTeamChurchAnchorLinkForm(_BaseParentLinkForm):
    parent_field_name = "parent_church_unit"

    def _configure_parent_field(self, text):
        self.fields[self.parent_field_name] = forms.ModelChoiceField(
            queryset=ChurchStructureUnit.objects.filter(is_active=True).order_by(
                "code", "name"
            ),
            label=text["parent_church_unit"],
            empty_label=text["parent_church_unit_empty"],
        )


# ---------------------------------------------------------------------------
# MINISTRY-STRUCTURE.1D-B — staff-only ministry role assignment form.
#
# Creates a single explicit long-term ``MinistryTeamRoleAssignment`` row. It is
# additive/readiness setup only: it never creates/updates TeamMembership,
# TeamAssignment, TeamAssignmentMember, ChurchStructureMembership,
# ChurchStructureUnitRoleAssignment, or BibleStudyMeetingRole, never drives
# permissions, and never appears in My Serving. The view that uses it is
# staff/superuser-only. Validation defers to
# ``MinistryTeamRoleAssignment.full_clean()`` (overlapping same user/team/role
# rejection, active team/role/user checks) so the UI never bypasses the model.
# ---------------------------------------------------------------------------


class MinistryRoleTypeChoiceField(forms.ModelChoiceField):
    def __init__(self, *args, language="en", **kwargs):
        self.language = language
        super().__init__(*args, **kwargs)

    def label_from_instance(self, role_type):
        return role_type.display_name(self.language)


class MinistryTeamRoleAssignmentForm(forms.Form):
    role_type = MinistryRoleTypeChoiceField(
        queryset=MinistryTeamRoleType.objects.none(),
    )
    user = forms.ModelChoiceField(queryset=get_user_model().objects.none())
    start_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    is_active = forms.BooleanField(required=False, initial=True)
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, language="en", team=None, **kwargs):
        super().__init__(*args, **kwargs)
        if team is None:
            raise ValueError("MinistryTeamRoleAssignmentForm requires a team.")
        self.team = team
        self.language = language
        text = role_assignment_form_text(language)

        self.fields["role_type"].queryset = MinistryTeamRoleType.objects.filter(
            is_active=True
        ).order_by("sort_order", "code")
        self.fields["role_type"].language = language
        self.fields["user"].queryset = order_users_by_visible_identity(
            get_user_model().objects.filter(is_active=True)
        )

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]
        self.fields["notes"].widget.attrs.update(
            {"placeholder": text["notes_placeholder"]}
        )
        self.fields["notes"].help_text = text["notes_help"]

    def _build_assignment(self):
        return MinistryTeamRoleAssignment(
            team=self.team,
            role_type=self.cleaned_data.get("role_type"),
            user=self.cleaned_data.get("user"),
            is_active=self.cleaned_data.get("is_active", True),
            start_date=self.cleaned_data.get("start_date"),
            end_date=self.cleaned_data.get("end_date"),
            notes=self.cleaned_data.get("notes", ""),
        )

    def clean(self):
        cleaned_data = super().clean()

        # Defer overlap/active validation to the model so the UI never bypasses
        # MinistryTeamRoleAssignment.full_clean(). Map model errors back to form
        # fields when possible, otherwise to the non-field error list.
        assignment = MinistryTeamRoleAssignment(
            team=self.team,
            role_type=cleaned_data.get("role_type"),
            user=cleaned_data.get("user"),
            is_active=cleaned_data.get("is_active", True),
            start_date=cleaned_data.get("start_date"),
            end_date=cleaned_data.get("end_date"),
            notes=cleaned_data.get("notes", ""),
        )
        try:
            assignment.full_clean()
        except forms.ValidationError as error:
            if hasattr(error, "message_dict"):
                for field_name, messages in error.message_dict.items():
                    target = field_name if field_name in self.fields else None
                    for message in messages:
                        self.add_error(target, message)
            else:
                self.add_error(None, error)

        return cleaned_data

    def save(self):
        assignment = self._build_assignment()
        assignment.save()
        return assignment
