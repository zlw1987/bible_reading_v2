from django import template

register = template.Library()


@register.filter
def ministry_team_name(team, language):
    if not team:
        return ""
    return team.get_name(language)


@register.filter
def ministry_team_description(team, language):
    if not team:
        return ""
    return team.get_description(language)


@register.filter
def membership_role_label(membership, language):
    labels = {
        "zh": {
            "member": "成员",
            "lead": "组长",
            "coordinator": "协调人",
        },
        "en": {
            "member": "Member",
            "lead": "Lead",
            "coordinator": "Coordinator",
        },
    }
    return labels.get(language, labels["en"]).get(membership.role, membership.role)
