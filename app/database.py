from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "trumbo.db"


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def rows(connection: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict]:
    cursor = connection.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]


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
        changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(scene_id) REFERENCES scenes(id) ON DELETE CASCADE
    );
    """
    with connect() as connection:
        connection.executescript(schema)

        count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        if count == 0:
            cursor = connection.execute(
                "INSERT INTO projects(title, format) VALUES (?, ?)",
                ("Mi primer proyecto en Trumbo", "feature"),
            )
            project_id = cursor.lastrowid
            connection.execute(
                """
                INSERT INTO scenes(project_id, scene_number, heading, body, synopsis, runtime_seconds)
                VALUES (?, 1, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    "INT. COCINA - NOCHE",
                    "MARTA abre un cajón. Dentro hay una llave y una fotografía rota.\n\n"
                    "PEDRO entra sin hacer ruido.\n\n"
                    "PEDRO\n¿La encontraste?",
                    "Marta encuentra una llave mientras Pedro la sorprende en la cocina.",
                    24,
                ),
            )
