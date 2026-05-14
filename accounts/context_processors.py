from .language import get_user_language, SUPPORTED_LANGUAGES
from .ui_text import UI_TEXT


def language_context(request):
    language = get_user_language(request)

    other_language = "en" if language == "zh" else "zh"

    return {
        "language": language,
        "language_label": SUPPORTED_LANGUAGES[language],
        "other_language": other_language,
        "other_language_label": SUPPORTED_LANGUAGES[other_language],
        "supported_languages": SUPPORTED_LANGUAGES,
        "ui": UI_TEXT[language],
    }