"""Presentation data for the staff dropdown.

The staff menu remains a navigation surface only. Items preserve their existing
routes and staff-only menu boundary; module-owned links are surface-gated by
their owning module.
"""


def build_staff_navigation_groups(enabled_modules):
    enabled = set(enabled_modules or ())

    groups = [
        {
            "key": "start_help",
            "label_en": "Start & Help",
            "label_zh": "开始与帮助",
            "items": [
                {
                    "label_en": "Staff Overview",
                    "label_zh": "同工总览",
                    "url_name": "staff_overview",
                },
                {
                    "label_en": "Staff User Guide",
                    "label_zh": "同工使用指南",
                    "url_name": "staff_setup_guide",
                },
            ],
        },
        {
            "key": "people_structure",
            "label_en": "People & Structure",
            "label_zh": "人员与结构",
            "items": [
                {
                    "label_en": "User Admin",
                    "label_zh": "用户管理",
                    "url_name": "staff_user_list",
                },
                {
                    "label_en": "Membership Requests",
                    "label_zh": "成员归属申请",
                    "url_name": "staff_membership_request_list",
                },
                {
                    "label_en": "Church Structure Setup & Review",
                    "label_zh": "教会结构设置与检查",
                    "url_name": "staff_structure_map",
                },
                {
                    "label_en": "Ministry Structure",
                    "label_zh": "事工结构",
                    "url_name": "ministry_structure_map",
                    "module": "ministry",
                },
            ],
        },
        {
            "key": "content_communication",
            "label_en": "Content & Communication",
            "label_zh": "内容与沟通",
            "items": [
                {
                    "label_en": "Reading Plan Admin",
                    "label_zh": "读经计划管理",
                    "url_name": "staff_reading_plan_list",
                    "module": "reading",
                },
                {
                    "label_en": "Bible Study Schedules",
                    "label_zh": "查经安排",
                    "url_name": "bible_study_schedule_manage_list",
                    "module": "studies",
                },
                {
                    "label_en": "Weekly Bible Study Guides",
                    "label_zh": "每周查经指引",
                    "url_name": "bible_study_lesson_manage_list",
                    "module": "studies",
                },
                {
                    "label_en": "Small Group Meetings",
                    "label_zh": "小组查经聚会",
                    "url_name": "bible_study_meeting_manage_list",
                    "module": "studies",
                },
                {
                    "label_en": "Announcement Admin",
                    "label_zh": "公告管理",
                    "url_name": "staff_announcement_list",
                    "module": "announcements",
                },
            ],
        },
        {
            "key": "gatherings_serving",
            "label_en": "Gatherings & Serving",
            "label_zh": "聚会与服事",
            "items": [
                {
                    "label_en": "Manage Church Gatherings",
                    "label_zh": "管理教会聚会",
                    "url_name": "service_event_list",
                    "module": "events",
                },
                {
                    "label_en": "Ministry Teams",
                    "label_zh": "事工团队",
                    "url_name": "ministry_team_list",
                    "module": "ministry",
                },
                {
                    "label_en": "Team Assignments",
                    "label_zh": "服事排班",
                    "url_name": "team_assignment_list",
                    "module": "ministry",
                },
            ],
        },
        {
            "key": "review_moderation",
            "label_en": "Review & Moderation",
            "label_zh": "审核与管理",
            "items": [
                {
                    "label_en": "Moderation Queue",
                    "label_zh": "审核队列",
                    "url_name": "staff_moderation_queue",
                },
                {
                    "label_en": "Activity Review",
                    "label_zh": "活动审核",
                    "url_name": "community_activity_review_list",
                    "module": "community_events",
                },
                {
                    "label_en": "Reflection Reports",
                    "label_zh": "默想举报",
                    "url_name": "staff_reflection_reports",
                },
                {
                    "label_en": "Prayer Reports",
                    "label_zh": "代祷举报",
                    "url_name": "staff_prayer_reports",
                    "module": "prayers",
                },
            ],
        },
        {
            "key": "system_admin",
            "label_en": "System Administration",
            "label_zh": "系统后台",
            "items": [
                {
                    "label_en": "Django Admin",
                    "label_zh": "Django 后台",
                    "url_name": "admin:index",
                },
            ],
        },
    ]

    visible_groups = []
    for group in groups:
        visible_items = [
            item
            for item in group["items"]
            if not item.get("module") or item["module"] in enabled
        ]
        if visible_items:
            visible_group = group.copy()
            visible_group["items"] = visible_items
            visible_groups.append(visible_group)

    return visible_groups
