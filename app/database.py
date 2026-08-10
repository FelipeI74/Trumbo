from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "trumbo.db"


@contextmanager
def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def rows(
    connection: sqlite3.Connection,
    query: str,
    params: tuple = (),
) -> list[dict]:
    cursor = connection.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]


def column_exists(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    columns = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(
        column["name"] == column_name
        for column in columns
    )


def migrate(connection: sqlite3.Connection) -> None:
    """
    Agrega columnas nuevas sin borrar los proyectos
    ni las escenas que ya existen.
    """

    if not column_exists(
        connection,
        "scenes",
        "semantic_lines",
    ):
        connection.execute(
            """
            ALTER TABLE scenes
            ADD COLUMN semantic_lines TEXT NOT NULL DEFAULT '[]'
            """
        )


def initialize() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        format TEXT NOT NULL DEFAULT 'feature',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS scenes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        scene_number INTEGER NOT NULL,
        heading TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL DEFAULT '',
        semantic_lines TEXT NOT NULL DEFAULT '[]',
        synopsis TEXT NOT NULL DEFAULT '',
        runtime_seconds INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'draft',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
        UNIQUE(project_id, scene_number)
    );

    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scene_id INTEGER NOT NULL,
        category TEXT NOT NULL DEFAULT 'general',
        body TEXT NOT NULL,
        resolved INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(scene_id) REFERENCES scenes(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS breakdown_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scene_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'manual',
        state TEXT NOT NULL DEFAULT 'confirmed',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(scene_id) REFERENCES scenes(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS revisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scene_id INTEGER NOT NULL,
        previous_heading TEXT NOT NULL DEFAULT '',
        previous_body TEXT NOT NULL DEFAULT '',
        previous_semantic_lines TEXT NOT NULL DEFAULT '[]',
        changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(scene_id) REFERENCES scenes(id) ON DELETE CASCADE
    );
    """

    with connect() as connection:
        connection.executescript(schema)

        migrate(connection)

        count = connection.execute(
            "SELECT COUNT(*) FROM projects"
        ).fetchone()[0]

        if count == 0:
            cursor = connection.execute(
                """
                INSERT INTO projects(title, format)
                VALUES (?, ?)
                """,
                (
                    "Mi primer proyecto en Trumbo",
                    "feature",
                ),
            )

            project_id = cursor.lastrowid

            connection.execute(
                """
                INSERT INTO scenes(
                    project_id,
                    scene_number,
                    heading,
                    body,
                    semantic_lines,
                    synopsis,
                    runtime_seconds
                )
                VALUES (?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    "INT. COCINA - NOCHE",
                    "MARTA abre un cajón. Dentro hay una llave y una fotografía rota.\n\n"
                    "PEDRO entra sin hacer ruido.\n\n"
                    "PEDRO\n¿La encontraste?",
                    """
                    [
                        {
                            "type": "heading",
                            "text": "INT. COCINA - NOCHE"
                        },
                        {
                            "type": "action",
                            "text": "MARTA abre un cajón. Dentro hay una llave y una fotografía rota."
                        },
                        {
                            "type": "action",
                            "text": ""
                        },
                        {
                            "type": "action",
                            "text": "PEDRO entra sin hacer ruido."
                        },
                        {
                            "type": "action",
                            "text": ""
                        },
                        {
                            "type": "character",
                            "text": "PEDRO"
                        },
                        {
                            "type": "dialogue",
                            "text": "¿La encontraste?"
                        }
                    ]
                    """.strip(),
                    "Marta encuentra una llave mientras Pedro la sorprende en la cocina.",
                    24,
                ),
            )