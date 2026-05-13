import re
from urllib.parse import quote


BIBLEGATEWAY_VERSION_ZH = "CUVS"
BIBLEGATEWAY_VERSION_EN = "NIV"
BIBLEGATEWAY_VERSION = BIBLEGATEWAY_VERSION_ZH

AUDIO_VERSION = "ccb"


BOOKS_ZH = {
    "创世记": {"search": "Genesis", "audio": "Gen"},
    "创世纪": {"search": "Genesis", "audio": "Gen"},
    "出埃及记": {"search": "Exodus", "audio": "Exod"},
    "利未记": {"search": "Leviticus", "audio": "Lev"},
    "民数记": {"search": "Numbers", "audio": "Num"},
    "申命记": {"search": "Deuteronomy", "audio": "Deut"},
    "约书亚记": {"search": "Joshua", "audio": "Josh"},
    "士师记": {"search": "Judges", "audio": "Judg"},
    "路得记": {"search": "Ruth", "audio": "Ruth"},
    "撒母耳记上": {"search": "1 Samuel", "audio": "1Sam"},
    "撒母耳记下": {"search": "2 Samuel", "audio": "2Sam"},
    "列王纪上": {"search": "1 Kings", "audio": "1Kgs"},
    "列王纪下": {"search": "2 Kings", "audio": "2Kgs"},
    "历代志上": {"search": "1 Chronicles", "audio": "1Chr"},
    "历代志下": {"search": "2 Chronicles", "audio": "2Chr"},
    "以斯拉记": {"search": "Ezra", "audio": "Ezra"},
    "尼希米记": {"search": "Nehemiah", "audio": "Neh"},
    "尼西米记": {"search": "Nehemiah", "audio": "Neh"},
    "以斯帖记": {"search": "Esther", "audio": "Esth"},
    "约伯记": {"search": "Job", "audio": "Job"},
    "诗篇": {"search": "Psalms", "audio": "Ps"},
    "箴言": {"search": "Proverbs", "audio": "Prov"},
    "传道书": {"search": "Ecclesiastes", "audio": "Eccl"},
    "雅歌": {"search": "Song of Songs", "audio": "Song"},
    "以赛亚书": {"search": "Isaiah", "audio": "Isa"},
    "耶利米书": {"search": "Jeremiah", "audio": "Jer"},
    "耶利米哀歌": {"search": "Lamentations", "audio": "Lam"},
    "以西结书": {"search": "Ezekiel", "audio": "Ezek"},
    "但以理书": {"search": "Daniel", "audio": "Dan"},
    "何西阿书": {"search": "Hosea", "audio": "Hos"},
    "约珥书": {"search": "Joel", "audio": "Joel"},
    "阿摩司书": {"search": "Amos", "audio": "Amos"},
    "俄巴底亚书": {"search": "Obadiah", "audio": "Obad"},
    "俄巴底压书": {"search": "Obadiah", "audio": "Obad"},
    "约拿书": {"search": "Jonah", "audio": "Jonah"},
    "弥迦书": {"search": "Micah", "audio": "Mic"},
    "那鸿书": {"search": "Nahum", "audio": "Nah"},
    "哈巴谷书": {"search": "Habakkuk", "audio": "Hab"},
    "西番雅书": {"search": "Zephaniah", "audio": "Zeph"},
    "哈该书": {"search": "Haggai", "audio": "Hag"},
    "撒迦利亚书": {"search": "Zechariah", "audio": "Zech"},
    "玛拉基书": {"search": "Malachi", "audio": "Mal"},

    "马太福音": {"search": "Matthew", "audio": "Matt"},
    "马可福音": {"search": "Mark", "audio": "Mark"},
    "路加福音": {"search": "Luke", "audio": "Luke"},
    "约翰福音": {"search": "John", "audio": "John"},
    "使徒行传": {"search": "Acts", "audio": "Acts"},
    "罗马书": {"search": "Romans", "audio": "Rom"},
    "哥林多前书": {"search": "1 Corinthians", "audio": "1Cor"},
    "哥林多后书": {"search": "2 Corinthians", "audio": "2Cor"},
    "加拉太书": {"search": "Galatians", "audio": "Gal"},
    "以弗所书": {"search": "Ephesians", "audio": "Eph"},
    "腓立比书": {"search": "Philippians", "audio": "Phil"},
    "歌罗西书": {"search": "Colossians", "audio": "Col"},
    "帖撒罗尼迦前书": {"search": "1 Thessalonians", "audio": "1Thess"},
    "帖撒罗尼迦后书": {"search": "2 Thessalonians", "audio": "2Thess"},
    "提摩太前书": {"search": "1 Timothy", "audio": "1Tim"},
    "提摩太后书": {"search": "2 Timothy", "audio": "2Tim"},
    "提多书": {"search": "Titus", "audio": "Titus"},
    "腓利门书": {"search": "Philemon", "audio": "Phlm"},
    "希伯来书": {"search": "Hebrews", "audio": "Heb"},
    "雅各书": {"search": "James", "audio": "Jas"},
    "彼得前书": {"search": "1 Peter", "audio": "1Pet"},
    "彼得后书": {"search": "2 Peter", "audio": "2Pet"},
    "约翰一书": {"search": "1 John", "audio": "1John"},
    "约翰二书": {"search": "2 John", "audio": "2John"},
    "约翰三书": {"search": "3 John", "audio": "3John"},
    "约翰壹书": {"search": "1 John", "audio": "1John"},
    "约翰贰书": {"search": "2 John", "audio": "2John"},
    "约翰参书": {"search": "3 John", "audio": "3John"},
    "犹大书": {"search": "Jude", "audio": "Jude"},
    "启示录": {"search": "Revelation", "audio": "Rev"},
}


