import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.database as database
import app.main as main
from app.schemas import ProjectCreate, SceneCreate, ScheduleManualOrder
from app.services.scheduling_service import calculate_shoot_date


class WorkingDayDateTests(unittest.TestCase):
    def test_second_weekday_skips_saturday_and_sunday(self):
        self.assertEqual(
            calculate_shoot_date("2026-11-06", 2, "1,2,3,4,5"),
            "2026-11-09",
        )

    def test_start_date_on_weekend_moves_to_next_workday(self):
        self.assertEqual(
            calculate_shoot_date("2026-11-07", 1, "1,2,3,4,5"),
            "2026-11-09",
        )

    def test_missing_start_date_has_no_shoot_date(self):
        self.assertIsNone(
            calculate_shoot_date(None, 1, "1,2,3,4,5"),
        )

    def test_schedule_preview_adds_working_dates_to_manual_days(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "trumbo.db"
            with patch.object(database, "DB_PATH", database_path):
                database.initialize()
                project = main.create_project(
                    ProjectCreate(title="Fechas laborables", format="feature")
                )
                scenes = [
                    main.create_scene(
                        project["id"],
                        SceneCreate(heading=f"INT. CASA {index} - DIA"),
                    )
                    for index in range(2)
                ]
                with database.connect() as connection:
                    connection.execute(
                        """
                        UPDATE projects
                        SET start_date = ?, work_days = ?
                        WHERE id = ?
                        """,
                        ("2026-11-06", "1,2,3,4,5", project["id"]),
                    )

                main.save_project_schedule_manual_order(
                    project["id"],
                    ScheduleManualOrder(
                        days=[
                            {"day": 1, "scene_ids": [scenes[0]["id"]]},
                            {"day": 2, "scene_ids": [scenes[1]["id"]]},
                        ]
                    ),
                )

                preview = main.get_project_schedule_preview(project["id"])
                days = preview["best_schedule"]["days"]

                self.assertEqual(
                    [day["shoot_date"] for day in days],
                    ["2026-11-06", "2026-11-09"],
                )


if __name__ == "__main__":
    unittest.main()
