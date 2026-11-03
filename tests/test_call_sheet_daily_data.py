import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import app.database as database
import app.main as main
from app.schemas import CallSheetDailyUpdate, ProjectCreate


class CallSheetDailyDataTests(unittest.TestCase):
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
            ProjectCreate(title="Hoja de llamado diaria", format="feature")
        )

    def test_get_returns_defaults_and_put_persists_daily_logistics(self):
        project_id = self.project["id"]

        defaults = main.get_project_call_sheet_daily_data(project_id, 2)
        self.assertEqual(defaults["day_number"], 2)
        self.assertEqual(defaults["weather"], "")
        self.assertEqual(defaults["general_notes"], "")

        saved = main.update_project_call_sheet_daily_data(
            project_id,
            2,
            CallSheetDailyUpdate(
                weather="Nublado, 15°C",
                start_time="08:00",
                end_time="18:30",
                catering_notes="Desayuno 08:00",
                tech_notes="Generador",
                general_notes="Acceso por calle norte",
            ),
        )
        loaded = main.get_project_call_sheet_daily_data(project_id, 2)

        self.assertEqual(saved, loaded)
        self.assertEqual(loaded["weather"], "Nublado, 15°C")
        self.assertEqual(loaded["start_time"], "08:00")
        self.assertEqual(loaded["end_time"], "18:30")
        self.assertEqual(loaded["catering_notes"], "Desayuno 08:00")
        self.assertEqual(loaded["tech_notes"], "Generador")
        self.assertEqual(loaded["general_notes"], "Acceso por calle norte")

    def test_daily_data_is_isolated_by_project_and_day(self):
        first_project_id = self.project["id"]
        second_project = main.create_project(
            ProjectCreate(title="Otro proyecto", format="feature")
        )
        main.update_project_call_sheet_daily_data(
            first_project_id,
            1,
            CallSheetDailyUpdate(weather="Soleado"),
        )

        first_day = main.get_project_call_sheet_daily_data(first_project_id, 1)
        second_day = main.get_project_call_sheet_daily_data(first_project_id, 2)
        other_project = main.get_project_call_sheet_daily_data(
            second_project["id"],
            1,
        )

        self.assertEqual(first_day["weather"], "Soleado")
        self.assertEqual(second_day["weather"], "")
        self.assertEqual(other_project["weather"], "")

    def test_unknown_project_returns_not_found(self):
        with self.assertRaises(HTTPException) as context:
            main.get_project_call_sheet_daily_data(999999, 1)
        self.assertEqual(context.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