BOOKS_EN = {
    "Genesis": {"search": "Genesis", "audio": "Gen"},
    "Exodus": {"search": "Exodus", "audio": "Exod"},
    "Leviticus": {"search": "Leviticus", "audio": "Lev"},
    "Numbers": {"search": "Numbers", "audio": "Num"},
    "Deuteronomy": {"search": "Deuteronomy", "audio": "Deut"},
    "Joshua": {"search": "Joshua", "audio": "Josh"},
    "Judges": {"search": "Judges", "audio": "Judg"},
    "Ruth": {"search": "Ruth", "audio": "Ruth"},
    "1 Samuel": {"search": "1 Samuel", "audio": "1Sam"},
    "2 Samuel": {"search": "2 Samuel", "audio": "2Sam"},
    "1 Kings": {"search": "1 Kings", "audio": "1Kgs"},
    "2 Kings": {"search": "2 Kings", "audio": "2Kgs"},
    "1 Chronicles": {"search": "1 Chronicles", "audio": "1Chr"},
    "2 Chronicles": {"search": "2 Chronicles", "audio": "2Chr"},
    "Ezra": {"search": "Ezra", "audio": "Ezra"},
    "Nehemiah": {"search": "Nehemiah", "audio": "Neh"},
    "Esther": {"search": "Esther", "audio": "Esth"},
    "Job": {"search": "Job", "audio": "Job"},
    "Psalm": {"search": "Psalms", "audio": "Ps"},
    "Psalms": {"search": "Psalms", "audio": "Ps"},
    "Proverbs": {"search": "Proverbs", "audio": "Prov"},
    "Ecclesiastes": {"search": "Ecclesiastes", "audio": "Eccl"},
    "Song of Songs": {"search": "Song of Songs", "audio": "Song"},
    "Song": {"search": "Song of Songs", "audio": "Song"},
    "Isaiah": {"search": "Isaiah", "audio": "Isa"},
    "Jeremiah": {"search": "Jeremiah", "audio": "Jer"},
    "Lamentations": {"search": "Lamentations", "audio": "Lam"},
    "Ezekiel": {"search": "Ezekiel", "audio": "Ezek"},
    "Daniel": {"search": "Daniel", "audio": "Dan"},
    "Hosea": {"search": "Hosea", "audio": "Hos"},
    "Joel": {"search": "Joel", "audio": "Joel"},
    "Amos": {"search": "Amos", "audio": "Amos"},
    "Obadiah": {"search": "Obadiah", "audio": "Obad"},
    "Jonah": {"search": "Jonah", "audio": "Jonah"},
    "Micah": {"search": "Micah", "audio": "Mic"},
    "Nahum": {"search": "Nahum", "audio": "Nah"},
    "Habakkuk": {"search": "Habakkuk", "audio": "Hab"},
    "Zephaniah": {"search": "Zephaniah", "audio": "Zeph"},
    "Haggai": {"search": "Haggai", "audio": "Hag"},
    "Zechariah": {"search": "Zechariah", "audio": "Zech"},
    "Malachi": {"search": "Malachi", "audio": "Mal"},

    "Matthew": {"search": "Matthew", "audio": "Matt"},
    "Mark": {"search": "Mark", "audio": "Mark"},
    "Luke": {"search": "Luke", "audio": "Luke"},
    "John": {"search": "John", "audio": "John"},
    "Acts": {"search": "Acts", "audio": "Acts"},
    "Romans": {"search": "Romans", "audio": "Rom"},
    "1 Corinthians": {"search": "1 Corinthians", "audio": "1Cor"},
    "2 Corinthians": {"search": "2 Corinthians", "audio": "2Cor"},
    "Galatians": {"search": "Galatians", "audio": "Gal"},
    "Ephesians": {"search": "Ephesians", "audio": "Eph"},
    "Philippians": {"search": "Philippians", "audio": "Phil"},
    "Colossians": {"search": "Colossians", "audio": "Col"},
    "1 Thessalonians": {"search": "1 Thessalonians", "audio": "1Thess"},
    "2 Thessalonians": {"search": "2 Thessalonians", "audio": "2Thess"},
    "1 Timothy": {"search": "1 Timothy", "audio": "1Tim"},
    "2 Timothy": {"search": "2 Timothy", "audio": "2Tim"},
    "Titus": {"search": "Titus", "audio": "Titus"},
    "Philemon": {"search": "Philemon", "audio": "Phlm"},
    "Hebrews": {"search": "Hebrews", "audio": "Heb"},
    "James": {"search": "James", "audio": "Jas"},
    "1 Peter": {"search": "1 Peter", "audio": "1Pet"},
    "2 Peter": {"search": "2 Peter", "audio": "2Pet"},
    "1 John": {"search": "1 John", "audio": "1John"},
    "2 John": {"search": "2 John", "audio": "2John"},
    "3 John": {"search": "3 John", "audio": "3John"},
    "Jude": {"search": "Jude", "audio": "Jude"},
    "Revelation": {"search": "Revelation", "audio": "Rev"},
}


