"""Team-neutral domain primitives for reviewed roster workbook cells.

Workbook adapters are responsible for extracting a cell and classifying its
primitive kind.  This module owns only the literal roster grammar and exact
membership-ID set comparison; it performs no database access or mutation.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
import re
import unicodedata


TEAM_ROSTER_CELL_V1 = "TEAM_ROSTER_CELL_V1"
TEAM_ROSTER_CELL_CONTRACT_REVISION = TEAM_ROSTER_CELL_V1

MAX_ROSTER_MEMBERS_PER_CELL = 16
MAX_PERSON_TOKEN_LENGTH = 120
MAX_SOURCE_LITERAL_LENGTH = 2048


_TEAM_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_COLUMN_RE = re.compile(r"^[A-Z]{1,3}$")
_PLACEHOLDER_RE = re.compile(
    r"\b(?:tbd|tba)\b|\bto(?:-|\s)+be(?:-|\s)+(?:decided|assigned|confirmed)\b",
    re.IGNORECASE,
)
_REPLACEMENT_RE = re.compile(
    r"\b(?:sub|substitute|replacement|replace|instead|back(?:-|\s)?up|stand(?:-|\s)?in)\b",
    re.IGNORECASE,
)
_UNSUPPORTED_SEPARATORS = ("&", ",", "，", "、", ";", "；", "／", "\\")
_ANNOTATION_MARKERS = (
    "(",
    ")",
    "（",
    "）",
    "[",
    "]",
    "【",
    "】",
    ":",
    "：",
)
_REPLACEMENT_MARKERS = (
    "->",
    "=>",
    "<-",
    "→",
    "←",
    "⇒",
    "替补",
    "替補",
    "代班",
    "待定",
    "待确认",
    "待確認",
)


class TeamRosterCellInputKind(StrEnum):
    """Primitive cell kinds supplied by a deployment-owned adapter."""

    BLANK = "blank"
    TEXT = "text"
    FORMULA = "formula"
    ERROR = "error"
    NON_TEXT = "non_text"


class TeamRosterCellState(StrEnum):
    NO_SOURCE_PROPOSAL = "no_source_proposal"
    SUPPORTED_LITERAL = "supported_literal"
    FORMULA_BLOCKED = "formula_blocked"
    ERROR_BLOCKED = "error_blocked"
    NON_TEXT_BLOCKED = "non_text_blocked"
    SOURCE_LITERAL_TOO_LONG = "source_literal_too_long"
    TOO_MANY_MEMBERS = "too_many_members"
    TOKEN_TOO_LONG = "token_too_long"
    EMPTY_SEGMENT = "empty_segment"
    DUPLICATE_TOKEN = "duplicate_token"
    UNSUPPORTED_SYNTAX = "unsupported_syntax"


@dataclass(frozen=True, slots=True)
class TeamRosterCellInput:
    """Typed adapter-to-domain seam for one already selected cell."""

    kind: TeamRosterCellInputKind
    value: str | None = None

    def __post_init__(self):
        if type(self.kind) is not TeamRosterCellInputKind:
            raise TypeError("Cell input kind must be a TeamRosterCellInputKind.")
        if self.kind == TeamRosterCellInputKind.TEXT:
            if type(self.value) is not str:
                raise TypeError("Text cell input requires a string value.")
        elif self.value is not None:
            raise ValueError("Only text cell input may carry a value.")

    @classmethod
    def blank(cls):
        return cls(TeamRosterCellInputKind.BLANK)

    @classmethod
    def text(cls, value):
        return cls(TeamRosterCellInputKind.TEXT, value)

    @classmethod
    def formula(cls):
        return cls(TeamRosterCellInputKind.FORMULA)

    @classmethod
    def error(cls):
        return cls(TeamRosterCellInputKind.ERROR)

    @classmethod
    def non_text(cls):
        return cls(TeamRosterCellInputKind.NON_TEXT)


@dataclass(frozen=True, slots=True)
class ParsedTeamRosterCell:
    state: TeamRosterCellState
    normalized_literal: str | None
    person_tokens: tuple[str, ...]

    @property
    def is_blocked(self):
        return self.state not in {
            TeamRosterCellState.NO_SOURCE_PROPOSAL,
            TeamRosterCellState.SUPPORTED_LITERAL,
        }


def _has_control_or_multiline_content(value):
    return any(
        unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
        for character in value
    )


def _has_unsupported_syntax(value):
    return bool(
        _has_control_or_multiline_content(value)
        or any(marker in value for marker in _UNSUPPORTED_SEPARATORS)
        or any(marker in value for marker in _ANNOTATION_MARKERS)
        or any(marker in value for marker in _REPLACEMENT_MARKERS)
        or _PLACEHOLDER_RE.search(value)
        or _REPLACEMENT_RE.search(value)
    )


def _parsed_blocker(state, normalized_literal=None, person_tokens=()):
    return ParsedTeamRosterCell(state, normalized_literal, tuple(person_tokens))


def parse_team_roster_cell(cell_input):
    """Parse one typed cell under ``TEAM_ROSTER_CELL_V1``.

    The adapter must classify formulas, errors, and other non-text values before
    calling this function.  Blank values are no-proposal evidence; all other
    unsupported forms return an explicit blocker state.
    """

    if type(cell_input) is not TeamRosterCellInput:
        raise TypeError("Expected a TeamRosterCellInput from the adapter boundary.")

    if cell_input.kind == TeamRosterCellInputKind.BLANK:
        return ParsedTeamRosterCell(
            TeamRosterCellState.NO_SOURCE_PROPOSAL, None, ()
        )
    if cell_input.kind == TeamRosterCellInputKind.FORMULA:
        return _parsed_blocker(TeamRosterCellState.FORMULA_BLOCKED)
    if cell_input.kind == TeamRosterCellInputKind.ERROR:
        return _parsed_blocker(TeamRosterCellState.ERROR_BLOCKED)
    if cell_input.kind == TeamRosterCellInputKind.NON_TEXT:
        return _parsed_blocker(TeamRosterCellState.NON_TEXT_BLOCKED)

    source_literal = unicodedata.normalize("NFC", cell_input.value)
    normalized_literal = source_literal.strip()
    if not normalized_literal:
        return ParsedTeamRosterCell(
            TeamRosterCellState.NO_SOURCE_PROPOSAL, None, ()
        )
    if (
        len(cell_input.value) > MAX_SOURCE_LITERAL_LENGTH
        or len(normalized_literal) > MAX_SOURCE_LITERAL_LENGTH
    ):
        return _parsed_blocker(
            TeamRosterCellState.SOURCE_LITERAL_TOO_LONG, normalized_literal
        )
    if _has_unsupported_syntax(source_literal):
        return _parsed_blocker(
            TeamRosterCellState.UNSUPPORTED_SYNTAX, normalized_literal
        )

    person_tokens = tuple(
        unicodedata.normalize("NFC", segment).strip()
        for segment in normalized_literal.split("/")
    )
    if any(not token for token in person_tokens):
        return _parsed_blocker(
            TeamRosterCellState.EMPTY_SEGMENT,
            normalized_literal,
            person_tokens,
        )
    if len(person_tokens) > MAX_ROSTER_MEMBERS_PER_CELL:
        return _parsed_blocker(
            TeamRosterCellState.TOO_MANY_MEMBERS,
            normalized_literal,
            person_tokens,
        )
    if any(len(token) > MAX_PERSON_TOKEN_LENGTH for token in person_tokens):
        return _parsed_blocker(
            TeamRosterCellState.TOKEN_TOO_LONG,
            normalized_literal,
            person_tokens,
        )
    if any(_has_unsupported_syntax(token) for token in person_tokens):
        return _parsed_blocker(
            TeamRosterCellState.UNSUPPORTED_SYNTAX,
            normalized_literal,
            person_tokens,
        )
    if len(set(person_tokens)) != len(person_tokens):
        return _parsed_blocker(
            TeamRosterCellState.DUPLICATE_TOKEN,
            normalized_literal,
            person_tokens,
        )
    return ParsedTeamRosterCell(
        TeamRosterCellState.SUPPORTED_LITERAL,
        normalized_literal,
        person_tokens,
    )


def _validate_exact_config_text(name, value, *, maximum_length):
    if type(value) is not str:
        raise TypeError(f"{name} must be text.")
    if not value or value != value.strip():
        raise ValueError(f"{name} must be nonblank and outer-trimmed.")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"{name} must use canonical Unicode NFC.")
    if len(value) > maximum_length or _has_control_or_multiline_content(value):
        raise ValueError(f"{name} has an invalid configuration shape.")


def _validate_external_evidence_text(name, value, *, maximum_length, allow_blank=False):
    """Bound exact workbook evidence without rewriting its literal value."""

    if type(value) is not str:
        raise TypeError(f"{name} must be text.")
    if not allow_blank and not value:
        raise ValueError(f"{name} must be nonempty.")
    if len(value) > maximum_length:
        raise ValueError(f"{name} exceeds its evidence length bound.")


def _column_number(value):
    number = 0
    for character in value:
        number = number * 26 + (ord(character) - ord("A") + 1)
    return number


@dataclass(frozen=True, slots=True)
class ObservedTeamRosterColumn:
    """Exact external column evidence before any human team review."""

    sheet_name: str
    column: str
    observed_header: str

    def __post_init__(self):
        _validate_external_evidence_text(
            "sheet_name", self.sheet_name, maximum_length=31
        )
        _validate_exact_config_text("column", self.column, maximum_length=3)
        _validate_external_evidence_text(
            "observed_header",
            self.observed_header,
            maximum_length=255,
            allow_blank=True,
        )
        _validate_worksheet_column(self.column)


@dataclass(frozen=True, slots=True)
class TeamRosterColumnHint:
    """Optional adapter convenience for exact-header automatic matching."""

    expected_header: str
    destination_team_key: str

    def __post_init__(self):
        _validate_exact_config_text(
            "expected_header", self.expected_header, maximum_length=255
        )
        _validate_exact_config_text(
            "destination_team_key", self.destination_team_key, maximum_length=64
        )
        if _TEAM_KEY_RE.fullmatch(self.destination_team_key) is None:
            raise ValueError("destination_team_key must be a canonical team key.")


class TeamRosterColumnHintConfigurationError(ValueError):
    pass


def validate_team_roster_column_hints(hints):
    """Return immutable exact hints or fail on an ambiguous header claim."""

    if isinstance(hints, (str, bytes)) or not isinstance(hints, Iterable):
        raise TeamRosterColumnHintConfigurationError(
            "Column hints must be an iterable of TeamRosterColumnHint values."
        )
    validated = tuple(hints)
    if any(type(hint) is not TeamRosterColumnHint for hint in validated):
        raise TeamRosterColumnHintConfigurationError(
            "Column hints must contain only TeamRosterColumnHint values."
        )
    seen_headers = set()
    for hint in validated:
        if hint.expected_header in seen_headers:
            raise TeamRosterColumnHintConfigurationError(
                "Two column hints claim the same exact observed header."
            )
        seen_headers.add(hint.expected_header)
    return validated


def resolve_exact_team_roster_column_hint(observed_header, hints):
    """Resolve one literal header without trimming or Unicode/case rewriting."""

    _validate_external_evidence_text(
        "observed_header", observed_header, maximum_length=255, allow_blank=True
    )
    for hint in validate_team_roster_column_hints(hints):
        if observed_header == hint.expected_header:
            return hint
    return None


def _validate_worksheet_column(column):
    if _COLUMN_RE.fullmatch(column) is None or _column_number(column) > 16384:
        raise ValueError("column must be a valid uppercase worksheet column.")


@dataclass(frozen=True, slots=True)
class ReviewedTeamRosterColumn:
    """Human-reviewed external column evidence and canonical team identity.

    Team activity and assignability are current database facts and are
    deliberately revalidated by the later DB-aware mapping/preview layer.
    """

    sheet_name: str
    column: str
    observed_header: str
    destination_team_id: int
    destination_team_key: str

    def __post_init__(self):
        _validate_external_evidence_text(
            "sheet_name", self.sheet_name, maximum_length=31
        )
        _validate_exact_config_text("column", self.column, maximum_length=3)
        _validate_external_evidence_text(
            "observed_header",
            self.observed_header,
            maximum_length=255,
            allow_blank=True,
        )
        _validate_exact_config_text(
            "destination_team_key", self.destination_team_key, maximum_length=64
        )
        _validate_worksheet_column(self.column)
        if type(self.destination_team_id) is not int:
            raise TypeError("destination_team_id must be an integer.")
        if self.destination_team_id <= 0:
            raise ValueError("destination_team_id must be a positive integer.")
        if _TEAM_KEY_RE.fullmatch(self.destination_team_key) is None:
            raise ValueError("destination_team_key must be a canonical team key.")


class TeamRosterDiffError(ValueError):
    pass


def _canonical_membership_ids(values, *, label):
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise TeamRosterDiffError(f"{label} must be an iterable of membership IDs.")
    membership_ids = tuple(values)
    if any(type(value) is not int or value <= 0 for value in membership_ids):
        raise TeamRosterDiffError(
            f"{label} must contain only positive integer membership IDs."
        )
    if len(set(membership_ids)) != len(membership_ids):
        raise TeamRosterDiffError(f"{label} contains a duplicate membership ID.")
    return tuple(sorted(membership_ids))


@dataclass(frozen=True, slots=True)
class TeamRosterDiff:
    current_membership_ids: tuple[int, ...]
    reviewed_membership_ids: tuple[int, ...]
    preserved_ids: tuple[int, ...]
    add_ids: tuple[int, ...]
    remove_ids: tuple[int, ...]

    def __post_init__(self):
        current = _canonical_membership_ids(
            self.current_membership_ids, label="current_membership_ids"
        )
        reviewed = _canonical_membership_ids(
            self.reviewed_membership_ids, label="reviewed_membership_ids"
        )
        if current != self.current_membership_ids:
            raise TeamRosterDiffError("current_membership_ids must be canonical.")
        if reviewed != self.reviewed_membership_ids:
            raise TeamRosterDiffError("reviewed_membership_ids must be canonical.")
        expected = (
            tuple(sorted(set(current) & set(reviewed))),
            tuple(sorted(set(reviewed) - set(current))),
            tuple(sorted(set(current) - set(reviewed))),
        )
        actual = (self.preserved_ids, self.add_ids, self.remove_ids)
        if any(type(value) is not tuple for value in actual) or actual != expected:
            raise TeamRosterDiffError("Roster diff fields must match the canonical sets.")


def compute_team_roster_diff(current_membership_ids, reviewed_membership_ids):
    """Return the deterministic exact set diff for two reviewed rosters."""

    current = _canonical_membership_ids(
        current_membership_ids, label="current_membership_ids"
    )
    reviewed = _canonical_membership_ids(
        reviewed_membership_ids, label="reviewed_membership_ids"
    )
    current_set = set(current)
    reviewed_set = set(reviewed)
    return TeamRosterDiff(
        current_membership_ids=current,
        reviewed_membership_ids=reviewed,
        preserved_ids=tuple(sorted(current_set & reviewed_set)),
        add_ids=tuple(sorted(reviewed_set - current_set)),
        remove_ids=tuple(sorted(current_set - reviewed_set)),
    )
