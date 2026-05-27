from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import (
    BibleStudyGuide,
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingRole,
    BibleStudyMeetingWorshipSong,
    BibleStudySeries,
    BibleStudySession,
    BibleStudyWorshipSong,
)


FORM_TEXT = {
    "en": {
        "series_title": "Title",
        "series_title_en": "English title",
        "description": "Description",
        "description_en": "English description",
        "is_active": "Active",
        "series": "Series",
        "title": "Title",
        "title_en": "English title",
        "scripture_reference": "Scripture",
        "prestudy_datetime": "Thursday Pre-study",
        "study_datetime": "Friday Bible Study",
        "location": "Location",
        "meeting_link": "Meeting Link",
        "scope_type": "Scope",
        "district": "District",
        "small_group": "Small Group",
        "status": "Status",
        "guide_body": "Study Guide",
        "guide_body_en": "English study guide",
        "discussion_questions": "Discussion Questions",
        "discussion_questions_en": "English discussion questions",
        "prestudy_notes": "Pre-study Notes",
        "prestudy_notes_en": "English pre-study notes",
        "global": "Global",
        "scope_district": "District",
        "scope_small_group": "Small Group",
        "draft": "Draft",
        "published": "Published",
        "completed": "Completed",
        "cancelled": "Cancelled",
        "title_placeholder": "Bible study session title",
        "scripture_placeholder": "John 15:1-17",
        "guide_placeholder": "Guidance for leaders and participants.",
        "questions_placeholder": "One question per line works well.",
        "notes_placeholder": "Notes for Thursday pre-study.",
    },
    "zh": {
        "series_title": "标题",
        "series_title_en": "英文标题",
        "description": "描述",
        "description_en": "英文描述",
        "is_active": "启用",
        "series": "系列",
        "title": "标题",
        "title_en": "英文标题",
        "scripture_reference": "经文",
        "prestudy_datetime": "周四预查",
        "study_datetime": "周五查经",
        "location": "地点",
        "meeting_link": "会议链接",
        "scope_type": "范围",
        "district": "区",
        "small_group": "小组",
        "status": "状态",
        "guide_body": "查经指引",
        "guide_body_en": "英文查经指引",
        "discussion_questions": "讨论问题",
        "discussion_questions_en": "英文讨论问题",
        "prestudy_notes": "预查备注",
        "prestudy_notes_en": "英文预查备注",
        "global": "全教会",
        "scope_district": "区",
        "scope_small_group": "小组",
        "draft": "草稿",
        "published": "已发布",
        "completed": "已完成",
        "cancelled": "已取消",
        "title_placeholder": "查经标题",
        "scripture_placeholder": "约翰福音 15:1-17",
        "guide_placeholder": "给带领者和参与者的查经指引。",
        "questions_placeholder": "可以每行一个讨论问题。",
        "notes_placeholder": "周四预查备注。",
    },
}


def form_text(language):
    return FORM_TEXT.get(language, FORM_TEXT["en"])


WORSHIP_FORM_TEXT = {
    "en": {
        "sort_order": "Order",
        "title": "Song Title",
        "title_en": "English Title",
        "song_key": "Key",
        "youtube_url": "YouTube Link",
        "chord_url": "Chord Link",
        "lyrics_url": "Lyrics Link",
        "note": "Notes",
        "note_en": "English Notes",
        "title_placeholder": "Song title",
        "title_en_placeholder": "Optional English song title",
        "key_placeholder": "C, D, E-flat...",
        "youtube_placeholder": "https://youtube.com/...",
        "chord_placeholder": "Chord sheet link",
        "lyrics_placeholder": "Lyrics link",
        "note_placeholder": "Notes for worship lead or pianist.",
        "note_en_placeholder": "Optional English notes.",
    },
    "zh": {
        "sort_order": "顺序",
        "title": "诗歌名",
        "title_en": "英文诗歌名",
        "song_key": "调",
        "youtube_url": "YouTube 链接",
        "chord_url": "和弦链接",
        "lyrics_url": "歌词链接",
        "note": "备注",
        "note_en": "英文备注",
        "title_placeholder": "诗歌名",
        "title_en_placeholder": "可选英文诗歌名",
        "key_placeholder": "C、D、降E...",
        "youtube_placeholder": "https://youtube.com/...",
        "chord_placeholder": "和弦谱链接",
        "lyrics_placeholder": "歌词链接",
        "note_placeholder": "给主领或司琴的备注。",
        "note_en_placeholder": "可选英文备注。",
    },
}


