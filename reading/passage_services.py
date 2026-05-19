from .bible_sources import parse_memory_verse_text, parse_reading_text
from .models import ReadingPlanDayPassage


def parse_plan_day_passages(plan_day, passage_type):
    if passage_type == ReadingPlanDayPassage.TYPE_MEMORY:
        if not plan_day.memory_verse:
            return []

        return parse_memory_verse_text(plan_day.memory_verse)

    return parse_reading_text(plan_day.reading_text)


def sync_plan_day_passages(plan_day, passage_type=None):
    passage_types = (
        [passage_type]
        if passage_type
        else [
            ReadingPlanDayPassage.TYPE_READING,
            ReadingPlanDayPassage.TYPE_MEMORY,
        ]
    )

    created_count = 0

    for current_type in passage_types:
        parsed_passages = parse_plan_day_passages(plan_day, current_type)

        ReadingPlanDayPassage.objects.filter(
            plan_day=plan_day,
            passage_type=current_type,
        ).delete()

        objects = []

        for index, passage in enumerate(parsed_passages):
            objects.append(
                ReadingPlanDayPassage(
                    plan_day=plan_day,
                    passage_type=current_type,
                    sort_order=index,
                    raw_reference=passage.get("search_text", ""),
                    scripture_ref_key=passage.get("search_text", ""),
                    display_zh=passage.get("display_zh", ""),
                    display_en=passage.get("display_en", ""),
                    text_url_zh=passage.get("text_url_zh", ""),
                    text_url_en=passage.get("text_url_en", ""),
                    audio_url=passage.get("audio_url", ""),
                )
            )

        if objects:
            ReadingPlanDayPassage.objects.bulk_create(objects)
            created_count += len(objects)

    return created_count


def get_plan_day_passages(plan_day, passage_type):
    structured_passages = list(
        ReadingPlanDayPassage.objects
        .filter(
            plan_day=plan_day,
            passage_type=passage_type,
        )
        .order_by("sort_order")
    )

    if structured_passages:
        return [
            structured_passage.as_passage_dict()
            for structured_passage in structured_passages
        ]

    return parse_plan_day_passages(plan_day, passage_type)


def get_reading_passages(plan_day):
    return get_plan_day_passages(
        plan_day,
        ReadingPlanDayPassage.TYPE_READING,
    )


def get_memory_passages(plan_day):
    return get_plan_day_passages(
        plan_day,
        ReadingPlanDayPassage.TYPE_MEMORY,
    )