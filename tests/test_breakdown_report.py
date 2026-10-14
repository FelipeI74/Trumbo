import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import app.database as database
import app.main as main
from app.schemas import (
    BreakdownItemCreate,
    ProjectCreate,
    SceneCreate,
)


class BreakdownReportTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        patcher = patch.object(
            database,
            "DB_PATH",
            Path(temporary_directory.name) / "trumbo.db",
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        database.initialize()

        self.project = main.create_project(
            ProjectCreate(title="Informe de desglose", format="feature")
        )

    def _create_scene(self, heading="INT. CASA - DIA", body="Accion."):
        return main.create_scene(
            self.project["id"],
            SceneCreate(heading=heading, body=body),
        )

    def _add_item(self, scene_id, category, name, state="confirmed"):
        return main.add_breakdown_item(
            scene_id,
            BreakdownItemCreate(
                category=category,
                name=name,
                source="manual",
                state=state,
            ),
        )

    def test_unknown_project_returns_404(self):
        with self.assertRaises(HTTPException) as context:
            main.get_project_breakdown_report(999999)
        self.assertEqual(context.exception.status_code, 404)

    def test_empty_project_returns_zero_scenes_and_totals(self):
        report = main.get_project_breakdown_report(self.project["id"])
        self.assertEqual(report["total_scenes"], 0)
        self.assertEqual(report["scenes"], [])
        self.assertEqual(report["totals"]["confirmed"], 0)
        self.assertEqual(report["totals"]["detected"], 0)
        self.assertEqual(report["totals"]["by_category"], {})

    def test_scenes_ordered_by_scene_number(self):
        scene_a = self._create_scene(heading="INT. A - DIA")
        scene_b = self._create_scene(heading="INT. B - DIA")
        scene_c = self._create_scene(heading="INT. C - DIA")

        self._add_item(scene_c["id"], "prop", "Cosa C")
        self._add_item(scene_a["id"], "prop", "Cosa A")
        self._add_item(scene_b["id"], "prop", "Cosa B")

        report = main.get_project_breakdown_report(self.project["id"])
        numbers = [scene["scene_number"] for scene in report["scenes"]]
        self.assertEqual(numbers, sorted(numbers))
        self.assertEqual(report["total_scenes"], 3)

    def test_rejected_items_are_excluded(self):
        scene = self._create_scene()
        self._add_item(scene["id"], "prop", "Cuchillo", state="confirmed")
        self._add_item(scene["id"], "prop", "Taza", state="rejected")
        self._add_item(scene["id"], "wardrobe", "Delantal", state="detected")

        report = main.get_project_breakdown_report(self.project["id"])
        resources = report["scenes"][0]["resources"]
        names = sorted(item["name"] for item in resources)
        self.assertEqual(names, ["Cuchillo", "Delantal"])
        self.assertEqual(report["totals"]["confirmed"], 1)
        self.assertEqual(report["totals"]["detected"], 1)

    def test_dedupe_confirmed_wins_over_detected(self):
        scene = self._create_scene()
        self._add_item(scene["id"], "prop", "Cuchillo", state="detected")
        self._add_item(scene["id"], "prop", "cuchillo", state="confirmed")

        report = main.get_project_breakdown_report(self.project["id"])
        resources = report["scenes"][0]["resources"]
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["state"], "confirmed")
        self.assertEqual(resources[0]["name"], "cuchillo")

    def test_dedupe_same_state_keeps_one(self):
        scene = self._create_scene()
        self._add_item(scene["id"], "prop", "Cuchillo", state="detected")
        self._add_item(scene["id"], "prop", "Cuchillo", state="detected")

        report = main.get_project_breakdown_report(self.project["id"])
        resources = report["scenes"][0]["resources"]
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["state"], "detected")


if __name__ == "__main__":
    unittest.main()
