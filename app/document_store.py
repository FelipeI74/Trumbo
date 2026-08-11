from __future__ import annotations

import sqlite3
from typing import Any

from .document_projection import (
    audit_scene_parity,
    derive_scenes_from_document_lines,
    is_complete_scene_heading_text,
    project_document_from_scenes,
)


def _upsert_project_document(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    document_id: str,
) -> None:
    existing = connection.execute(
        """
        SELECT id
        FROM documents
        WHERE project_id = ?
        """,
        (project_id,),
    ).fetchone()

    if existing is None:
        connection.execute(
            """
            INSERT INTO documents(id, project_id)
            VALUES (?, ?)
            """,
            (document_id, project_id),
        )
        return

    connection.execute(
        """
        UPDATE documents
        SET
            id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE project_id = ?
        """,
        (document_id, project_id),
    )


def _existing_lines_for_document(
    connection: sqlite3.Connection,
    document_id: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            uuid,
            document_id,
            position,
            type,
            text,
            source_scene_id,
            source_line_index
        FROM document_lines
        WHERE document_id = ?
        ORDER BY position
        """,
        (document_id,),
    ).fetchall()

    return [dict(row) for row in rows]


def _replace_document_lines(
    connection: sqlite3.Connection,
    *,
    document_id: str,
    lines: list[dict[str, Any]],
) -> None:
    connection.execute(
        """
        DELETE FROM document_lines
        WHERE document_id = ?
        """,
        (document_id,),
    )

    if not lines:
        return

    connection.executemany(
        """
        INSERT INTO document_lines(
            uuid,
            document_id,
            position,
            type,
            text,
            source_scene_id,
            source_line_index
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                line["uuid"],
                line["document_id"],
                line["position"],
                line["type"],
                line["text"],
                line.get("source_scene_id"),
                line.get("source_line_index"),
            )
            for line in lines
        ],
    )


def sync_project_document_from_scenes(
    connection: sqlite3.Connection,
    *,
    project_id: int,
    scenes: list[dict[str, Any]],
) -> dict[str, Any]:
    previous_document_id_row = connection.execute(
        """
        SELECT id
        FROM documents
        WHERE project_id = ?
        """,
        (project_id,),
    ).fetchone()

    previous_document_id = previous_document_id_row["id"] if previous_document_id_row is not None else None
    existing_lines = (
        _existing_lines_for_document(connection, previous_document_id)
        if previous_document_id is not None
        else []
    )

    projection = project_document_from_scenes(
        project_id,
        scenes,
        existing_lines=existing_lines,
    )

    document = projection["document"]
    lines = projection["lines"]
    document_id = document["id"]

    _upsert_project_document(
        connection,
        project_id=project_id,
        document_id=document_id,
    )

    if previous_document_id is not None and previous_document_id != document_id:
        connection.execute(
            """
            DELETE FROM document_lines
            WHERE document_id = ?
            """,
            (previous_document_id,),
        )

    _replace_document_lines(
        connection,
        document_id=document_id,
        lines=lines,
    )

    rebuilt = derive_scenes_from_document_lines(lines)
    parity = audit_scene_parity(scenes, rebuilt["scenes"])
    all_scenes_are_derivable = all(
        is_complete_scene_heading_text(str(scene.get("heading") or ""))
        for scene in scenes
    )

    if not parity.ok and all_scenes_are_derivable:
        raise ValueError(" | ".join(parity.errors))

    return projection
