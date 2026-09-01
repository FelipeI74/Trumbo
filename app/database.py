from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from collections.abc import Generator
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "trumbo.db"


@contextmanager
def connect() -> Generator[sqlite3.Connection, None, None]:
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
        column["name"].lower() == column_name.lower()
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

    # Agregar production_number de forma segura
    try:
        connection.execute(
            "ALTER TABLE scenes ADD COLUMN production_number TEXT"
        )
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            raise


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
        production_number TEXT,
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

    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        project_id INTEGER NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS document_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid TEXT NOT NULL UNIQUE,
        document_id TEXT NOT NULL,
        position INTEGER NOT NULL,
        type TEXT NOT NULL,
        text TEXT NOT NULL DEFAULT '',
        source_scene_id INTEGER,
        source_line_index INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
        FOREIGN KEY(source_scene_id) REFERENCES scenes(id) ON DELETE SET NULL,
        UNIQUE(document_id, position)
    );

    CREATE INDEX IF NOT EXISTS idx_document_lines_document_position
        ON document_lines(document_id, position);

    CREATE INDEX IF NOT EXISTS idx_document_lines_origin
        ON document_lines(document_id, source_scene_id, source_line_index);

    CREATE TABLE IF NOT EXISTS shots (
        id TEXT PRIMARY KEY,
        project_id INTEGER NOT NULL,
        scene_id INTEGER NOT NULL,
        sort_order INTEGER NOT NULL,
        shot_type TEXT NOT NULL DEFAULT 'PM',
        camera_movement TEXT NOT NULL DEFAULT 'Fijo',
        description TEXT,
        notes TEXT,
        storage_key TEXT,
        is_archived INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
        FOREIGN KEY(scene_id) REFERENCES scenes(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_shots_project_scene_archived_order
        ON shots(project_id, scene_id, is_archived, sort_order);
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
                    "Mi primer proyecto en ADÜMN",
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