BOOKS_EN_NORMALIZED = {
    key.lower(): value
    for key, value in BOOKS_EN.items()
}

EN_TO_ZH = {}

for zh_name, info in BOOKS_ZH.items():
    EN_TO_ZH.setdefault(info["search"], zh_name)

# Prefer these standard Chinese names when multiple aliases exist.
EN_TO_ZH.update({
    "Genesis": "创世记",
    "Nehemiah": "尼希米记",
    "Obadiah": "俄巴底亚书",
})

ZH_BOOK_PATTERN = "|".join(
    re.escape(book_name)
    for book_name in sorted(BOOKS_ZH.keys(), key=len, reverse=True)
)

EN_BOOK_PATTERN = "|".join(
    re.escape(book_name)
    for book_name in sorted(BOOKS_EN.keys(), key=len, reverse=True)
)


ZH_PASSAGE_PATTERN = re.compile(
    rf"(?P<book>{ZH_BOOK_PATTERN})\s*第\s*(?P<chapter>\d+)\s*章"
    rf"(?:\s*(?P<verses>\d+\s*[-–—]\s*\d+|\d+)\s*节)?"
)
ZH_COMPACT_PASSAGE_PATTERN = re.compile(
    rf"(?P<book>{ZH_BOOK_PATTERN})\s*"
    rf"(?P<chapter>\d+)\s*[:：]\s*"
    rf"(?P<verses>\d+\s*[-–—]\s*\d+|\d+)"
)
EN_PASSAGE_PATTERN = re.compile(
    rf"(?P<book>{EN_BOOK_PATTERN})\s+"
    rf"(?P<chapter>\d+)"
    rf"(?::(?P<verses>\d+\s*[-–—]\s*\d+|\d+))?",
    re.IGNORECASE,
)


