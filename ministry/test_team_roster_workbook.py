from dataclasses import FrozenInstanceError, fields
import unicodedata

from django.test import SimpleTestCase

from ministry.services.team_roster_workbook import (
    MAX_PERSON_TOKEN_LENGTH,
    MAX_ROSTER_MEMBERS_PER_CELL,
    MAX_SOURCE_LITERAL_LENGTH,
    TEAM_ROSTER_CELL_CONTRACT_REVISION,
    TEAM_ROSTER_CELL_V1,
    ObservedTeamRosterColumn,
    ReviewedTeamRosterColumn,
    TeamRosterCellInput,
    TeamRosterCellState,
    TeamRosterColumnHint,
    TeamRosterColumnHintConfigurationError,
    TeamRosterDiffError,
    compute_team_roster_diff,
    parse_team_roster_cell,
    resolve_exact_team_roster_column_hint,
    validate_team_roster_column_hints,
)


def parse_text(value):
    return parse_team_roster_cell(TeamRosterCellInput.text(value))


class TeamRosterCellParserTests(SimpleTestCase):
    def test_contract_revision_and_technical_limits_are_frozen(self):
        self.assertEqual(TEAM_ROSTER_CELL_V1, "TEAM_ROSTER_CELL_V1")
        self.assertEqual(TEAM_ROSTER_CELL_CONTRACT_REVISION, TEAM_ROSTER_CELL_V1)
        self.assertEqual(MAX_ROSTER_MEMBERS_PER_CELL, 16)
        self.assertEqual(MAX_PERSON_TOKEN_LENGTH, 120)
        self.assertEqual(MAX_SOURCE_LITERAL_LENGTH, 2048)

    def test_blank_and_whitespace_only_are_no_source_proposal(self):
        for cell_input in (
            TeamRosterCellInput.blank(),
            TeamRosterCellInput.text(""),
            TeamRosterCellInput.text("   "),
            TeamRosterCellInput.text("\t\r\n"),
        ):
            with self.subTest(cell_input=cell_input):
                parsed = parse_team_roster_cell(cell_input)
                self.assertEqual(parsed.state, TeamRosterCellState.NO_SOURCE_PROPOSAL)
                self.assertEqual(parsed.person_tokens, ())

    def test_one_through_many_people_are_supported(self):
        for count in (1, 2, 3, 4, 9, 16):
            with self.subTest(count=count):
                parsed = parse_text("/".join(f"Person {index}" for index in range(count)))
                self.assertEqual(parsed.state, TeamRosterCellState.SUPPORTED_LITERAL)
                self.assertEqual(len(parsed.person_tokens), count)

    def test_seventeen_people_are_rejected_without_truncation(self):
        parsed = parse_text("/".join(f"Person {index}" for index in range(17)))
        self.assertEqual(parsed.state, TeamRosterCellState.TOO_MANY_MEMBERS)
        self.assertEqual(len(parsed.person_tokens), 17)

    def test_unicode_nfc_and_outer_trim_apply_to_cell_and_segments(self):
        decomposed = "Jose\N{COMBINING ACUTE ACCENT}"
        parsed = parse_text(f"  {decomposed}  /  Lee  ")
        self.assertEqual(parsed.state, TeamRosterCellState.SUPPORTED_LITERAL)
        self.assertEqual(
            parsed.person_tokens,
            (unicodedata.normalize("NFC", decomposed), "Lee"),
        )
        self.assertEqual(parsed.normalized_literal, f"{unicodedata.normalize('NFC', decomposed)}  /  Lee")

    def test_inner_whitespace_is_preserved(self):
        parsed = parse_text("  Mary  Jane / Lee   Ann  ")
        self.assertEqual(parsed.person_tokens, ("Mary  Jane", "Lee   Ann"))

    def test_empty_slash_segment_is_rejected(self):
        for value in ("/Alex", "Alex/", "Alex//Lee", "Alex/   /Lee"):
            with self.subTest(value=value):
                self.assertEqual(parse_text(value).state, TeamRosterCellState.EMPTY_SEGMENT)

    def test_duplicate_normalized_token_is_rejected(self):
        self.assertEqual(
            parse_text(" Alex /Alex ").state,
            TeamRosterCellState.DUPLICATE_TOKEN,
        )

    def test_case_distinct_tokens_remain_distinct(self):
        parsed = parse_text("Alex/alex")
        self.assertEqual(parsed.state, TeamRosterCellState.SUPPORTED_LITERAL)
        self.assertEqual(parsed.person_tokens, ("Alex", "alex"))

    def test_unsupported_separator_syntax_is_rejected(self):
        values = (
            "Alex／Lee",
            "Alex\\Lee",
            "Alex, Lee",
            "Alex，Lee",
            "Alex、Lee",
            "Alex; Lee",
            "Alex；Lee",
            "Alex & Lee",
        )
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(
                    parse_text(value).state, TeamRosterCellState.UNSUPPORTED_SYNTAX
                )

    def test_multiline_and_control_content_is_rejected(self):
        for value in (
            "Alex\nLee",
            "Alex\tLee",
            "Alex\rLee",
            "Alex\x00Lee",
            "Alex\u200bLee",
            "Alex\u2028Lee",
        ):
            with self.subTest(value=repr(value)):
                self.assertEqual(
                    parse_text(value).state, TeamRosterCellState.UNSUPPORTED_SYNTAX
                )

    def test_annotation_placeholder_and_replacement_syntax_is_rejected(self):
        values = (
            "Alex (backup)",
            "Alex【backup】",
            "Alex: backup",
            "TBD",
            "to be assigned",
            "to-be-assigned",
            "Alex replacement Lee",
            "Alex backup",
            "Alex stand in Lee",
            "Alex -> Lee",
            "Alex 替補 Lee",
            "待確認",
        )
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(
                    parse_text(value).state, TeamRosterCellState.UNSUPPORTED_SYNTAX
                )

    def test_ordinary_literal_name_punctuation_is_preserved(self):
        parsed = parse_text("O'Neil/Anne-Marie/J. Smith")
        self.assertEqual(parsed.state, TeamRosterCellState.SUPPORTED_LITERAL)
        self.assertEqual(parsed.person_tokens, ("O'Neil", "Anne-Marie", "J. Smith"))

    def test_formula_error_and_non_text_are_blocked_through_typed_seam(self):
        cases = (
            (TeamRosterCellInput.formula(), TeamRosterCellState.FORMULA_BLOCKED),
            (TeamRosterCellInput.error(), TeamRosterCellState.ERROR_BLOCKED),
            (TeamRosterCellInput.non_text(), TeamRosterCellState.NON_TEXT_BLOCKED),
        )
        for cell_input, state in cases:
            with self.subTest(cell_input=cell_input):
                self.assertEqual(parse_team_roster_cell(cell_input).state, state)

    def test_typed_seam_rejects_malformed_input(self):
        with self.assertRaises(TypeError):
            TeamRosterCellInput.text(42)
        with self.assertRaises(ValueError):
            TeamRosterCellInput(TeamRosterCellInput.blank().kind, "unexpected")
        with self.assertRaises(TypeError):
            parse_team_roster_cell("Alex")

    def test_token_over_120_is_rejected(self):
        parsed = parse_text("A" * 121)
        self.assertEqual(parsed.state, TeamRosterCellState.TOKEN_TOO_LONG)

    def test_literal_over_2048_is_rejected(self):
        parsed = parse_text("A" * 2049)
        self.assertEqual(parsed.state, TeamRosterCellState.SOURCE_LITERAL_TOO_LONG)


