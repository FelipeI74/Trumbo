import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import app.database as database
import app.main as main
from app.schemas import ProjectCreate, SceneCreate, SceneUpdate, ScheduleManualOrder


class ScheduleManualOrderTests(unittest.TestCase):
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
            ProjectCreate(title="Orden manual", format="feature")
        )
        self.scenes = [
            main.create_scene(
                self.project["id"],
                SceneCreate(
                    heading=heading,
                    body=f"Acción de escena {index}.",
                ),
            )
            for index, heading in enumerate(
                (
                    "INT. CASA - DIA",
                    "EXT. CALLE - DIA",
                    "INT. OFICINA - NOCHE",
                ),
                start=1,
            )
        ]
        ids = [scene["id"] for scene in self.scenes]
        self.calculated = {
            "best_schedule": {
                "days": [
                    {
                        "day": 1,
                        "runtime_seconds": 120,
                        "scene_ids": ids[:2],
                        "locations": ["CASA", "CALLE"],
                        "over_capacity": False,
                    },
                    {
                        "day": 2,
                        "runtime_seconds": 60,
                        "scene_ids": ids[2:],
                        "locations": ["OFICINA"],
                        "over_capacity": False,
                    },
                ],
                "total_days": 2,
                "total_runtime_seconds": 180,
            },
            "score": {"total_score": 1.25},
            "candidates_evaluated": 2,
        }
        self.optimizer_patcher = patch(
            "app.main.optimize_schedule",
            side_effect=lambda *_args, **_kwargs: copy.deepcopy(self.calculated),
        )
        self.optimizer_patcher.start()
        self.addCleanup(self.optimizer_patcher.stop)

    def _valid_manual_days(self):
        return [
            {"day": 1, "scene_ids": [self.scenes[1]["id"], self.scenes[0]["id"]]},
            {"day": 2, "scene_ids": [self.scenes[2]["id"]]},
        ]

    def test_save_and_preview_persist_order_and_preserve_calculated_metadata(self):
        saved = main.save_project_schedule_manual_order(
            self.project["id"],
            ScheduleManualOrder(days=self._valid_manual_days()),
        )
        self.assertEqual(saved["status"], "ok")

        first_preview = main.get_project_schedule_preview(self.project["id"])
        reopened_preview = main.get_project_schedule_preview(self.project["id"])
        for preview in (first_preview, reopened_preview):
            self.assertEqual(
                preview["best_schedule"]["days"][0]["scene_ids"],
                self._valid_manual_days()[0]["scene_ids"],
            )
            self.assertEqual(
                preview["best_schedule"]["days"][0]["locations"],
                ["CASA", "CALLE"],
            )
            self.assertEqual(
                preview["best_schedule"]["days"][0]["runtime_seconds"],
                120,
            )
            self.assertEqual(preview["score"], {"total_score": 1.25})

    def test_rejects_duplicate_scene(self):
        days = self._valid_manual_days()
        days[0]["scene_ids"] = [self.scenes[0]["id"], self.scenes[0]["id"]]
        with self.assertRaises(HTTPException) as context:
            main.save_project_schedule_manual_order(
                self.project["id"], ScheduleManualOrder(days=days)
            )
        self.assertEqual(context.exception.status_code, 400)

    def test_rejects_missing_or_unknown_scene(self):
        for scene_ids in (
            [self.scenes[0]["id"]],
            [self.scenes[0]["id"], 999999],
        ):
            days = self._valid_manual_days()
            days[0]["scene_ids"] = scene_ids
            with self.subTest(scene_ids=scene_ids):
                with self.assertRaises(HTTPException) as context:
                    main.save_project_schedule_manual_order(
                        self.project["id"], ScheduleManualOrder(days=days)
                    )
                self.assertEqual(context.exception.status_code, 400)

    def test_rejects_moving_scene_between_days(self):
        days = self._valid_manual_days()
        days[0]["scene_ids"] = [self.scenes[0]["id"]]
        days[1]["scene_ids"] = [self.scenes[1]["id"], self.scenes[2]["id"]]
        with self.assertRaises(HTTPException) as context:
            main.save_project_schedule_manual_order(
                self.project["id"], ScheduleManualOrder(days=days)
            )
        self.assertEqual(context.exception.status_code, 400)

    def test_rejects_day_scene_after_night_scene(self):
        days = self._valid_manual_days()
        self.calculated["best_schedule"]["days"][0]["scene_ids"] = [
            self.scenes[0]["id"],
            self.scenes[2]["id"],
        ]
        self.calculated["best_schedule"]["days"][1]["scene_ids"] = [
            self.scenes[1]["id"]
        ]
        days[0]["scene_ids"] = [self.scenes[2]["id"], self.scenes[0]["id"]]
        days[1]["scene_ids"] = [self.scenes[1]["id"]]
        with self.assertRaises(HTTPException) as context:
            main.save_project_schedule_manual_order(
                self.project["id"], ScheduleManualOrder(days=days)
            )
        self.assertEqual(context.exception.status_code, 400)

    def test_stale_fingerprint_ignores_manual_order(self):
        main.save_project_schedule_manual_order(
            self.project["id"], ScheduleManualOrder(days=self._valid_manual_days())
        )
        main.update_scene(
            self.scenes[0]["id"],
            SceneUpdate(heading="INT. CASA - NOCHE"),
        )

        preview = main.get_project_schedule_preview(self.project["id"])
        self.assertEqual(
            preview["best_schedule"]["days"][0]["scene_ids"],
            self.calculated["best_schedule"]["days"][0]["scene_ids"],
        )

    def test_corrupt_json_falls_back_to_calculated_schedule(self):
        main.save_project_schedule_manual_order(
            self.project["id"], ScheduleManualOrder(days=self._valid_manual_days())
        )
        with database.connect() as connection:
            connection.execute(
                "UPDATE schedule_manual_orders SET days_json = ? WHERE project_id = ?",
                ("{broken", self.project["id"]),
            )

        preview = main.get_project_schedule_preview(self.project["id"])
        self.assertEqual(
            preview["best_schedule"]["days"][0]["scene_ids"],
            self.calculated["best_schedule"]["days"][0]["scene_ids"],
        )

    def test_delete_restores_calculated_order(self):
        main.save_project_schedule_manual_order(
            self.project["id"], ScheduleManualOrder(days=self._valid_manual_days())
        )
        result = main.delete_project_schedule_manual_order(self.project["id"])
        self.assertEqual(result["status"], "deleted")
        preview = main.get_project_schedule_preview(self.project["id"])
        self.assertEqual(
            preview["best_schedule"]["days"][0]["scene_ids"],
            self.calculated["best_schedule"]["days"][0]["scene_ids"],
        )


if __name__ == "__main__":
    unittest.main()