def normalize_verse_range(raw_verses):
    if not raw_verses:
        return ""

    return (
        raw_verses
        .replace(" ", "")
        .replace("–", "-")
        .replace("—", "-")
    )


def build_text_url(search_text, version=BIBLEGATEWAY_VERSION):
    encoded = quote(search_text)
    return (
        "https://www.biblegateway.com/passage/"
        f"?search={encoded}&version={version}&interface=print"
    )


def build_audio_url(audio_book_code, chapter):
    return (
        "https://www.biblegateway.com/audio/biblica/"
        f"{AUDIO_VERSION}/{audio_book_code}.{chapter}?interface=amp"
    )


def make_passage(book_label, book_info, chapter, verses, language):
    search_text = f"{book_info['search']} {chapter}"

    zh_book_name = EN_TO_ZH.get(book_info["search"], book_label)

    display_zh = f"{zh_book_name} 第 {chapter} 章"
    display_en = f"{book_info['search']} {chapter}"

    if verses:
        search_text = f"{search_text}:{verses}"
        display_zh = f"{display_zh} {verses} 节"
        display_en = f"{display_en}:{verses}"

    if language == "zh":
        display = display_zh
    else:
        display = display_en

    return {
        "book": book_info["search"],
        "book_zh": zh_book_name,
        "book_en": book_info["search"],
        "chapter": chapter,
        "verses": verses,
        "display": display,
        "display_zh": display_zh,
        "display_en": display_en,
        "search_text": search_text,

        # Default text URL uses Chinese.
        "text_url": build_text_url(search_text, BIBLEGATEWAY_VERSION_ZH),

        # Explicit bilingual URLs.
        "text_url_zh": build_text_url(search_text, BIBLEGATEWAY_VERSION_ZH),
        "text_url_en": build_text_url(search_text, BIBLEGATEWAY_VERSION_EN),

        "audio_url": build_audio_url(book_info["audio"], chapter),
    }


def parse_chinese_passages(reading_text):
    passages = []

    for match in ZH_PASSAGE_PATTERN.finditer(reading_text):
        book_zh = match.group("book")
        chapter = int(match.group("chapter"))
        verses = normalize_verse_range(match.group("verses"))

        book_info = BOOKS_ZH[book_zh]

        passages.append(
            make_passage(
                book_label=book_zh,
                book_info=book_info,
                chapter=chapter,
                verses=verses,
                language="zh",
            )
        )

    for match in ZH_COMPACT_PASSAGE_PATTERN.finditer(reading_text):
        book_zh = match.group("book")
        chapter = int(match.group("chapter"))
        verses = normalize_verse_range(match.group("verses"))

        book_info = BOOKS_ZH[book_zh]

        passages.append(
            make_passage(
                book_label=book_zh,
                book_info=book_info,
                chapter=chapter,
                verses=verses,
                language="zh",
            )
        )

    return passages


def parse_english_passages(reading_text):
    passages = []

    for match in EN_PASSAGE_PATTERN.finditer(reading_text):
        raw_book = " ".join(match.group("book").split())
        chapter = int(match.group("chapter"))
        verses = normalize_verse_range(match.group("verses"))

        book_info = BOOKS_EN_NORMALIZED.get(raw_book.lower())

        if not book_info:
            continue

        passages.append(
            make_passage(
                book_label=raw_book,
                book_info=book_info,
                chapter=chapter,
                verses=verses,
                language="en",
            )
        )

    return passages


def dedupe_passages(passages):
    seen = set()
    result = []

    for passage in passages:
        key = passage["search_text"]

        if key in seen:
            continue

        seen.add(key)
        result.append(passage)

    return result


def parse_reading_text(reading_text):
    if not reading_text:
        return []

    passages = []
    passages.extend(parse_chinese_passages(reading_text))
    passages.extend(parse_english_passages(reading_text))

    return dedupe_passages(passages)

def parse_memory_verse_text(memory_verse):
    return parse_reading_text(memory_verse)