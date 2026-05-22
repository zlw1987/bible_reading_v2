from django import forms

from .models import MinistryTeam, TeamMembership


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
        "can_lead": "Can Lead",
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
        "can_lead": "可带领",
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


def team_form_text(language):
    return TEAM_FORM_TEXT.get(language, TEAM_FORM_TEXT["en"])


def membership_form_text(language):
    return MEMBERSHIP_FORM_TEXT.get(language, MEMBERSHIP_FORM_TEXT["en"])


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
            "can_lead",
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