class TeamRosterColumnMappingTests(SimpleTestCase):
    def make_reviewed_column(self, **overrides):
        values = {
            "sheet_name": "Annual Roster",
            "column": "C",
            "observed_header": "Crew",
            "destination_team_id": 42,
            "destination_team_key": "main.ops.crew",
        }
        values.update(overrides)
        return ReviewedTeamRosterColumn(**values)

    def test_hint_and_reviewed_mapping_have_distinct_exact_frozen_fields(self):
        hint = TeamRosterColumnHint(
            expected_header="Crew",
            destination_team_key="main.ops.crew",
        )
        reviewed = self.make_reviewed_column()
        self.assertEqual(
            tuple(field.name for field in fields(hint)),
            ("expected_header", "destination_team_key"),
        )
        self.assertEqual(
            tuple(field.name for field in fields(reviewed)),
            (
                "sheet_name",
                "column",
                "observed_header",
                "destination_team_id",
                "destination_team_key",
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            hint.expected_header = "changed"
        with self.assertRaises(FrozenInstanceError):
            reviewed.observed_header = "changed"

    def test_observed_column_is_immutable_unmapped_external_evidence(self):
        decomposed = "Cafe\N{COMBINING ACUTE ACCENT}"
        observed = ObservedTeamRosterColumn(
            sheet_name="  Annual Roster  ",
            column="F",
            observed_header=decomposed,
        )
        self.assertEqual(
            tuple(field.name for field in fields(observed)),
            ("sheet_name", "column", "observed_header"),
        )
        self.assertEqual(observed.sheet_name, "  Annual Roster  ")
        self.assertEqual(observed.observed_header, decomposed)
        self.assertNotEqual(
            observed.observed_header,
            unicodedata.normalize("NFC", observed.observed_header),
        )
        self.assertFalse(hasattr(observed, "destination_team_key"))
        with self.assertRaises(FrozenInstanceError):
            observed.observed_header = "changed"

    def test_observed_column_preserves_blank_header_and_requires_uppercase_column(self):
        observed = ObservedTeamRosterColumn(
            sheet_name="Annual Roster", column="C", observed_header=""
        )
        self.assertEqual(observed.observed_header, "")
        with self.assertRaises(ValueError):
            ObservedTeamRosterColumn(
                sheet_name="Annual Roster", column="c", observed_header="Crew"
            )

    def test_hint_resolver_uses_literal_exact_equality_only(self):
        sound = TeamRosterColumnHint(
            expected_header="Sound",
            destination_team_key="main.cm.digital.sound",
        )
        hints = validate_team_roster_column_hints((sound,))
        self.assertIs(
            resolve_exact_team_roster_column_hint("Sound", hints), sound
        )
        for observed_header in ("sound", "Sound ", "sounder"):
            with self.subTest(observed_header=repr(observed_header)):
                self.assertIsNone(
                    resolve_exact_team_roster_column_hint(observed_header, hints)
                )

    def test_hint_resolver_does_not_normalize_unicode(self):
        composed = "Vid\N{LATIN SMALL LETTER E WITH ACUTE}o"
        decomposed = "Vide\N{COMBINING ACUTE ACCENT}o"
        hint = TeamRosterColumnHint(
            expected_header=composed,
            destination_team_key="main.cm.digital.video",
        )
        self.assertIsNone(
            resolve_exact_team_roster_column_hint(decomposed, (hint,))
        )

    def test_duplicate_exact_hint_configuration_fails_closed(self):
        duplicate_hints = (
            TeamRosterColumnHint(
                expected_header="Crew", destination_team_key="main.ops.first"
            ),
            TeamRosterColumnHint(
                expected_header="Crew", destination_team_key="main.ops.second"
            ),
        )
        for operation in (
            lambda: validate_team_roster_column_hints(duplicate_hints),
            lambda: resolve_exact_team_roster_column_hint(
                "unrelated", duplicate_hints
            ),
        ):
            with self.subTest(operation=operation), self.assertRaises(
                TeamRosterColumnHintConfigurationError
            ):
                operation()

    def test_observed_header_preserves_exact_external_evidence(self):
        decomposed = "Cafe\N{COMBINING ACUTE ACCENT}"
        self.assertNotEqual(unicodedata.normalize("NFC", decomposed), decomposed)
        for observed_header in (
            "sounder",
            "  Sound  ",
            decomposed,
            "",
        ):
            with self.subTest(observed_header=repr(observed_header)):
                reviewed = self.make_reviewed_column(
                    observed_header=observed_header
                )
                self.assertEqual(reviewed.observed_header, observed_header)

    def test_sheet_name_preserves_exact_external_evidence(self):
        sheet_name = "  Cafe\N{COMBINING ACUTE ACCENT}  "
        reviewed = self.make_reviewed_column(sheet_name=sheet_name)
        self.assertEqual(reviewed.sheet_name, sheet_name)

    def test_unknown_headers_are_not_mapping_blockers_and_remain_independent(self):
        first = self.make_reviewed_column(
            column="C", observed_header="sounder", destination_team_id=7
        )
        second = self.make_reviewed_column(
            column="D",
            observed_header="unregistered heading",
            destination_team_id=8,
            destination_team_key="main.ops.video",
        )
        self.assertEqual(first.observed_header, "sounder")
        self.assertEqual(second.observed_header, "unregistered heading")
        self.assertNotEqual(first.column, second.column)

    def test_hint_validates_configuration_and_canonical_team_key(self):
        invalid = (
            {"expected_header": ""},
            {"expected_header": " Crew"},
            {"expected_header": "Header\nTwo"},
            {"destination_team_key": "Main.Ops.Crew"},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(
                (TypeError, ValueError)
            ):
                values = {
                    "expected_header": "Crew",
                    "destination_team_key": "main.ops.crew",
                }
                values.update(overrides)
                TeamRosterColumnHint(**values)

    def test_reviewed_mapping_validates_column_and_canonical_team_identity(self):
        invalid = (
            {"sheet_name": ""},
            {"column": "c"},
            {"column": "XFE"},
            {"destination_team_id": 0},
            {"destination_team_id": True},
            {"destination_team_key": "Main.Ops.Crew"},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(
                (TypeError, ValueError)
            ):
                self.make_reviewed_column(**overrides)


class TeamRosterDiffTests(SimpleTestCase):
    def test_add_only_examples(self):
        empty = compute_team_roster_diff([], [1, 2])
        self.assertEqual(empty.preserved_ids, ())
        self.assertEqual(empty.add_ids, (1, 2))
        self.assertEqual(empty.remove_ids, ())

        retained = compute_team_roster_diff([1], [1, 2])
        self.assertEqual(retained.preserved_ids, (1,))
        self.assertEqual(retained.add_ids, (2,))
        self.assertEqual(retained.remove_ids, ())

    def test_remove_only_diff(self):
        diff = compute_team_roster_diff([1, 2], [1])
        self.assertEqual(diff.preserved_ids, (1,))
        self.assertEqual(diff.add_ids, ())
        self.assertEqual(diff.remove_ids, (2,))

    def test_mixed_add_remove_diff(self):
        diff = compute_team_roster_diff([1, 2], [1, 3])
        self.assertEqual(diff.preserved_ids, (1,))
        self.assertEqual(diff.add_ids, (3,))
        self.assertEqual(diff.remove_ids, (2,))

    def test_order_is_not_authority_and_output_is_deterministic(self):
        diff = compute_team_roster_diff([2, 1], [1, 2])
        self.assertEqual(diff.current_membership_ids, (1, 2))
        self.assertEqual(diff.reviewed_membership_ids, (1, 2))
        self.assertEqual(diff.preserved_ids, (1, 2))
        self.assertEqual(diff.add_ids, ())
        self.assertEqual(diff.remove_ids, ())

    def test_duplicate_membership_ids_fail_closed(self):
        for current, reviewed in (([1, 1], [1]), ([1], [1, 1])):
            with self.subTest(current=current, reviewed=reviewed), self.assertRaises(
                TeamRosterDiffError
            ):
                compute_team_roster_diff(current, reviewed)

    def test_non_positive_non_integer_membership_ids_fail_closed(self):
        for reviewed in ([0], [-1], [True], ["1"]):
            with self.subTest(reviewed=reviewed), self.assertRaises(
                TeamRosterDiffError
            ):
                compute_team_roster_diff([], reviewed)

    def test_diff_is_immutable(self):
        diff = compute_team_roster_diff([1], [1, 2])
        with self.assertRaises(FrozenInstanceError):
            diff.add_ids = (3,)
