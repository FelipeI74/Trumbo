import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.database as database
import app.main as main
from app.schemas import ProjectCreate


class ProjectCreationTests(unittest.TestCase):
    def test_creating_project_does_not_create_initial_scene(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trumbo.db"

            with patch.object(database, "DB_PATH", db_path):
                database.initialize()

                with database.connect() as connection:
                    connection.execute("DELETE FROM scenes")
                    connection.execute("DELETE FROM projects")

                created = main.create_project(
                    ProjectCreate(title="Nuevo proyecto", format="feature")
                )

                with database.connect() as connection:
                    scenes_count = connection.execute(
                        "SELECT COUNT(*) FROM scenes"
                    ).fetchone()[0]
                    projects_count = connection.execute(
                        "SELECT COUNT(*) FROM projects"
                    ).fetchone()[0]

                self.assertEqual(projects_count, 1)
                self.assertEqual(scenes_count, 0)
                self.assertEqual(created["title"], "Nuevo proyecto")


if __name__ == "__main__":
    unittest.main()