def worship_form_text(language):
    return WORSHIP_FORM_TEXT.get(language, WORSHIP_FORM_TEXT["en"])


class BibleStudySeriesForm(forms.ModelForm):
    class Meta:
        model = BibleStudySeries
        fields = ["title", "title_en", "description", "description_en", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "description_en": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        text = form_text(language)
        self.fields["title"].label = text["series_title"]
        self.fields["title_en"].label = text["series_title_en"]
        self.fields["description"].label = text["description"]
        self.fields["description_en"].label = text["description_en"]
        self.fields["is_active"].label = text["is_active"]


class BibleStudySessionForm(forms.ModelForm):
    class Meta:
        model = BibleStudySession
        fields = [
            "series",
            "title",
            "title_en",
            "scripture_reference",
            "prestudy_datetime",
            "study_datetime",
            "location",
            "meeting_link",
            "scope_type",
            "district",
            "small_group",
            "status",
        ]
        widgets = {
            "prestudy_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "study_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        text = form_text(language)

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

        self.fields["scope_type"].choices = [
            (BibleStudySession.SCOPE_GLOBAL, text["global"]),
            (BibleStudySession.SCOPE_DISTRICT, text["scope_district"]),
            (BibleStudySession.SCOPE_SMALL_GROUP, text["scope_small_group"]),
        ]
        self.fields["status"].choices = [
            (BibleStudySession.STATUS_DRAFT, text["draft"]),
            (BibleStudySession.STATUS_PUBLISHED, text["published"]),
            (BibleStudySession.STATUS_COMPLETED, text["completed"]),
            (BibleStudySession.STATUS_CANCELLED, text["cancelled"]),
        ]
        self.fields["title"].widget.attrs.update(
            {"placeholder": text["title_placeholder"]}
        )
        self.fields["scripture_reference"].widget.attrs.update(
            {"placeholder": text["scripture_placeholder"]}
        )
        self.fields["prestudy_datetime"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["study_datetime"].input_formats = ["%Y-%m-%dT%H:%M"]


LESSON_FORM_TEXT = {
    "en": {
        "series": "Series",
        "title": "Title",
        "title_en": "English title",
        "scripture_reference": "Scripture",
        "lesson_date": "Guide Date",
        "prestudy_datetime": "Thursday Pre-study",
        "pastor_guide_body": "Pastor Guide",
        "pastor_guide_body_en": "English pastor guide",
        "global_discussion_questions": "Church-wide Discussion Questions",
        "global_discussion_questions_en": "English church-wide discussion questions",
        "prestudy_notes": "Pre-study Notes",
        "prestudy_notes_en": "English pre-study notes",
        "status": "Status",
        "draft": "Draft",
        "published": "Published",
        "completed": "Completed",
        "cancelled": "Cancelled",
        "title_placeholder": "Bible study guide title",
        "scripture_placeholder": "John 15:1-17",
        "pastor_guide_placeholder": "Pastor guidance for church-wide preparation.",
        "questions_placeholder": "One question per line works well.",
        "notes_placeholder": "Notes for Thursday pre-study.",
    },
    "zh": {
        "series": "系列",
        "title": "标题",
        "title_en": "英文标题",
        "scripture_reference": "经文",
        "lesson_date": "指引日期",
        "prestudy_datetime": "周四预查",
        "pastor_guide_body": "牧者预查指引",
        "pastor_guide_body_en": "英文牧者预查指引",
        "global_discussion_questions": "全教会讨论问题",
        "global_discussion_questions_en": "英文全教会讨论问题",
        "prestudy_notes": "预查备注",
        "prestudy_notes_en": "英文预查备注",
        "status": "状态",
        "draft": "草稿",
        "published": "已发布",
        "completed": "已完成",
        "cancelled": "已取消",
        "title_placeholder": "查经指引标题",
        "scripture_placeholder": "约翰福音 15:1-17",
        "pastor_guide_placeholder": "给全教会预查和带领的牧者指引。",
        "questions_placeholder": "可以每行一个讨论问题。",
        "notes_placeholder": "周四预查备注。",
    },
}


def lesson_form_text(language):
    return LESSON_FORM_TEXT.get(language, LESSON_FORM_TEXT["en"])


class BibleStudyLessonForm(forms.ModelForm):
    class Meta:
        model = BibleStudyLesson
        fields = [
            "series",
            "title",
            "title_en",
            "scripture_reference",
            "lesson_date",
            "prestudy_datetime",
            "pastor_guide_body",
            "pastor_guide_body_en",
            "global_discussion_questions",
            "global_discussion_questions_en",
            "prestudy_notes",
            "prestudy_notes_en",
            "status",
        ]
        widgets = {
            "lesson_date": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "prestudy_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "pastor_guide_body": forms.Textarea(attrs={"rows": 6}),
            "pastor_guide_body_en": forms.Textarea(attrs={"rows": 6}),
            "global_discussion_questions": forms.Textarea(attrs={"rows": 5}),
            "global_discussion_questions_en": forms.Textarea(attrs={"rows": 5}),
            "prestudy_notes": forms.Textarea(attrs={"rows": 4}),
            "prestudy_notes_en": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        text = lesson_form_text(language)

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

        self.fields["status"].choices = [
            (BibleStudyLesson.STATUS_DRAFT, text["draft"]),
            (BibleStudyLesson.STATUS_PUBLISHED, text["published"]),
            (BibleStudyLesson.STATUS_COMPLETED, text["completed"]),
            (BibleStudyLesson.STATUS_CANCELLED, text["cancelled"]),
        ]
        self.fields["title"].widget.attrs.update(
            {"placeholder": text["title_placeholder"]}
        )
        self.fields["scripture_reference"].widget.attrs.update(
            {"placeholder": text["scripture_placeholder"]}
        )
        self.fields["pastor_guide_body"].widget.attrs.update(
            {"placeholder": text["pastor_guide_placeholder"]}
        )
        self.fields["global_discussion_questions"].widget.attrs.update(
            {"placeholder": text["questions_placeholder"]}
        )
        self.fields["prestudy_notes"].widget.attrs.update(
            {"placeholder": text["notes_placeholder"]}
        )
        self.fields["lesson_date"].input_formats = ["%Y-%m-%d"]
        self.fields["prestudy_datetime"].input_formats = ["%Y-%m-%dT%H:%M"]


MEETING_FORM_TEXT = {
    "en": {
        "lesson": "Bible Study Guide",
        "small_group": "Small Group",
        "meeting_datetime": "Meeting Time",
        "location": "Location",
        "location_en": "English location",
        "meeting_link": "Meeting Link",
        "discussion_leader_user": "Discussion Leader User",
        "discussion_leader_name": "Discussion Leader Name",
        "group_direction": "Group Direction",
        "group_direction_en": "English group direction",
        "group_questions": "Group Discussion Questions",
        "group_questions_en": "English group discussion questions",
        "status": "Status",
        "service_event": "Service Event",
        "draft": "Draft",
        "published": "Published",
        "completed": "Completed",
        "cancelled": "Cancelled",
        "location_placeholder": "Meeting location",
        "leader_placeholder": "Fallback leader name",
        "direction_placeholder": "Direction for this small group meeting.",
        "questions_placeholder": "Questions for this small group.",
    },
    "zh": {
        "lesson": "查经指引",
        "small_group": "小组",
        "meeting_datetime": "聚会时间",
        "location": "地点",
        "location_en": "英文地点",
        "meeting_link": "会议链接",
        "discussion_leader_user": "带领同工",
        "discussion_leader_name": "带领人姓名",
        "group_direction": "小组方向",
        "group_direction_en": "英文小组方向",
        "group_questions": "小组讨论问题",
        "group_questions_en": "英文小组讨论问题",
        "status": "状态",
        "service_event": "聚会事件",
        "draft": "草稿",
        "published": "已发布",
        "completed": "已完成",
        "cancelled": "已取消",
        "location_placeholder": "小组查经聚会地点",
        "leader_placeholder": "备用带领人姓名",
        "direction_placeholder": "这个小组聚会的查经方向。",
        "questions_placeholder": "这个小组的讨论问题。",
    },
}


def meeting_form_text(language):
    return MEETING_FORM_TEXT.get(language, MEETING_FORM_TEXT["en"])


class BibleStudyMeetingForm(forms.ModelForm):
    class Meta:
        model = BibleStudyMeeting
        fields = [
            "lesson",
            "small_group",
            "meeting_datetime",
            "location",
            "location_en",
            "meeting_link",
            "discussion_leader_user",
            "discussion_leader_name",
            "group_direction",
            "group_direction_en",
            "group_questions",
            "group_questions_en",
            "status",
            "service_event",
        ]
        widgets = {
            "meeting_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "group_direction": forms.Textarea(attrs={"rows": 4}),
            "group_direction_en": forms.Textarea(attrs={"rows": 4}),
            "group_questions": forms.Textarea(attrs={"rows": 5}),
            "group_questions_en": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        text = meeting_form_text(language)

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

        self.fields["lesson"].queryset = BibleStudyLesson.objects.select_related(
            "series",
        ).order_by("-lesson_date", "title")
        self.fields["status"].choices = [
            (BibleStudyMeeting.STATUS_DRAFT, text["draft"]),
            (BibleStudyMeeting.STATUS_PUBLISHED, text["published"]),
            (BibleStudyMeeting.STATUS_COMPLETED, text["completed"]),
            (BibleStudyMeeting.STATUS_CANCELLED, text["cancelled"]),
        ]
        self.fields["location"].widget.attrs.update(
            {"placeholder": text["location_placeholder"]}
        )
        self.fields["discussion_leader_name"].widget.attrs.update(
            {"placeholder": text["leader_placeholder"]}
        )
        self.fields["group_direction"].widget.attrs.update(
            {"placeholder": text["direction_placeholder"]}
        )
        self.fields["group_questions"].widget.attrs.update(
            {"placeholder": text["questions_placeholder"]}
        )
        self.fields["meeting_datetime"].input_formats = ["%Y-%m-%dT%H:%M"]


class BibleStudyMeetingPreparationForm(forms.ModelForm):
    class Meta:
        model = BibleStudyMeeting
        fields = [
            "group_direction",
            "group_direction_en",
            "group_questions",
            "group_questions_en",
        ]
        widgets = {
            "group_direction": forms.Textarea(attrs={"rows": 4}),
            "group_direction_en": forms.Textarea(attrs={"rows": 4}),
            "group_questions": forms.Textarea(attrs={"rows": 5}),
            "group_questions_en": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        text = meeting_form_text(language)

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

        self.fields["group_direction"].widget.attrs.update(
            {"placeholder": text["direction_placeholder"]}
        )
        self.fields["group_questions"].widget.attrs.update(
            {"placeholder": text["questions_placeholder"]}
        )


MEETING_ROLE_FORM_TEXT = {
    "en": {
        "role": "Role",
        "user": "User",
        "display_name": "Display Name",
        "notes": "Notes",
        "notes_en": "English Notes",
        "discussion_leader": "Discussion Leader",
        "worship_lead": "Worship Lead",
        "pianist": "Pianist",
        "support": "Support",
        "host": "Host",
        "display_name_placeholder": "Fallback name if no user is selected",
        "notes_placeholder": "Preparation notes for this role.",
        "notes_en_placeholder": "Optional English notes.",
    },
    "zh": {
        "role": "分工",
        "user": "用户",
        "display_name": "显示姓名",
        "notes": "备注",
        "notes_en": "英文备注",
        "discussion_leader": "查经带领",
        "worship_lead": "敬拜带领",
        "pianist": "伴奏",
        "support": "配搭",
        "host": "接待",
        "display_name_placeholder": "未选择用户时显示的姓名",
        "notes_placeholder": "这个分工的预备备注。",
        "notes_en_placeholder": "可选英文备注。",
    },
}


def meeting_role_form_text(language):
    return MEETING_ROLE_FORM_TEXT.get(language, MEETING_ROLE_FORM_TEXT["en"])


class BibleStudyMeetingRoleForm(forms.ModelForm):
    class Meta:
        model = BibleStudyMeetingRole
        fields = [
            "role",
            "user",
            "display_name",
            "notes",
            "notes_en",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
            "notes_en": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, language="en", meeting=None, **kwargs):
        self.meeting = meeting
        super().__init__(*args, **kwargs)
        text = meeting_role_form_text(language)

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

        self.fields["role"].choices = [
            (BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER, text["discussion_leader"]),
            (BibleStudyMeetingRole.ROLE_WORSHIP_LEAD, text["worship_lead"]),
            (BibleStudyMeetingRole.ROLE_PIANIST, text["pianist"]),
            (BibleStudyMeetingRole.ROLE_SUPPORT, text["support"]),
            (BibleStudyMeetingRole.ROLE_HOST, text["host"]),
        ]

        user_model = get_user_model()
        users = user_model.objects.filter(is_active=True)
        if meeting:
            user_filter = Q(profile__small_group=meeting.small_group)
            if self.instance.user_id:
                user_filter |= Q(id=self.instance.user_id)
            users = users.filter(user_filter)
        self.fields["user"].queryset = users.distinct().order_by("username")

        self.fields["display_name"].widget.attrs.update(
            {"placeholder": text["display_name_placeholder"]}
        )
        self.fields["notes"].widget.attrs.update(
            {"placeholder": text["notes_placeholder"]}
        )
        self.fields["notes_en"].widget.attrs.update(
            {"placeholder": text["notes_en_placeholder"]}
        )


MEETING_WORSHIP_FORM_TEXT = {
    "en": {
        "sort_order": "Order",
        "title": "Song Title",
        "title_en": "English Title",
        "song_key": "Key",
        "youtube_url": "YouTube Link",
        "chord_url": "Chord Link",
        "lyrics_url": "Lyrics Link",
        "arrangement_notes": "Arrangement Notes",
        "arrangement_notes_en": "English arrangement notes",
        "worship_lead_user": "Worship Lead",
        "worship_lead_name": "Worship Lead Name",
        "support_notes": "Support Notes",
        "support_notes_en": "English support notes",
        "title_placeholder": "Song title",
        "title_en_placeholder": "Optional English song title",
        "key_placeholder": "C, D, E-flat...",
        "youtube_placeholder": "https://youtube.com/...",
        "chord_placeholder": "Chord sheet link",
        "lyrics_placeholder": "Lyrics link",
        "arrangement_placeholder": "Notes for arrangement or flow.",
        "support_placeholder": "Notes for support coworkers.",
        "lead_placeholder": "Fallback worship lead name",
    },
    "zh": {
        "sort_order": "顺序",
        "title": "诗歌标题",
        "title_en": "英文诗歌标题",
        "song_key": "调",
        "youtube_url": "YouTube 链接",
        "chord_url": "和弦链接",
        "lyrics_url": "歌词链接",
        "arrangement_notes": "编排备注",
        "arrangement_notes_en": "英文编排备注",
        "worship_lead_user": "敬拜带领",
        "worship_lead_name": "敬拜带领姓名",
        "support_notes": "配搭备注",
        "support_notes_en": "英文配搭备注",
        "title_placeholder": "诗歌标题",
        "title_en_placeholder": "可选英文诗歌标题",
        "key_placeholder": "C、D、降E...",
        "youtube_placeholder": "https://youtube.com/...",
        "chord_placeholder": "和弦谱链接",
        "lyrics_placeholder": "歌词链接",
        "arrangement_placeholder": "编排或流程备注。",
        "support_placeholder": "给配搭同工的备注。",
        "lead_placeholder": "备用敬拜带领姓名",
    },
}


def meeting_worship_form_text(language):
    return MEETING_WORSHIP_FORM_TEXT.get(language, MEETING_WORSHIP_FORM_TEXT["en"])


class BibleStudyMeetingWorshipSongForm(forms.ModelForm):
    class Meta:
        model = BibleStudyMeetingWorshipSong
        fields = [
            "sort_order",
            "title",
            "title_en",
            "song_key",
            "youtube_url",
            "chord_url",
            "lyrics_url",
            "arrangement_notes",
            "arrangement_notes_en",
            "worship_lead_user",
            "worship_lead_name",
            "support_notes",
            "support_notes_en",
        ]
        widgets = {
            "arrangement_notes": forms.Textarea(attrs={"rows": 3}),
            "arrangement_notes_en": forms.Textarea(attrs={"rows": 3}),
            "support_notes": forms.Textarea(attrs={"rows": 3}),
            "support_notes_en": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, language="en", meeting=None, **kwargs):
        self.meeting = meeting
        super().__init__(*args, **kwargs)
        text = meeting_worship_form_text(language)

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

        user_model = get_user_model()
        users = user_model.objects.filter(is_active=True)
        if meeting:
            user_filter = Q(profile__small_group=meeting.small_group)
            if self.instance.worship_lead_user_id:
                user_filter |= Q(id=self.instance.worship_lead_user_id)
            users = users.filter(user_filter)
        self.fields["worship_lead_user"].queryset = users.distinct().order_by(
            "username"
        )

        self.fields["title"].widget.attrs.update(
            {"placeholder": text["title_placeholder"]}
        )
        self.fields["title_en"].widget.attrs.update(
            {"placeholder": text["title_en_placeholder"]}
        )
        self.fields["song_key"].widget.attrs.update(
            {"placeholder": text["key_placeholder"]}
        )
        self.fields["youtube_url"].widget.attrs.update(
            {"placeholder": text["youtube_placeholder"]}
        )
        self.fields["chord_url"].widget.attrs.update(
            {"placeholder": text["chord_placeholder"]}
        )
        self.fields["lyrics_url"].widget.attrs.update(
            {"placeholder": text["lyrics_placeholder"]}
        )
        self.fields["arrangement_notes"].widget.attrs.update(
            {"placeholder": text["arrangement_placeholder"]}
        )
        self.fields["support_notes"].widget.attrs.update(
            {"placeholder": text["support_placeholder"]}
        )
        self.fields["worship_lead_name"].widget.attrs.update(
            {"placeholder": text["lead_placeholder"]}
        )

    def clean_sort_order(self):
        sort_order = self.cleaned_data["sort_order"]
        if self.meeting and sort_order:
            duplicate = BibleStudyMeetingWorshipSong.objects.filter(
                meeting=self.meeting,
                sort_order=sort_order,
            )
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise forms.ValidationError(
                    "This meeting already has a worship song with this order."
                )
        return sort_order


class BibleStudyGuideForm(forms.ModelForm):
    class Meta:
        model = BibleStudyGuide
        fields = [
            "guide_body",
            "guide_body_en",
            "discussion_questions",
            "discussion_questions_en",
            "prestudy_notes",
            "prestudy_notes_en",
        ]
        widgets = {
            "guide_body": forms.Textarea(attrs={"rows": 6}),
            "guide_body_en": forms.Textarea(attrs={"rows": 6}),
            "discussion_questions": forms.Textarea(attrs={"rows": 5}),
            "discussion_questions_en": forms.Textarea(attrs={"rows": 5}),
            "prestudy_notes": forms.Textarea(attrs={"rows": 4}),
            "prestudy_notes_en": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        text = form_text(language)

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

        self.fields["guide_body"].widget.attrs.update(
            {"placeholder": text["guide_placeholder"]}
        )
        self.fields["discussion_questions"].widget.attrs.update(
            {"placeholder": text["questions_placeholder"]}
        )
        self.fields["prestudy_notes"].widget.attrs.update(
            {"placeholder": text["notes_placeholder"]}
        )


class BibleStudyWorshipSongForm(forms.ModelForm):
    class Meta:
        model = BibleStudyWorshipSong
        fields = [
            "sort_order",
            "title",
            "title_en",
            "song_key",
            "youtube_url",
            "chord_url",
            "lyrics_url",
            "note",
            "note_en",
        ]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
            "note_en": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        text = worship_form_text(language)

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

        self.fields["title"].widget.attrs.update(
            {"placeholder": text["title_placeholder"]}
        )
        self.fields["title_en"].widget.attrs.update(
            {"placeholder": text["title_en_placeholder"]}
        )
        self.fields["song_key"].widget.attrs.update(
            {"placeholder": text["key_placeholder"]}
        )
        self.fields["youtube_url"].widget.attrs.update(
            {"placeholder": text["youtube_placeholder"]}
        )
        self.fields["chord_url"].widget.attrs.update(
            {"placeholder": text["chord_placeholder"]}
        )
        self.fields["lyrics_url"].widget.attrs.update(
            {"placeholder": text["lyrics_placeholder"]}
        )
        self.fields["note"].widget.attrs.update(
            {"placeholder": text["note_placeholder"]}
        )
        self.fields["note_en"].widget.attrs.update(
            {"placeholder": text["note_en_placeholder"]}
        )
