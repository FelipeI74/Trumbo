import copy
import unittest

from app.document_projection import (
    assert_scene_parity,
    audit_scene_parity,
    derive_scenes_from_document_lines,
    project_document_from_scenes,
)


class DocumentProjectionTests(unittest.TestCase):
    def _sample_scenes(self) -> list[dict]:
        return [
            {
                "id": 101,
                "scene_number": 1,
                "heading": "INT. CASA - DIA",
                "body": "",
                "semantic_lines": [
                    {"type": "heading", "text": "INT. CASA - DIA"},
                    {"type": "action", "text": "MARTA abre la ventana."},
                ],
            },
            {
                "id": 102,
                "scene_number": 2,
                "heading": "EXT. CALLE - NOCHE",
                "body": "",
                "semantic_lines": [
                    {"type": "heading", "text": "EXT. CALLE - NOCHE"},
                    {"type": "character", "text": "PEDRO"},
                    {"type": "dialogue", "text": "No llegaremos a tiempo."},
                    {"type": "transition", "text": "CUT TO:"},
                ],
            },
        ]

    def test_a_and_b_and_c_projection_keeps_count_order_and_uuid_uniqueness(self):
        scenes = self._sample_scenes()

        projected = project_document_from_scenes(7, scenes)
        lines = projected["lines"]

        expected_pairs = [
            ("heading", "INT. CASA - DIA"),
            ("action", "MARTA abre la ventana."),
            ("heading", "EXT. CALLE - NOCHE"),
            ("character", "PEDRO"),
            ("dialogue", "No llegaremos a tiempo."),
            ("transition", "CUT TO:"),
        ]

        self.assertEqual(len(lines), len(expected_pairs))
        self.assertEqual([(line["type"], line["text"]) for line in lines], expected_pairs)
        self.assertEqual([line["position"] for line in lines], list(range(len(lines))))

        uuids = [line["uuid"] for line in lines]
        self.assertEqual(len(uuids), len(set(uuids)))

    def test_d_backfill_twice_is_stable_without_duplication(self):
        scenes = [
            {
                "id": 201,
                "scene_number": 1,
                "heading": "INT. OFICINA - DIA",
                "body": "Línea uno\nLínea dos",
                "semantic_lines": [],
            }
        ]

        first = project_document_from_scenes(9, scenes)
        second = project_document_from_scenes(9, scenes, existing_lines=first["lines"])

        first_uuids = [line["uuid"] for line in first["lines"]]
        second_uuids = [line["uuid"] for line in second["lines"]]

        self.assertEqual(first_uuids, second_uuids)
        self.assertEqual(len(second_uuids), len(set(second_uuids)))

    def test_e_editing_only_text_keeps_uuid(self):
        scenes = self._sample_scenes()

        first = project_document_from_scenes(11, scenes)

        edited = copy.deepcopy(scenes)
        edited[0]["semantic_lines"][1]["text"] = "MARTA cierra la ventana."

        second = project_document_from_scenes(11, edited, existing_lines=first["lines"])

        self.assertEqual(
            [line["uuid"] for line in first["lines"]],
            [line["uuid"] for line in second["lines"]],
        )

    def test_f_editing_only_type_keeps_uuid(self):
        scenes = self._sample_scenes()

        first = project_document_from_scenes(12, scenes)

        edited = copy.deepcopy(scenes)
        edited[1]["semantic_lines"][2]["type"] = "parenthetical"

        second = project_document_from_scenes(12, edited, existing_lines=first["lines"])

        self.assertEqual(
            [line["uuid"] for line in first["lines"]],
            [line["uuid"] for line in second["lines"]],
        )

    def test_g_fade_in_preface_is_preserved_and_does_not_create_scene(self):
        lines = [
            {"uuid": "u-1", "document_id": "d", "position": 0, "type": "transition", "text": "FADE IN:"},
            {"uuid": "u-2", "document_id": "d", "position": 1, "type": "heading", "text": "INT. CASA - DIA"},
            {"uuid": "u-3", "document_id": "d", "position": 2, "type": "action", "text": "MARTA entra."},
        ]

        rebuilt = derive_scenes_from_document_lines(lines)

        self.assertEqual(rebuilt["preface_lines"], [{"type": "transition", "text": "FADE IN:"}])
        self.assertEqual(len(rebuilt["scenes"]), 1)

    def test_h_tail_after_last_heading_belongs_to_last_scene(self):
        lines = [
            {"uuid": "u-1", "document_id": "d", "position": 0, "type": "heading", "text": "INT. CASA - DIA"},
            {"uuid": "u-2", "document_id": "d", "position": 1, "type": "action", "text": "MARTA mira el reloj."},
            {"uuid": "u-3", "document_id": "d", "position": 2, "type": "heading", "text": "EXT. CALLE - NOCHE"},
            {"uuid": "u-4", "document_id": "d", "position": 3, "type": "dialogue", "text": "No queda tiempo."},
            {"uuid": "u-5", "document_id": "d", "position": 4, "type": "transition", "text": "CUT TO:"},
        ]

        rebuilt = derive_scenes_from_document_lines(lines)
        last_scene = rebuilt["scenes"][-1]

        self.assertEqual(last_scene["heading"], "EXT. CALLE - NOCHE")
        self.assertEqual(last_scene["semantic_lines"][1]["type"], "dialogue")
        self.assertEqual(last_scene["semantic_lines"][2]["type"], "transition")

    def test_i_rebuild_from_lines_matches_original_scene_payload(self):
        scenes = self._sample_scenes()

        projected = project_document_from_scenes(31, scenes)
        rebuilt = derive_scenes_from_document_lines(projected["lines"])
        parity = audit_scene_parity(scenes, rebuilt["scenes"])

        self.assertTrue(parity.ok, msg=" | ".join(parity.errors))
        assert_scene_parity(scenes, rebuilt["scenes"])


if __name__ == "__main__":
    unittest.main()