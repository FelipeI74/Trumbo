import unittest

from app.scene_derivation import (
    apply_reconciliation,
    derive_scene_headings_from_document,
)


class DocumentSceneDerivationTests(unittest.TestCase):
    def test_a_fade_in_produces_zero_scenes(self):
        document = "FADE IN:\n"

        headings = derive_scene_headings_from_document(document)

        self.assertEqual(headings, [])

    def test_b_single_int_heading_produces_one_scene(self):
        document = "INT. CASA - DIA\n"

        headings = derive_scene_headings_from_document(document)

        self.assertEqual(headings, ["INT. CASA - DIA"])

    def test_c_three_valid_headings_produce_three_scenes(self):
        document = (
            "INT. CASA - DIA\n"
            "acción\n"
            "\n"
            "EXT. CALLE - NOCHE\n"
            "acción\n"
            "\n"
            "INT. AUTO - DIA\n"
            "acción\n"
        )

        headings = derive_scene_headings_from_document(document)

        self.assertEqual(
            headings,
            [
                "INT. CASA - DIA",
                "EXT. CALLE - NOCHE",
                "INT. AUTO - DIA",
            ],
        )

    def test_d_editing_heading_keeps_one_scene_and_updates_heading(self):
        before = "INT. CASA - DIA\n"
        after = "INT. CASA DE PEDRO - NOCHE\n"

        before_headings = derive_scene_headings_from_document(before)
        after_headings = derive_scene_headings_from_document(after)

        self.assertEqual(len(before_headings), 1)
        self.assertEqual(len(after_headings), 1)
        self.assertEqual(after_headings[0], "INT. CASA DE PEDRO - NOCHE")

    def test_e_removing_one_of_three_headings_leaves_two_without_ghost(self):
        initial_doc = (
            "INT. CASA - DIA\n"
            "acción\n"
            "\n"
            "EXT. CALLE - NOCHE\n"
            "acción\n"
            "\n"
            "INT. AUTO - DIA\n"
            "acción\n"
        )

        updated_doc = (
            "INT. CASA - DIA\n"
            "acción\n"
            "\n"
            "acción sin heading intermedio\n"
            "\n"
            "INT. AUTO - DIA\n"
            "acción\n"
        )

        scene_ids, first_result, next_id = apply_reconciliation([], initial_doc, 1)
        scene_ids, second_result, _ = apply_reconciliation(scene_ids, updated_doc, next_id)

        self.assertEqual(first_result.scene_count, 3)
        self.assertEqual(second_result.scene_count, 2)
        self.assertEqual(len(scene_ids), 2)
        self.assertEqual(second_result.deleted_scene_ids, [3])

    def test_f_reconciling_same_document_twice_does_not_duplicate_scenes(self):
        document = (
            "INT. CASA - DIA\n"
            "acción\n"
            "\n"
            "EXT. CALLE - NOCHE\n"
            "acción\n"
        )

        scene_ids, first_result, next_id = apply_reconciliation([], document, 10)
        scene_ids, second_result, _ = apply_reconciliation(scene_ids, document, next_id)

        self.assertEqual(first_result.scene_count, 2)
        self.assertEqual(first_result.created_scene_ids, [10, 11])
        self.assertEqual(second_result.scene_count, 2)
        self.assertEqual(second_result.created_scene_ids, [])
        self.assertEqual(second_result.deleted_scene_ids, [])
        self.assertEqual(scene_ids, [10, 11])

    def test_g_paste_and_typing_same_structure_produce_same_scenes(self):
        typed_lines = [
            "INT. CASA - DIA",
            "acción",
            "",
            "EXT. CALLE - NOCHE",
            "acción",
        ]

        pasted_document = "\n".join(typed_lines)
        typed_document = "\n".join(typed_lines)

        pasted_headings = derive_scene_headings_from_document(pasted_document)
        typed_headings = derive_scene_headings_from_document(typed_document)

        self.assertEqual(pasted_headings, typed_headings)
        self.assertEqual(
            typed_headings,
            [
                "INT. CASA - DIA",
                "EXT. CALLE - NOCHE",
            ],
        )


if __name__ == "__main__":
    unittest.main()
