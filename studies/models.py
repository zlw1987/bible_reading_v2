from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from accounts.models import ChurchStructureUnit, District, MinistryContext, SmallGroup
from accounts.permissions import (
    CAP_MANAGE_BIBLE_STUDIES,
    CAP_PUBLISH_BIBLE_STUDY_GUIDES,
    has_capability,
)
from accounts.structure_selectors import (
    resolve_units_to_small_groups as resolve_structure_units_to_small_groups,
)


def resolve_units_to_small_groups(units):
    """Compatibility wrapper for the shared church-structure resolver."""
    return resolve_structure_units_to_small_groups(units)


class BibleStudySeries(models.Model):
    SCOPE_GLOBAL = "global"
    SCOPE_MINISTRY_CONTEXT = "ministry_context"
    SCOPE_DISTRICT = "district"
    SCOPE_SMALL_GROUP = "small_group"

    SCOPE_CHOICES = [
        (SCOPE_GLOBAL, "Global"),
        (SCOPE_MINISTRY_CONTEXT, "Ministry Context"),
        (SCOPE_DISTRICT, "District"),
        (SCOPE_SMALL_GROUP, "Small Group"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    title = models.CharField(max_length=160)
    title_en = models.CharField(max_length=160, blank=True, default="")
    description = models.TextField(blank=True, default="")
    description_en = models.TextField(blank=True, default="")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_bible_study_schedules",
    )
    scope_type = models.CharField(
        max_length=32,
        choices=SCOPE_CHOICES,
        default=SCOPE_GLOBAL,
    )
    ministry_context = models.ForeignKey(
        MinistryContext,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bible_study_series",
    )
    district = models.ForeignKey(
        District,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bible_study_schedules",
    )
    small_group = models.ForeignKey(
        SmallGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bible_study_schedules",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def get_title(self, language="zh"):
        if language == "en" and self.title_en:
            return self.title_en
        return self.title

    def get_description(self, language="zh"):
        if language == "en" and self.description_en:
            return self.description_en or self.description
        return self.description

    @property
    def is_published(self):
        return self.status in {self.STATUS_PUBLISHED, self.STATUS_COMPLETED}

    def clean(self):
        errors = {}

        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "End date cannot be before start date."

        if self.status not in {
            self.STATUS_DRAFT,
            self.STATUS_PUBLISHED,
            self.STATUS_COMPLETED,
            self.STATUS_CANCELLED,
        }:
            errors["status"] = "Invalid Bible study schedule status."

        if self.scope_type == self.SCOPE_GLOBAL:
            if self.ministry_context_id:
                errors["ministry_context"] = (
                    "Whole-church schedules cannot be scoped to a ministry context."
                )
            if self.district_id:
                errors["district"] = "Whole-church schedules cannot be scoped to a district."
            if self.small_group_id:
                errors["small_group"] = "Whole-church schedules cannot be scoped to a small group."
        elif self.scope_type == self.SCOPE_MINISTRY_CONTEXT:
            if not self.ministry_context_id:
                errors["ministry_context"] = (
                    "Ministry-context-scoped schedules require a ministry context."
                )
            if self.district_id:
                errors["district"] = (
                    "Ministry-context-scoped schedules cannot also use a district."
                )
            if self.small_group_id:
                errors["small_group"] = (
                    "Ministry-context-scoped schedules cannot also use a small group."
                )
        elif self.scope_type == self.SCOPE_DISTRICT:
            if not self.district_id:
                errors["district"] = "District-scoped schedules require a district."
            if self.ministry_context_id:
                errors["ministry_context"] = (
                    "District-scoped schedules cannot also use a ministry context."
                )
            if self.small_group_id:
                errors["small_group"] = "District-scoped schedules cannot also use a small group."
        elif self.scope_type == self.SCOPE_SMALL_GROUP:
            if not self.small_group_id:
                errors["small_group"] = "Small-group-scoped schedules require a small group."
            if self.ministry_context_id:
                errors["ministry_context"] = (
                    "Small-group-scoped schedules cannot also use a ministry context."
                )
            if self.district_id:
                errors["district"] = "Small-group-scoped schedules cannot also use a district."
        else:
            errors["scope_type"] = "Invalid Bible study schedule scope."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_audience_scope_units(self):
        """Return selected ChurchStructureUnit rows for a saved schedule."""
        if not self.pk:
            return ChurchStructureUnit.objects.none()
        return ChurchStructureUnit.objects.filter(
            bible_study_series_audience_scopes__series_id=self.pk,
        ).distinct()

    def apply_audience_legacy_fallback(self, units):
        """Best-effort mirror of selected units into legacy scope fields.

        Audience scope rows (``BibleStudySeriesAudienceScope``) drive runtime
        eligibility. The legacy ``scope_type`` / ``ministry_context`` /
        ``district`` / ``small_group`` fields are kept only as a coexistence
        fallback. A single cleanly mappable unit is represented precisely;
        multi-unit or unmappable selections fall back to the narrowest available
        legacy value so that, if audience rows were ever removed, the legacy
        fallback never silently over-exposes meetings to the whole church.
        """
        units = list(units)
        self.ministry_context = None
        self.district = None
        self.small_group = None

        if not units:
            self.scope_type = self.SCOPE_GLOBAL
            return

        if any(unit.unit_type == ChurchStructureUnit.UNIT_ROOT for unit in units):
            self.scope_type = self.SCOPE_GLOBAL
            return

        if len(units) == 1:
            unit = units[0]
            group = (
                unit.legacy_small_groups.filter(is_active=True).first()
                or unit.legacy_small_groups.first()
            )
            district = unit.legacy_districts.first()
            context = unit.legacy_ministry_contexts.first()
            if group is not None:
                self.scope_type = self.SCOPE_SMALL_GROUP
                self.small_group = group
                return
            if district is not None:
                self.scope_type = self.SCOPE_DISTRICT
                self.district = district
                return
            if context is not None:
                self.scope_type = self.SCOPE_MINISTRY_CONTEXT
                self.ministry_context = context
                return

        # Multi-unit or unmappable single unit: prefer a narrow small-group
        # fallback rather than a broad whole-church one.
        fallback_group = resolve_units_to_small_groups(units).order_by("name").first()
        if fallback_group is not None:
            self.scope_type = self.SCOPE_SMALL_GROUP
            self.small_group = fallback_group
            return

        # Nothing resolves to an active legacy group; audience rows still drive
        # eligibility, so the legacy fallback resolves to no meetings.
        self.scope_type = self.SCOPE_GLOBAL

    def get_eligible_small_groups(self):
        units = list(self.get_audience_scope_units())
        if units:
            return resolve_units_to_small_groups(units)

        groups = SmallGroup.objects.filter(is_active=True)

        if self.scope_type == self.SCOPE_GLOBAL:
            return groups

        if self.scope_type == self.SCOPE_MINISTRY_CONTEXT:
            if not self.ministry_context_id:
                return groups.none()
            return groups.filter(district__ministry_context_id=self.ministry_context_id)

        if self.scope_type == self.SCOPE_DISTRICT:
            if not self.district_id:
                return groups.none()
            return groups.filter(district_id=self.district_id)

        if self.scope_type == self.SCOPE_SMALL_GROUP:
            if not self.small_group_id:
                return groups.none()
            return groups.filter(id=self.small_group_id)

        return groups.none()


class BibleStudySeriesAudienceScope(models.Model):
    """App-specific audience-scope join from a schedule to ChurchStructureUnit.

    Selected units are the BS-AS.1 audience-scope foundation for Bible Study
    Schedule. They resolve to legacy ``SmallGroup`` rows for meeting generation;
    they do not directly grant ordinary-member visibility. Since CS-CORE.2C-B,
    ordinary v2 ``BibleStudyMeeting`` visibility uses active primary
    ``ChurchStructureMembership``. Legacy ``BibleStudySession`` visibility is
    unchanged.
    """

    series = models.ForeignKey(
        BibleStudySeries,
        on_delete=models.CASCADE,
        related_name="audience_scope_links",
    )
    unit = models.ForeignKey(
        ChurchStructureUnit,
        on_delete=models.PROTECT,
        related_name="bible_study_series_audience_scopes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = [
            "series__title",
            "unit__parent_id",
            "unit__sort_order",
            "unit__code",
            "unit__name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["series", "unit"],
                name="unique_bible_study_series_audience_scope",
            )
        ]
        indexes = [
            models.Index(fields=["series"]),
            models.Index(fields=["unit"]),
        ]

    def __str__(self):
        return f"{self.unit} audience scope for {self.series}"

    def clean(self):
        errors = {}

        if self.unit_id and not self.unit.is_active:
            errors["unit"] = "Audience scope must use an active church structure unit."

        if self.series_id and self.unit_id and "unit" not in errors:
            selected_units = ChurchStructureUnit.objects.filter(
                bible_study_series_audience_scopes__series_id=self.series_id,
            )
            if self.pk:
                selected_units = selected_units.exclude(
                    bible_study_series_audience_scopes__pk=self.pk,
                )

            selected_unit_ids = set(selected_units.values_list("id", flat=True))

            if selected_unit_ids and (
                self.unit.unit_type == ChurchStructureUnit.UNIT_ROOT
                or selected_units.filter(
                    unit_type=ChurchStructureUnit.UNIT_ROOT,
                ).exists()
            ):
                errors["unit"] = (
                    "Whole-church audience scope cannot be combined with other "
                    "units for the same schedule."
                )
            else:
                ancestor_ids = {
                    ancestor.id
                    for ancestor in self.unit.get_ancestors()
                    if ancestor.id is not None
                }

                if ancestor_ids & selected_unit_ids:
                    errors["unit"] = (
                        "Audience scope cannot include both an ancestor and "
                        "descendant unit for the same schedule."
                    )
                else:
                    for selected_unit in selected_units:
                        selected_ancestor_ids = {
                            ancestor.id
                            for ancestor in selected_unit.get_ancestors()
                            if ancestor.id is not None
                        }
                        if self.unit_id in selected_ancestor_ids:
                            errors["unit"] = (
                                "Audience scope cannot include both an ancestor "
                                "and descendant unit for the same schedule."
                            )
                            break

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class BibleStudySession(models.Model):
    SCOPE_GLOBAL = "global"
    SCOPE_DISTRICT = "district"
    SCOPE_SMALL_GROUP = "small_group"

    SCOPE_CHOICES = [
        (SCOPE_GLOBAL, "Global"),
        (SCOPE_DISTRICT, "District"),
        (SCOPE_SMALL_GROUP, "Small Group"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    series = models.ForeignKey(
        BibleStudySeries,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    title = models.CharField(max_length=180)
    title_en = models.CharField(max_length=180, blank=True, default="")
    scripture_reference = models.CharField(max_length=180, blank=True, default="")
    prestudy_datetime = models.DateTimeField(null=True, blank=True)
    study_datetime = models.DateTimeField()
    location = models.CharField(max_length=180, blank=True, default="")
    meeting_link = models.URLField(max_length=500, blank=True, default="")
    scope_type = models.CharField(
        max_length=32,
        choices=SCOPE_CHOICES,
        default=SCOPE_GLOBAL,
    )
    district = models.ForeignKey(
        District,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bible_study_sessions",
    )
    small_group = models.ForeignKey(
        SmallGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bible_study_sessions",
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_bible_study_sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-study_datetime"]

    def __str__(self):
        return self.title

    def clean(self):
        errors = {}

        if self.scope_type == self.SCOPE_GLOBAL:
            if self.district_id:
                errors["district"] = "Global sessions cannot be scoped to a district."
            if self.small_group_id:
                errors["small_group"] = "Global sessions cannot be scoped to a small group."
        elif self.scope_type == self.SCOPE_DISTRICT:
            if not self.district_id:
                errors["district"] = "District-scoped sessions require a district."
            if self.small_group_id:
                errors["small_group"] = "District-scoped sessions cannot also use a small group."
        elif self.scope_type == self.SCOPE_SMALL_GROUP:
            if not self.small_group_id:
                errors["small_group"] = "Small-group-scoped sessions require a small group."
            if self.district_id:
                errors["district"] = "Small-group-scoped sessions cannot also use a district."

        if self.status not in {
            self.STATUS_DRAFT,
            self.STATUS_PUBLISHED,
            self.STATUS_COMPLETED,
            self.STATUS_CANCELLED,
        }:
            errors["status"] = "Invalid Bible study session status."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_published(self):
        return self.status in {self.STATUS_PUBLISHED, self.STATUS_COMPLETED}

    def get_title(self, language="zh"):
        if language == "en" and self.title_en:
            return self.title_en
        return self.title

    def can_be_seen_by(self, user):
        if not getattr(user, "is_authenticated", False):
            return False

        if (
            getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
            or has_capability(user, CAP_MANAGE_BIBLE_STUDIES)
            or has_capability(user, CAP_PUBLISH_BIBLE_STUDY_GUIDES)
        ):
            return True

        if self.status == self.STATUS_CANCELLED:
            return False

        if not self.is_published:
            return False

        if self.scope_type == self.SCOPE_GLOBAL:
            return True

        profile = getattr(user, "profile", None)
        user_group = getattr(profile, "small_group", None)
        if not user_group:
            return False

        if self.scope_type == self.SCOPE_DISTRICT:
            return bool(
                self.district_id
                and user_group.district_id
                and self.district_id == user_group.district_id
            )

        if self.scope_type == self.SCOPE_SMALL_GROUP:
            return bool(self.small_group_id and self.small_group_id == user_group.id)

        return False


class BibleStudyLesson(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    series = models.ForeignKey(
        BibleStudySeries,
        on_delete=models.CASCADE,
        related_name="lessons",
    )
    title = models.CharField(max_length=180)
    title_en = models.CharField(max_length=180, blank=True, default="")
    scripture_reference = models.CharField(max_length=180, blank=True, default="")
    lesson_date = models.DateField()
    prestudy_datetime = models.DateTimeField(null=True, blank=True)
    pastor_guide_body = models.TextField(blank=True, default="")
    pastor_guide_body_en = models.TextField(blank=True, default="")
    global_discussion_questions = models.TextField(blank=True, default="")
    global_discussion_questions_en = models.TextField(blank=True, default="")
    prestudy_notes = models.TextField(blank=True, default="")
    prestudy_notes_en = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_bible_study_lessons",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-lesson_date", "-prestudy_datetime"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_published(self):
        return self.status in {self.STATUS_PUBLISHED, self.STATUS_COMPLETED}

    def get_title(self, language="zh"):
        if language == "en" and self.title_en:
            return self.title_en
        return self.title

    def get_pastor_guide_body(self, language="zh"):
        if language == "en":
            return self.pastor_guide_body_en or self.pastor_guide_body
        return self.pastor_guide_body

    def get_global_discussion_questions(self, language="zh"):
        if language == "en":
            return (
                self.global_discussion_questions_en
                or self.global_discussion_questions
            )
        return self.global_discussion_questions

    def get_prestudy_notes(self, language="zh"):
        if language == "en":
            return self.prestudy_notes_en or self.prestudy_notes
        return self.prestudy_notes


class BibleStudyMeeting(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    # BS-STRUCT.1B rotation/replacement readiness marker. Inert in this slice:
    # no generation, visibility, or rotation logic reads it yet. It exists so a
    # future rotation engine can tell a normal group week from a higher-level /
    # joint / cancelled-replacement week without re-deriving it.
    KIND_NORMAL = "normal"
    KIND_HIGHER_LEVEL = "higher_level"
    KIND_JOINT = "joint"
    KIND_CANCELLED_REPLACEMENT = "cancelled_replacement"

    KIND_CHOICES = [
        (KIND_NORMAL, "Normal group meeting"),
        (KIND_HIGHER_LEVEL, "Higher-level meeting"),
        (KIND_JOINT, "Multi-unit joint meeting"),
        (KIND_CANCELLED_REPLACEMENT, "Cancelled / replacement week"),
    ]

    lesson = models.ForeignKey(
        BibleStudyLesson,
        on_delete=models.CASCADE,
        related_name="meetings",
    )
    # BS-STRUCT.1B: legacy SmallGroup becomes a temporary compatibility mirror,
    # not the audience source of truth. It is now nullable so higher-level and
    # multi-unit joint meetings (which map to no single leaf group) are
    # representable, and SET_NULL so retiring a legacy group never deletes a
    # meeting. Normal group-level meetings still set it.
    small_group = models.ForeignKey(
        SmallGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bible_study_meetings",
    )
    # BS-STRUCT.1B: optional primary organizational unit for
    # display/grouping/ownership. Not a visibility source; no runtime reads it
    # for visibility in this slice.
    anchor_unit = models.ForeignKey(
        ChurchStructureUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anchored_bible_study_meetings",
    )
    # BS-STRUCT.1B: future generation idempotency key. Nullable; multiple null
    # rows are allowed. A conditional unique constraint enforces one meeting per
    # (lesson, generation_key) only when it is set. No runtime depends on it yet.
    generation_key = models.CharField(max_length=120, null=True, blank=True)
    meeting_kind = models.CharField(
        max_length=32,
        choices=KIND_CHOICES,
        default=KIND_NORMAL,
    )
    meeting_datetime = models.DateTimeField()
    location = models.CharField(max_length=180, blank=True, default="")
    location_en = models.CharField(max_length=180, blank=True, default="")
    meeting_link = models.URLField(max_length=500, blank=True, default="")
    discussion_leader_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bible_study_discussion_meetings",
    )
    discussion_leader_name = models.CharField(max_length=160, blank=True, default="")
    group_direction = models.TextField(blank=True, default="")
    group_direction_en = models.TextField(blank=True, default="")
    group_questions = models.TextField(blank=True, default="")
    group_questions_en = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    service_event = models.ForeignKey(
        "events.ServiceEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bible_study_meetings",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_bible_study_meetings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-meeting_datetime"]
        constraints = [
            # Existing duplicate protection for normal group-level meetings.
            # Now conditional on a non-null small_group so multiple
            # higher-level / joint meetings (small_group is null) for one lesson
            # are not blocked, while two meetings for the same (lesson, group)
            # are still rejected.
            models.UniqueConstraint(
                fields=["lesson", "small_group"],
                condition=models.Q(small_group__isnull=False),
                name="unique_bible_study_meeting_lesson_group",
            ),
            # BS-STRUCT.1B future identity key for joint/higher-level meetings
            # that have no single small_group. Only enforced when set; multiple
            # null generation_key rows for one lesson are allowed.
            models.UniqueConstraint(
                fields=["lesson", "generation_key"],
                condition=models.Q(generation_key__isnull=False),
                name="unique_bible_study_meeting_lesson_generation_key",
            ),
        ]

    def __str__(self):
        return f"{self.lesson} - {self.small_group}"

    def clean(self):
        super().clean()
        # BS-STRUCT.1B-FU1: treat a blank/whitespace-only generation_key as
        # unset (None) so it is excluded from the conditional
        # (lesson, generation_key) unique constraint rather than colliding as a
        # set "" value. Non-empty keys are stripped. This runs before
        # validate_constraints() inside full_clean(), so the normalized value is
        # what the constraint sees and what is persisted.
        if self.generation_key is not None:
            self.generation_key = self.generation_key.strip() or None

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_audience_scope_units(self):
        """Return selected ChurchStructureUnit rows for a saved meeting.

        BibleStudyMeetingAudienceScope rows are the V2 runtime source of truth
        for ordinary-member visibility. V2 landing/Today and role/worship
        candidate pickers also read these rows. Zero-row V2 meetings fail closed
        for ordinary users; legacy ``small_group`` remains mirror/display/
        backfill/history/idempotency compatibility only.
        """
        if not self.pk:
            return ChurchStructureUnit.objects.none()
        return ChurchStructureUnit.objects.filter(
            bible_study_meeting_audience_scopes__meeting_id=self.pk,
        ).distinct()

    @property
    def is_published(self):
        return self.status in {self.STATUS_PUBLISHED, self.STATUS_COMPLETED}

    def get_location(self, language="zh"):
        if language == "en" and self.location_en:
            return self.location_en
        return self.location

    def get_group_direction(self, language="zh"):
        if language == "en":
            return self.group_direction_en or self.group_direction
        return self.group_direction

    def get_group_questions(self, language="zh"):
        if language == "en":
            return self.group_questions_en or self.group_questions
        return self.group_questions

    def can_be_seen_by(self, user):
        from .visibility import (
            meeting_has_audience_scope_rows,
            meeting_is_member_visible,
            user_has_bible_study_manager_override,
            user_matches_meeting_audience_scopes,
        )

        if not getattr(user, "is_authenticated", False):
            return False

        if user_has_bible_study_manager_override(user):
            return True

        if not meeting_is_member_visible(self):
            return False

        # BS-STRUCT.2A: audience-scope rows are the V2 runtime source of truth.
        # Zero-row meetings fail closed for ordinary users; legacy small_group
        # remains mirror/display/backfill context only.
        if meeting_has_audience_scope_rows(self):
            return user_matches_meeting_audience_scopes(user, self)

        return False


class BibleStudyMeetingAudienceScope(models.Model):
    """App-specific audience-scope join from a meeting to ChurchStructureUnit.

    Selected units are the structure-native meeting audience (single group,
    district, CM/EM, or multi-unit joint such as Singles + Campus), replacing
    the single legacy ``BibleStudyMeeting.small_group`` FK as the audience
    source. Since BS-STRUCT.1D generation writes a row for each newly generated
    normal group-level meeting, and since BS-STRUCT.1E ordinary-member
    visibility, the V2 landing/Today read path, and role / worship pickers read
    these rows. Zero-row V2 meetings fail closed for ordinary users; legacy
    ``small_group`` remains mirror/display/backfill context only. Validation
    mirrors ``BibleStudySeriesAudienceScope``.
    """

    meeting = models.ForeignKey(
        BibleStudyMeeting,
        on_delete=models.CASCADE,
        related_name="audience_scope_links",
    )
    unit = models.ForeignKey(
        ChurchStructureUnit,
        on_delete=models.PROTECT,
        related_name="bible_study_meeting_audience_scopes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = [
            "meeting__meeting_datetime",
            "unit__parent_id",
            "unit__sort_order",
            "unit__code",
            "unit__name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["meeting", "unit"],
                name="unique_bible_study_meeting_audience_scope",
            )
        ]
        indexes = [
            models.Index(fields=["meeting"]),
            models.Index(fields=["unit"]),
        ]

    def __str__(self):
        return f"{self.unit} audience scope for {self.meeting}"

    def clean(self):
        errors = {}

        if self.unit_id and not self.unit.is_active:
            errors["unit"] = "Audience scope must use an active church structure unit."

        if self.meeting_id and self.unit_id and "unit" not in errors:
            selected_units = ChurchStructureUnit.objects.filter(
                bible_study_meeting_audience_scopes__meeting_id=self.meeting_id,
            )
            if self.pk:
                selected_units = selected_units.exclude(
                    bible_study_meeting_audience_scopes__pk=self.pk,
                )

            selected_unit_ids = set(selected_units.values_list("id", flat=True))

            if selected_unit_ids and (
                self.unit.unit_type == ChurchStructureUnit.UNIT_ROOT
                or selected_units.filter(
                    unit_type=ChurchStructureUnit.UNIT_ROOT,
                ).exists()
            ):
                errors["unit"] = (
                    "Whole-church audience scope cannot be combined with other "
                    "units for the same meeting."
                )
            else:
                ancestor_ids = {
                    ancestor.id
                    for ancestor in self.unit.get_ancestors()
                    if ancestor.id is not None
                }

                if ancestor_ids & selected_unit_ids:
                    errors["unit"] = (
                        "Audience scope cannot include both an ancestor and "
                        "descendant unit for the same meeting."
                    )
                else:
                    for selected_unit in selected_units:
                        selected_ancestor_ids = {
                            ancestor.id
                            for ancestor in selected_unit.get_ancestors()
                            if ancestor.id is not None
                        }
                        if self.unit_id in selected_ancestor_ids:
                            errors["unit"] = (
                                "Audience scope cannot include both an ancestor "
                                "and descendant unit for the same meeting."
                            )
                            break

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class BibleStudyMeetingWorshipSong(models.Model):
    meeting = models.ForeignKey(
        BibleStudyMeeting,
        on_delete=models.CASCADE,
        related_name="worship_songs",
    )
    sort_order = models.PositiveIntegerField()
    title = models.CharField(max_length=160)
    title_en = models.CharField(max_length=160, blank=True, default="")
    song_key = models.CharField(max_length=40, blank=True, default="")
    youtube_url = models.URLField(max_length=500, blank=True, default="")
    chord_url = models.URLField(max_length=500, blank=True, default="")
    lyrics_url = models.URLField(max_length=500, blank=True, default="")
    arrangement_notes = models.TextField(blank=True, default="")
    arrangement_notes_en = models.TextField(blank=True, default="")
    worship_lead_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bible_study_worship_songs",
    )
    worship_lead_name = models.CharField(max_length=160, blank=True, default="")
    support_notes = models.TextField(blank=True, default="")
    support_notes_en = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["meeting", "sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["meeting", "sort_order"],
                name="unique_bible_study_meeting_song_order",
            )
        ]

    def __str__(self):
        return self.title

    def clean(self):
        errors = {}

        if not self.title:
            errors["title"] = "Song title is required."

        if self.sort_order is not None and self.sort_order < 1:
            errors["sort_order"] = "Sort order must be positive."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_title(self, language="zh"):
        if language == "en" and self.title_en:
            return self.title_en
        return self.title

    def get_arrangement_notes(self, language="zh"):
        if language == "en":
            return self.arrangement_notes_en or self.arrangement_notes
        return self.arrangement_notes

    def get_support_notes(self, language="zh"):
        if language == "en":
            return self.support_notes_en or self.support_notes
        return self.support_notes


class BibleStudyMeetingRole(models.Model):
    ROLE_DISCUSSION_LEADER = "discussion_leader"
    ROLE_WORSHIP_LEAD = "worship_lead"
    ROLE_PIANIST = "pianist"
    ROLE_SUPPORT = "support"
    ROLE_HOST = "host"

    ROLE_CHOICES = [
        (ROLE_DISCUSSION_LEADER, "Discussion Leader"),
        (ROLE_WORSHIP_LEAD, "Worship Lead"),
        (ROLE_PIANIST, "Pianist"),
        (ROLE_SUPPORT, "Support"),
        (ROLE_HOST, "Host"),
    ]

    meeting = models.ForeignKey(
        BibleStudyMeeting,
        on_delete=models.CASCADE,
        related_name="roles",
    )
    role = models.CharField(max_length=40, choices=ROLE_CHOICES)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bible_study_meeting_roles",
    )
    display_name = models.CharField(max_length=160, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    notes_en = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["meeting", "role", "id"]

    def __str__(self):
        return f"{self.get_role_display()} - {self.get_display_name()}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_notes(self, language="zh"):
        if language == "en":
            return self.notes_en or self.notes
        return self.notes

    def get_display_name(self):
        if self.display_name:
            return self.display_name
        if self.user_id:
            return self.user.get_full_name() or self.user.get_username()
        return ""


class BibleStudyGuide(models.Model):
    session = models.OneToOneField(
        BibleStudySession,
        on_delete=models.CASCADE,
        related_name="guide",
    )
    guide_body = models.TextField(blank=True, default="")
    guide_body_en = models.TextField(blank=True, default="")
    discussion_questions = models.TextField(blank=True, default="")
    discussion_questions_en = models.TextField(blank=True, default="")
    prestudy_notes = models.TextField(blank=True, default="")
    prestudy_notes_en = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Guide for {self.session}"

    def get_guide_body(self, language="zh"):
        if language == "en":
            return self.guide_body_en or self.guide_body
        return self.guide_body

    def get_discussion_questions(self, language="zh"):
        if language == "en":
            return self.discussion_questions_en or self.discussion_questions
        return self.discussion_questions

    def get_prestudy_notes(self, language="zh"):
        if language == "en":
            return self.prestudy_notes_en or self.prestudy_notes
        return self.prestudy_notes


class BibleStudyWorshipSong(models.Model):
    session = models.ForeignKey(
        BibleStudySession,
        on_delete=models.CASCADE,
        related_name="worship_songs",
    )
    sort_order = models.PositiveIntegerField()
    title = models.CharField(max_length=160)
    title_en = models.CharField(max_length=160, blank=True, default="")
    song_key = models.CharField(max_length=40, blank=True, default="")
    youtube_url = models.URLField(max_length=500, blank=True, default="")
    chord_url = models.URLField(max_length=500, blank=True, default="")
    lyrics_url = models.URLField(max_length=500, blank=True, default="")
    note = models.TextField(blank=True, default="")
    note_en = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["session", "sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "sort_order"],
                name="unique_bible_study_worship_song_order",
            )
        ]

    def __str__(self):
        return self.title

    def clean(self):
        errors = {}

        if not self.title:
            errors["title"] = "Song title is required."

        if self.sort_order is not None and self.sort_order < 1:
            errors["sort_order"] = "Sort order must be positive."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_title(self, language="zh"):
        if language == "en" and self.title_en:
            return self.title_en
        return self.title

    def get_note(self, language="zh"):
        if language == "en" and self.note_en:
            return self.note_en
        return self.note
