import unittest

from app.domain import resolve_character_alias


class ResolveCharacterAliasTests(unittest.TestCase):
    def test_empty_name_returns_empty(self):
        self.assertEqual(resolve_character_alias("", {}), "")

    def test_empty_aliases_returns_name_unchanged(self):
        self.assertEqual(resolve_character_alias("FELIPE", {}), "FELIPE")

    def test_registered_alias_returns_primary(self):
        aliases = {"don felipe": "FELIPE AMADO"}
        self.assertEqual(
            resolve_character_alias("DON FELIPE", aliases),
            "FELIPE AMADO",
        )

    def test_alias_lookup_is_case_insensitive(self):
        aliases = {"don felipe": "FELIPE AMADO"}
        self.assertEqual(
            resolve_character_alias("don felipe", aliases),
            "FELIPE AMADO",
        )
        self.assertEqual(
            resolve_character_alias("Don Felipe", aliases),
            "FELIPE AMADO",
        )

    def test_alias_with_leading_trailing_spaces(self):
        aliases = {"don felipe": "FELIPE AMADO"}
        self.assertEqual(
            resolve_character_alias("   DON FELIPE   ", aliases),
            "FELIPE AMADO",
        )

    def test_primary_name_itself_returns_unchanged(self):
        aliases = {"don felipe": "FELIPE AMADO"}
        self.assertEqual(
            resolve_character_alias("FELIPE AMADO", aliases),
            "FELIPE AMADO",
        )

    def test_unregistered_name_returns_unchanged(self):
        aliases = {"don felipe": "FELIPE AMADO"}
        self.assertEqual(
            resolve_character_alias("MARTA", aliases),
            "MARTA",
        )

    def test_multiple_aliases_to_same_primary(self):
        aliases = {
            "don felipe": "FELIPE AMADO",
            "felipe a.": "FELIPE AMADO",
            "pipe": "FELIPE AMADO",
        }
        self.assertEqual(
            resolve_character_alias("PIPE", aliases),
            "FELIPE AMADO",
        )
        self.assertEqual(
            resolve_character_alias("FELIPE A.", aliases),
            "FELIPE AMADO",
        )

    def test_multiple_aliases_to_different_primaries(self):
        aliases = {
            "don felipe": "FELIPE AMADO",
            "martita": "MARTA",
        }
        self.assertEqual(
            resolve_character_alias("MARTITA", aliases),
            "MARTA",
        )
        self.assertEqual(
            resolve_character_alias("DON FELIPE", aliases),
            "FELIPE AMADO",
        )

    def test_primary_with_accents_returns_unchanged(self):
        aliases = {"ramon": "RAMÓN GARCÍA"}
        self.assertEqual(
            resolve_character_alias("RAMON", aliases),
            "RAMÓN GARCÍA",
        )


if __name__ == "__main__":
    unittest.main()
