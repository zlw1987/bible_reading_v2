SUPPORTED_LANGUAGES = {
    "zh": "中文",
    "en": "English",
}

DEFAULT_LANGUAGE = "zh"


def normalize_language(language):
    if language in SUPPORTED_LANGUAGES:
        return language

    return DEFAULT_LANGUAGE


def get_user_language(request):
    language = request.GET.get("lang") or request.session.get("language")

    if language:
        return normalize_language(language)

    if request.user.is_authenticated:
        profile = getattr(request.user, "profile", None)
        if profile and profile.preferred_language:
            return normalize_language(profile.preferred_language)

    return DEFAULT_LANGUAGE


def set_user_language(request, language):
    language = normalize_language(language)

    request.session["language"] = language

    if request.user.is_authenticated:
        profile = getattr(request.user, "profile", None)
        if profile:
            profile.preferred_language = language
            profile.save(update_fields=["preferred_language"])

    return language