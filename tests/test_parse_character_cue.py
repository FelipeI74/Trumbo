import unittest

from app.domain import parse_character_cue


class ParseCharacterCueTests(unittest.TestCase):
    def test_empty_string_returns_empty_list(self):
        self.assertEqual(parse_character_cue(""), [])

    def test_whitespace_only_returns_empty_list(self):
        self.assertEqual(parse_character_cue("   "), [])

    def test_single_uppercase_name(self):
        self.assertEqual(
            parse_character_cue("FRED"),
            [{"name": "FRED", "is_voice_over": False}],
        )

    def test_single_lowercase_name(self):
        self.assertEqual(
            parse_character_cue("fred"),
            [{"name": "fred", "is_voice_over": False}],
        )

    def test_name_with_leading_and_trailing_spaces(self):
        self.assertEqual(
            parse_character_cue("   FRED   "),
            [{"name": "FRED", "is_voice_over": False}],
        )

    def test_slash_separated_names(self):
        self.assertEqual(
            parse_character_cue("FRED/BARNEY"),
            [
                {"name": "FRED", "is_voice_over": False},
                {"name": "BARNEY", "is_voice_over": False},
            ],
        )

    def test_ampersand_separated_names(self):
        self.assertEqual(
            parse_character_cue("FRED & BARNEY"),
            [
                {"name": "FRED", "is_voice_over": False},
                {"name": "BARNEY", "is_voice_over": False},
            ],
        )

    def test_comma_separated_names(self):
        self.assertEqual(
            parse_character_cue("FRED, BARNEY"),
            [
                {"name": "FRED", "is_voice_over": False},
                {"name": "BARNEY", "is_voice_over": False},
            ],
        )

    def test_three_combined_names(self):
        self.assertEqual(
            parse_character_cue("FRED/BARNEY/WILMA"),
            [
                {"name": "FRED", "is_voice_over": False},
                {"name": "BARNEY", "is_voice_over": False},
                {"name": "WILMA", "is_voice_over": False},
            ],
        )

    def test_voice_over_vo_with_periods(self):
        self.assertEqual(
            parse_character_cue("FRED (V.O.)"),
            [{"name": "FRED", "is_voice_over": True}],
        )

    def test_voice_over_vo_without_periods(self):
        self.assertEqual(
            parse_character_cue("NARRADOR (VO)"),
            [{"name": "NARRADOR", "is_voice_over": True}],
        )

    def test_voice_over_os_with_periods(self):
        self.assertEqual(
            parse_character_cue("FRED (O.S.)"),
            [{"name": "FRED", "is_voice_over": True}],
        )

    def test_voice_over_os_without_periods(self):
        self.assertEqual(
            parse_character_cue("FRED (OS)"),
            [{"name": "FRED", "is_voice_over": True}],
        )

    def test_voice_over_lowercase(self):
        self.assertEqual(
            parse_character_cue("fred (v.o.)"),
            [{"name": "fred", "is_voice_over": True}],
        )

    def test_non_voice_parenthetical_is_stripped(self):
        self.assertEqual(
            parse_character_cue("FRED (CONT'D)"),
            [{"name": "FRED", "is_voice_over": False}],
        )

    def test_continuing_parenthetical_is_stripped(self):
        self.assertEqual(
            parse_character_cue("FRED (CONTINUING)"),
            [{"name": "FRED", "is_voice_over": False}],
        )

    def test_hyphen_does_not_separate_names(self):
        self.assertEqual(
            parse_character_cue("FRED - BARNEY"),
            [{"name": "FRED - BARNEY", "is_voice_over": False}],
        )

    def test_mixed_voice_and_non_voice_in_combined_cue(self):
        self.assertEqual(
            parse_character_cue("FRED (V.O.) / BARNEY"),
            [
                {"name": "FRED", "is_voice_over": True},
                {"name": "BARNEY", "is_voice_over": False},
            ],
        )

    def test_duplicate_same_name_is_collapsed(self):
        self.assertEqual(
            parse_character_cue("FRED/FRED"),
            [{"name": "FRED", "is_voice_over": False}],
        )

    def test_duplicate_case_insensitive_is_collapsed(self):
        self.assertEqual(
            parse_character_cue("FRED/fred"),
            [{"name": "FRED", "is_voice_over": False}],
        )

    def test_only_parenthetical_returns_empty(self):
        self.assertEqual(parse_character_cue("(V.O.)"), [])


if __name__ == "__main__":
    unittest.main()
