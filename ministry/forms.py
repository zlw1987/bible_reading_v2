from django import forms
from django.utils import timezone

from accounts.ordering import (
    order_team_memberships_by_visible_identity,
    order_users_by_visible_identity,
)
from events.models import ServiceEvent

from .models import (
    MinistryTeam,
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
    },
}


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
    class Meta:
        model = TeamMembership
        fields = [
            "user",
            "display_name",
            "email",
            "role",
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

        self.fields["role"].choices = [
            (TeamMembership.ROLE_MEMBER, text["member"]),
            (TeamMembership.ROLE_LEAD, text["lead"]),
            (TeamMembership.ROLE_COORDINATOR, text["coordinator"]),
        ]
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

        if manageable_teams is not None:
            self.fields["ministry_team"].queryset = manageable_teams

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

        return cleaned_data


class TeamScheduleAssignmentForm(forms.ModelForm):
    assigned_members = TeamMembershipChoiceField(
        queryset=TeamMembership.objects.none(),
        required=False,
    )

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

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

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
