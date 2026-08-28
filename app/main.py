from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
from io import BytesIO, StringIO
import json
from pathlib import Path
import re
from typing import Any, List
import uuid

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from fastapi.responses import Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .database import connect, initialize, rows
from .document_projection import (
    derive_scenes_from_document_lines,
)
from .document_store import sync_project_document_from_scenes
from .domain import estimate_runtime, format_seconds, screenplay_summary
from .scheduling.optimizer import optimize_schedule
from .services.engine_analysis_adapter import analyze_scene_with_engine
from .storage import SecurityError, StoryboardStorage
from .schemas import (
    BreakdownItemCreate,
    BreakdownItemUpdate,
    NoteCreate,
    ProjectCreate,
    ProjectUpdate,
    SceneCreate,
    SceneUpdate,
    ShotCreate,
    ShotOut,
    ShotReorderRequest,
    ShotUpdate,
)


app = FastAPI(
    title="ADÜMN Alpha",
    version="0.3.1",
)

storage_service = StoryboardStorage()

def get_utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_project_and_scene(
    connection,
    project_id: int,
    scene_id: int,
) -> None:
    project = connection.execute(
        "SELECT id FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()

    if project is None:
        raise HTTPException(
            404,
            f"Proyecto {project_id} no existe",
        )

    scene = connection.execute(
        """
        SELECT id
        FROM scenes
        WHERE id = ?
          AND project_id = ?
        """,
        (scene_id, project_id),
    ).fetchone()

    if scene is None:
        raise HTTPException(
            404,
            f"Escena {scene_id} no encontrada en el proyecto {project_id}",
        )
    
STATIC_DIR = (
    Path(__file__)
    .resolve()
    .parent
    / "static"
)

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)

WORD_REGEX = re.compile(
    r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,}"
)

SPELLING_STOPWORDS = {
    "int",
    "ext",
    "dia",
    "noche",
    "flashforward",
}

BREAKDOWN_STATES = {
    "detected",
    "confirmed",
    "rejected",
}

# Matches INT./EXT./INT/EXT. etc.; period makes trailing space optional
_HEADING_PREFIX_RE = re.compile(
    r"^(INT\.?/EXT\.?|EXT\.?/INT\.?|I/E\.?|E/I\.?|INT\.?|EXT\.?)(?:(?<=\.)\s*|\s+)",
    re.IGNORECASE,
)

_HEADING_SPLIT_RE = re.compile(
    r"\s*[-–]\s*"
)

_KNOWN_TIME_OF_DAY = frozenset({
    "DIA",
    "DÍA",
    "NOCHE",
    "AMANECER",
    "ATARDECER",
    "TARDE",
})

_TIME_OF_DAY_SUFFIX_RE = re.compile(
    r"^(D[IÍ]A|NOCHE|AMANECER|ATARDECER|TARDE)(?:[\.,;:!?]+)?(?:\([^)]*\))?$"
)

# Transition cues sometimes misclassified as character lines; skip them in CSV
_CSV_TRANSITION_SKIP = frozenset({
    "CUT TO:", "FADE IN:", "FADE OUT:", "FADE TO:", "DISSOLVE TO:",
    "CORTE A:", "CORTE:", "FUNDIDO A:", "FUNDIDO:", "DISOLVENCIA A:",
    "MATCH CUT:", "JUMP CUT:", "IRIS OUT:", "IRIS IN:", "SMASH CUT TO:",
})


def serialize_semantic_lines(
    semantic_lines: list[Any] | None,
) -> str:
    """
    Convierte las líneas semánticas validadas por Pydantic
    en texto JSON para guardarlas en SQLite.
    """

    if not semantic_lines:
        return "[]"

    normalized: list[dict] = []

    for line in semantic_lines:
        if hasattr(line, "model_dump"):
            normalized.append(
                line.model_dump()
            )
        elif isinstance(line, dict):
            normalized.append(line)

    return json.dumps(
        normalized,
        ensure_ascii=False,
    )


def deserialize_semantic_lines(
    value: str | None,
) -> list[dict]:
    """
    Convierte el JSON guardado en SQLite nuevamente
    en una lista que el frontend pueda utilizar.
    """

    if not value:
        return []

    try:
        parsed = json.loads(value)
    except (
        json.JSONDecodeError,
        TypeError,
    ):
        return []

    if not isinstance(parsed, list):
        return []

    result: list[dict] = []

    valid_types = {
        "heading",
        "action",
        "character",
        "dialogue",
        "parenthetical",
        "transition",
    }

    for item in parsed:
        if not isinstance(item, dict):
            continue

        line_type = item.get("type")
        text = item.get("text", "")

        if (
            line_type not in valid_types
            or not isinstance(text, str)
        ):
            continue

        result.append(
            {
                "type": line_type,
                "text": text,
            }
        )

    return result


def scene_to_dict(
    scene: Any,
) -> dict:
    """
    Convierte una fila de SQLite en una escena apta
    para enviarse al navegador.
    """

    data = dict(scene)

    data["semantic_lines"] = (
        deserialize_semantic_lines(
            data.get("semantic_lines")
        )
    )

    return data


def project_scenes_for_projection(
    connection: Any,
    project_id: int,
) -> list[dict]:
    scene_rows = connection.execute(
        """
        SELECT *
        FROM scenes
        WHERE project_id = ?
        ORDER BY scene_number, id
        """,
        (project_id,),
    ).fetchall()

    return [scene_to_dict(scene_row) for scene_row in scene_rows]


def scene_with_metadata(
    connection: Any,
    scene_row: Any,
) -> dict:
    scene = scene_to_dict(scene_row)

    scene["notes"] = rows(
        connection,
        """
        SELECT *
        FROM notes
        WHERE scene_id = ?
        ORDER BY id DESC
        """,
        (scene["id"],),
    )

    scene["breakdown_items"] = rows(
        connection,
        """
        SELECT *
        FROM breakdown_items
        WHERE scene_id = ?
        ORDER BY category, name
        """,
        (scene["id"],),
    )

    return scene


def _document_lines_with_position(
    connection: Any,
    document_id: str,
) -> list[dict]:
    line_rows = connection.execute(
        """
        SELECT
            position,
            uuid,
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

    return [dict(line_row) for line_row in line_rows]


def normalize_breakdown_state(
    value: str,
) -> str:
    state = value.strip().lower()

    if state not in BREAKDOWN_STATES:
        raise HTTPException(
            400,
            "Estado de desglose inválido",
        )

    return state


def scene_lines_for_export(
    scene: dict,
) -> list[dict]:
    semantic_lines = deserialize_semantic_lines(
        scene.get("semantic_lines")
    )

    if semantic_lines:
        return semantic_lines

    heading = str(scene.get("heading") or "").strip()
    body = str(scene.get("body") or "")

    lines: list[dict] = []

    if heading:
        lines.append(
            {
                "type": "heading",
                "text": heading,
            }
        )

    for body_line in body.splitlines() or [""]:
        lines.append(
            {
                "type": "action",
                "text": body_line,
            }
        )

    return lines


def _parse_heading_fields(heading: str) -> dict:
    """Conservative best-effort split of a scene heading into its components."""
    text = heading.strip().upper()
    match = _HEADING_PREFIX_RE.match(text)
    if not match:
        return {
            "int_ext": "",
            "location": "",
            "sublocation": "",
            "time_of_day": "",
        }

    int_ext = match.group(1).upper()
    remainder = text[match.end():].strip()
    parts = [
        p.strip()
        for p in _HEADING_SPLIT_RE.split(remainder)
        if p.strip()
    ]

    if not parts:
        return {
            "int_ext": int_ext,
            "location": "",
            "sublocation": "",
            "time_of_day": "",
        }

    if len(parts) == 1:
        return {
            "int_ext": int_ext,
            "location": parts[0],
            "sublocation": "",
            "time_of_day": "",
        }

    time_of_day_match = _TIME_OF_DAY_SUFFIX_RE.match(
        parts[-1]
    )

    if time_of_day_match:
        return {
            "int_ext": int_ext,
            "location": parts[0],
            "sublocation": " - ".join(parts[1:-1]),
            "time_of_day": time_of_day_match.group(1),
        }

    return {
        "int_ext": int_ext,
        "location": parts[0],
        "sublocation": " - ".join(parts[1:]),
        "time_of_day": "",
    }


def spelling_candidates(
    scene: dict,
) -> list[tuple[str, str]]:
    heading = str(scene.get("heading") or "")
    body = str(scene.get("body") or "")
    source = f"{heading}\n{body}"

    results: list[tuple[str, str]] = []

    for match in WORD_REGEX.finditer(source):
        original = match.group(0)
        normalized = original.lower()

        if normalized in SPELLING_STOPWORDS:
            continue

        if original.isupper() and len(original) <= 4:
            continue

        results.append((original, normalized))

    return results


@app.on_event("startup")
def startup() -> None:
    initialize()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html"
    )


@app.get("/api/projects")
def list_projects() -> list[dict]:
    with connect() as connection:
        return rows(
            connection,
            """
            SELECT *
            FROM projects
            ORDER BY updated_at DESC, id DESC
            """,
        )


@app.post("/api/projects")
def create_project(
    payload: ProjectCreate,
) -> dict:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO projects(
                title,
                format
            )
            VALUES (?, ?)
            """,
            (
                payload.title.strip(),
                payload.format.strip(),
            ),
        )

        project_id = cursor.lastrowid

        project = connection.execute(
            """
            SELECT *
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        return dict(project)


@app.patch("/api/projects/{project_id}")
def update_project(
    project_id: int,
    payload: ProjectUpdate,
) -> dict:
    data = payload.model_dump(
        exclude_none=True
    )

    if not data:
        raise HTTPException(
            400,
            "No hay cambios",
        )

    assignments = ", ".join(
        f"{key} = ?"
        for key in data
    )

    values = [
        value.strip()
        if isinstance(value, str)
        else value
        for value in data.values()
    ]

    values.append(project_id)

    with connect() as connection:
        cursor = connection.execute(
            f"""
            UPDATE projects
            SET
                {assignments},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            tuple(values),
        )

        if cursor.rowcount == 0:
            raise HTTPException(
                404,
                "Proyecto no encontrado",
            )

        project = connection.execute(
            """
            SELECT *
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        return dict(project)


@app.get("/api/projects/{project_id}")
def get_project(
    project_id: int,
) -> dict:
    with connect() as connection:
        project = connection.execute(
            """
            SELECT *
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        if project is None:
            raise HTTPException(
                404,
                "Proyecto no encontrado",
            )

        scene_rows = connection.execute(
            """
            SELECT *
            FROM scenes
            WHERE project_id = ?
            ORDER BY scene_number
            """,
            (project_id,),
        ).fetchall()

        scenes: list[dict] = []

        for scene_row in scene_rows:
            scenes.append(
                scene_with_metadata(
                    connection,
                    scene_row,
                )
            )

        return {
            "project": dict(project),
            "scenes": scenes,
        }


@app.get("/api/projects/{project_id}/characters")
def list_project_characters(
    project_id: int,
) -> dict:
    with connect() as connection:
        project_exists = connection.execute(
            """
            SELECT 1
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        if project_exists is None:
            raise HTTPException(
                404,
                "Proyecto no encontrado",
            )

        scene_rows = connection.execute(
            """
            SELECT scene_number, semantic_lines
            FROM scenes
            WHERE project_id = ?
            ORDER BY scene_number
            """,
            (project_id,),
        ).fetchall()

    grouped: dict[str, dict] = {}

    for scene in scene_rows:
        scene_number = int(scene["scene_number"])
        seen_in_scene: set[str] = set()

        for line in deserialize_semantic_lines(scene["semantic_lines"]):
            if line.get("type") != "character":
                continue

            name = str(line.get("text") or "").strip()
            key = name.casefold()

            if not name or key in seen_in_scene:
                continue

            seen_in_scene.add(key)
            character = grouped.setdefault(
                key,
                {
                    "name": name,
                    "scene_numbers": [],
                },
            )

            if scene_number not in character["scene_numbers"]:
                character["scene_numbers"].append(scene_number)

    characters = [
        {
            "name": character["name"],
            "scene_count": len(character["scene_numbers"]),
            "first_scene": character["scene_numbers"][0],
            "scene_numbers": character["scene_numbers"],
        }
        for character in grouped.values()
    ]
    characters.sort(key=lambda character: character["name"].casefold())

    return {"characters": characters}


@app.get("/api/projects/{project_id}/locations")
def list_project_locations(
    project_id: int,
) -> dict:
    with connect() as connection:
        project_exists = connection.execute(
            """
            SELECT 1
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        if project_exists is None:
            raise HTTPException(
                404,
                "Proyecto no encontrado",
            )

        scene_rows = connection.execute(
            """
            SELECT scene_number, heading
            FROM scenes
            WHERE project_id = ?
            ORDER BY scene_number
            """,
            (project_id,),
        ).fetchall()

    grouped: dict[str, dict] = {}

    for scene in scene_rows:
        fields = _parse_heading_fields(
            str(scene["heading"] or "")
        )
        location = fields["location"]
        sublocation = fields["sublocation"]

        if not location:
            continue

        name = (
            f"{location} - {sublocation}"
            if sublocation
            else location
        )
        key = name.casefold()
        scene_number = int(scene["scene_number"])
        location_data = grouped.setdefault(
            key,
            {
                "name": name,
                "scene_numbers": [],
            },
        )

        if scene_number not in location_data["scene_numbers"]:
            location_data["scene_numbers"].append(scene_number)

    locations = [
        {
            "name": location["name"],
            "scene_count": len(location["scene_numbers"]),
            "first_scene": location["scene_numbers"][0],
            "scene_numbers": location["scene_numbers"],
        }
        for location in grouped.values()
    ]
    locations.sort(key=lambda location: location["name"].casefold())

    return {"locations": locations}


@app.get("/api/projects/{project_id}/resources")
def list_project_resources(
    project_id: int,
) -> dict:
    with connect() as connection:
        project_exists = connection.execute(
            """
            SELECT 1
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        if project_exists is None:
            raise HTTPException(
                404,
                "Proyecto no encontrado",
            )

        resource_rows = connection.execute(
            """
            SELECT
                breakdown_items.name,
                breakdown_items.category,
                scenes.scene_number
            FROM breakdown_items
            JOIN scenes
                ON scenes.id = breakdown_items.scene_id
            WHERE scenes.project_id = ?
            ORDER BY scenes.scene_number, breakdown_items.name, breakdown_items.category
            """,
            (project_id,),
        ).fetchall()

    grouped: dict[tuple[str, str], dict] = {}
    seen_in_scene: set[tuple[int, str, str]] = set()

    for resource in resource_rows:
        name = str(resource["name"] or "").strip()
        category = str(resource["category"] or "").strip()
        scene_number = int(resource["scene_number"])
        key = (name.casefold(), category.casefold())
        scene_key = (scene_number, *key)

        if not name or not category or scene_key in seen_in_scene:
            continue

        seen_in_scene.add(scene_key)
        resource_data = grouped.setdefault(
            key,
            {
                "name": name,
                "category": category,
                "scene_numbers": [],
            },
        )

        if scene_number not in resource_data["scene_numbers"]:
            resource_data["scene_numbers"].append(scene_number)

    resources = [
        {
            "name": resource["name"],
            "category": resource["category"],
            "scene_count": len(resource["scene_numbers"]),
            "first_scene": resource["scene_numbers"][0],
            "scene_numbers": resource["scene_numbers"],
        }
        for resource in grouped.values()
    ]
    resources.sort(
        key=lambda resource: (
            resource["name"].casefold(),
            resource["category"].casefold(),
        )
    )

    return {"resources": resources}


def _build_project_scheduling_input(
    project_id: int,
) -> dict:
    with connect() as connection:
        project_exists = connection.execute(
            """
            SELECT 1
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        if project_exists is None:
            raise HTTPException(
                404,
                "Proyecto no encontrado",
            )

        scene_rows = connection.execute(
            """
            SELECT
                id,
                scene_number,
                heading,
                runtime_seconds,
                semantic_lines
            FROM scenes
            WHERE project_id = ?
            ORDER BY scene_number, id
            """,
            (project_id,),
        ).fetchall()

        resource_rows = connection.execute(
            """
            SELECT
                breakdown_items.scene_id,
                breakdown_items.category,
                breakdown_items.name
            FROM breakdown_items
            JOIN scenes
                ON scenes.id = breakdown_items.scene_id
            WHERE scenes.project_id = ?
            ORDER BY scenes.scene_number, breakdown_items.name
            """,
            (project_id,),
        ).fetchall()

    resources_by_scene: dict[int, list[str]] = {}
    seen_resources_by_scene: dict[int, set[str]] = {}
    scene_cast_by_scene: dict[int, list[str]] = {}
    seen_scene_cast_by_scene: dict[int, set[str]] = {}

    for resource_row in resource_rows:
        scene_id = int(resource_row["scene_id"])
        resource_category = str(resource_row["category"] or "").strip()
        resource_name = str(resource_row["name"] or "").strip()

        if not resource_name:
            continue

        resource_key = resource_name.casefold()
        if resource_category.casefold() in {"cast", "scene_cast"}:
            seen_scene_cast = seen_scene_cast_by_scene.setdefault(
                scene_id,
                set(),
            )

            if resource_key in seen_scene_cast:
                continue

            seen_scene_cast.add(resource_key)
            scene_cast_by_scene.setdefault(
                scene_id,
                [],
            ).append(resource_name)
            continue

        seen_resources = seen_resources_by_scene.setdefault(
            scene_id,
            set(),
        )

        if resource_key in seen_resources:
            continue

        seen_resources.add(resource_key)
        resources_by_scene.setdefault(
            scene_id,
            [],
        ).append(resource_name)

    scenes: list[dict] = []

    for script_order, scene_row in enumerate(
        scene_rows,
        start=1,
    ):
        scene_id = int(scene_row["id"])
        heading_fields = _parse_heading_fields(
            str(scene_row["heading"] or "")
        )
        seen_characters: set[str] = set()
        characters: list[str] = []

        for line in deserialize_semantic_lines(
            scene_row["semantic_lines"]
        ):
            if line.get("type") != "character":
                continue

            name = str(line.get("text") or "").strip()
            key = name.casefold()

            if not name or key in seen_characters:
                continue

            seen_characters.add(key)
            characters.append(name)

        scene_cast = list(characters)
        seen_scene_cast = {name.strip().casefold() for name in scene_cast}
        for name in scene_cast_by_scene.get(scene_id, []):
            key = name.strip().casefold()
            if not key or key in seen_scene_cast:
                continue
            seen_scene_cast.add(key)
            scene_cast.append(name)

        scenes.append(
            {
                "scene_id": scene_id,
                "scene_number": int(scene_row["scene_number"]),
                "script_order": script_order,
                "int_ext": heading_fields["int_ext"],
                "location": heading_fields["location"],
                "sublocation": heading_fields["sublocation"],
                "time_of_day": heading_fields["time_of_day"],
                "runtime_seconds": int(scene_row["runtime_seconds"] or 0),
                "characters": characters,
                "scene_cast": scene_cast,
                "resources": resources_by_scene.get(scene_id, []),
            }
        )

    return {"scenes": scenes}


@app.get("/api/projects/{project_id}/scheduling-input")
def get_project_scheduling_input(
    project_id: int,
) -> dict:
    return _build_project_scheduling_input(
        project_id
    )


@app.get("/api/projects/{project_id}/schedule-preview")
def get_project_schedule_preview(
    project_id: int,
    shoot_rate_seconds: int = Query(420),
) -> dict:
    scheduling_input = _build_project_scheduling_input(
        project_id
    )

    return optimize_schedule(
        scheduling_input["scenes"],
        shoot_rate_seconds=shoot_rate_seconds,
    )


@app.get("/api/projects/{project_id}/document")
def get_project_document(
    project_id: int,
) -> dict:
    with connect() as connection:
        project = connection.execute(
            """
            SELECT *
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        if project is None:
            raise HTTPException(
                404,
                "Proyecto no encontrado",
            )

        document = connection.execute(
            """
            SELECT
                id,
                project_id,
                created_at,
                updated_at
            FROM documents
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()

        if document is None:
            raise HTTPException(
                404,
                "El proyecto aún no tiene un documento generado. Guarda una escena para crearlo.",
            )

        ordered_lines = _document_lines_with_position(
            connection,
            document["id"],
        )

        derived_projection = derive_scenes_from_document_lines(
            ordered_lines
        )

        persisted_scene_rows = connection.execute(
            """
            SELECT *
            FROM scenes
            WHERE project_id = ?
            ORDER BY scene_number, id
            """,
            (project_id,),
        ).fetchall()

        persisted_scenes_by_id = {
            scene_row["id"]: scene_with_metadata(
                connection,
                scene_row,
            )
            for scene_row in persisted_scene_rows
        }

        derived_scenes: list[dict] = []
        inconsistencies: list[dict] = []

        for index, derived_scene in enumerate(
            derived_projection["scenes"]
        ):
            chunk_index = index + 1
            origin_ids = set(
                derived_scene.get("source_scene_ids")
                or []
            )

            has_single_non_null_origin = (
                len(origin_ids) == 1
                and next(iter(origin_ids), None) is not None
            )

            if has_single_non_null_origin:
                source_scene_id = next(iter(origin_ids))
                persisted_scene = persisted_scenes_by_id.get(
                    source_scene_id
                )

                if persisted_scene is not None:
                    derived_scenes.append(
                        {
                            **persisted_scene,
                            "scene_number": derived_scene["scene_number"],
                            "heading": derived_scene["heading"],
                            "body": derived_scene["body"],
                            "semantic_lines": derived_scene["semantic_lines"],
                        }
                    )
                    continue

            derived_scenes.append(
                {
                    "id": None,
                    "scene_number": derived_scene["scene_number"],
                    "heading": derived_scene["heading"],
                    "body": derived_scene["body"],
                    "semantic_lines": derived_scene["semantic_lines"],
                    "synopsis": None,
                    "runtime_seconds": None,
                    "notes": [],
                    "breakdown_items": [],
                    "structural_conflict": True,
                }
            )

            inconsistencies.append(
                {
                    "type": "mixed_or_missing_source_scene_id",
                    "scene_number": chunk_index,
                    "source_scene_ids": sorted(
                        [
                            source_scene_id
                            for source_scene_id in origin_ids
                            if source_scene_id is not None
                        ]
                    ),
                    "has_null_source_scene_id": None in origin_ids,
                }
            )

        return {
            "project": dict(project),
            "document": dict(document),
            "lines": [
                {
                    "uuid": line["uuid"],
                    "type": line["type"],
                    "text": line["text"],
                    "source_scene_id": line["source_scene_id"],
                    "source_line_index": line["source_line_index"],
                }
                for line in ordered_lines
            ],
            "derived_scenes": derived_scenes,
            "inconsistencies": inconsistencies,
        }


@app.post("/api/projects/{project_id}/scenes")
def create_scene(
    project_id: int,
    payload: SceneCreate,
) -> dict:
    runtime = estimate_runtime(
        payload.body
    )

    semantic_json = (
        serialize_semantic_lines(
            payload.semantic_lines
        )
    )

    with connect() as connection:
        exists = connection.execute(
            """
            SELECT 1
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        if exists is None:
            raise HTTPException(
                404,
                "Proyecto no encontrado",
            )

        next_number = connection.execute(
            """
            SELECT
                COALESCE(
                    MAX(scene_number),
                    0
                ) + 1
            FROM scenes
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()[0]

        cursor = connection.execute(
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
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                next_number,
                payload.heading,
                payload.body,
                semantic_json,
                payload.synopsis,
                runtime.seconds,
            ),
        )

        projected_scenes = project_scenes_for_projection(
            connection,
            project_id,
        )

        sync_project_document_from_scenes(
            connection,
            project_id=project_id,
            scenes=projected_scenes,
        )

        scene = connection.execute(
            """
            SELECT *
            FROM scenes
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

        result = scene_to_dict(scene)

        result["notes"] = []
        result["breakdown_items"] = []

        return result


@app.patch("/api/scenes/{scene_id}")
def update_scene(
    scene_id: int,
    payload: SceneUpdate,
) -> dict:
    data = payload.model_dump(
        exclude_none=True
    )

    if not data:
        raise HTTPException(
            400,
            "No hay cambios",
        )

    with connect() as connection:
        current = connection.execute(
            """
            SELECT *
            FROM scenes
            WHERE id = ?
            """,
            (scene_id,),
        ).fetchone()

        if current is None:
            raise HTTPException(
                404,
                "Escena no encontrada",
            )

        new_heading = data.get(
            "heading",
            current["heading"],
        )

        new_body = data.get(
            "body",
            current["body"],
        )

        current_semantic_json = (
            current["semantic_lines"]
            or "[]"
        )

        if "semantic_lines" in data:
            new_semantic_json = (
                serialize_semantic_lines(
                    data["semantic_lines"]
                )
            )
        else:
            new_semantic_json = (
                current_semantic_json
            )

        content_changed = any(
            (
                new_heading
                != current["heading"],

                new_body
                != current["body"],

                new_semantic_json
                != current_semantic_json,
            )
        )

        if content_changed:
            connection.execute(
                """
                INSERT INTO revisions(
                    scene_id,
                    previous_heading,
                    previous_body,
                    previous_semantic_lines
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    scene_id,
                    current["heading"],
                    current["body"],
                    current_semantic_json,
                ),
            )

        data["semantic_lines"] = (
            new_semantic_json
        )

        data["runtime_seconds"] = (
            estimate_runtime(
                new_body
            ).seconds
        )

        assignments = ", ".join(
            f"{key} = ?"
            for key in data
        )

        values = (
            list(data.values())
            + [scene_id]
        )

        connection.execute(
            f"""
            UPDATE scenes
            SET
                {assignments},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            tuple(values),
        )

        connection.execute(
            """
            UPDATE projects
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = (
                SELECT project_id
                FROM scenes
                WHERE id = ?
            )
            """,
            (scene_id,),
        )

        projected_scenes = project_scenes_for_projection(
            connection,
            current["project_id"],
        )

        sync_project_document_from_scenes(
            connection,
            project_id=current["project_id"],
            scenes=projected_scenes,
        )

        updated = connection.execute(
            """
            SELECT *
            FROM scenes
            WHERE id = ?
            """,
            (scene_id,),
        ).fetchone()

        return scene_to_dict(updated)


@app.delete("/api/scenes/{scene_id}")
def delete_scene(
    scene_id: int,
) -> dict:
    with connect() as connection:
        current = connection.execute(
            """
            SELECT id, project_id
            FROM scenes
            WHERE id = ?
            """,
            (scene_id,),
        ).fetchone()

        if current is None:
            raise HTTPException(
                404,
                "Escena no encontrada",
            )

        project_id = current["project_id"]

        connection.execute(
            """
            DELETE FROM scenes
            WHERE id = ?
            """,
            (scene_id,),
        )

        remaining_ids = connection.execute(
            """
            SELECT id
            FROM scenes
            WHERE project_id = ?
            ORDER BY scene_number, id
            """,
            (project_id,),
        ).fetchall()

        for index, row in enumerate(
            remaining_ids,
            start=1,
        ):
            connection.execute(
                """
                UPDATE scenes
                SET
                    scene_number = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    index,
                    row["id"],
                ),
            )

        connection.execute(
            """
            UPDATE projects
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (project_id,),
        )

        projected_scenes = project_scenes_for_projection(
            connection,
            project_id,
        )

        sync_project_document_from_scenes(
            connection,
            project_id=project_id,
            scenes=projected_scenes,
        )

        return {
            "ok": True,
            "deleted_scene_id": scene_id,
            "project_id": project_id,
        }


@app.get("/api/scenes/{scene_id}/analysis")
def analyze_scene(
    scene_id: int,
) -> dict:
    with connect() as connection:
        scene = connection.execute(
            """
            SELECT
                heading,
                body
            FROM scenes
            WHERE id = ?
            """,
            (scene_id,),
        ).fetchone()

        if scene is None:
            raise HTTPException(
                404,
                "Escena no encontrada",
            )

        return analyze_scene_with_engine(
            scene_id=scene_id,
            heading=scene["heading"],
            body=scene["body"],
        )


@app.post("/api/scenes/{scene_id}/notes")
def add_note(
    scene_id: int,
    payload: NoteCreate,
) -> dict:
    with connect() as connection:
        scene_exists = connection.execute(
            """
            SELECT 1
            FROM scenes
            WHERE id = ?
            """,
            (scene_id,),
        ).fetchone()

        if scene_exists is None:
            raise HTTPException(
                404,
                "Escena no encontrada",
            )

        cursor = connection.execute(
            """
            INSERT INTO notes(
                scene_id,
                category,
                body
            )
            VALUES (?, ?, ?)
            """,
            (
                scene_id,
                payload.category.strip(),
                payload.body.strip(),
            ),
        )

        note = connection.execute(
            """
            SELECT *
            FROM notes
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

        return dict(note)


@app.post("/api/scenes/{scene_id}/breakdown")
def add_breakdown_item(
    scene_id: int,
    payload: BreakdownItemCreate,
) -> dict:
    with connect() as connection:
        scene_exists = connection.execute(
            """
            SELECT 1
            FROM scenes
            WHERE id = ?
            """,
            (scene_id,),
        ).fetchone()

        if scene_exists is None:
            raise HTTPException(
                404,
                "Escena no encontrada",
            )

        cursor = connection.execute(
            """
            INSERT INTO breakdown_items(
                scene_id,
                category,
                name,
                source,
                state
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                scene_id,
                payload.category.strip(),
                payload.name.strip(),
                payload.source.strip(),
                normalize_breakdown_state(
                    payload.state
                ),
            ),
        )

        item = connection.execute(
            """
            SELECT *
            FROM breakdown_items
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

        return dict(item)


@app.patch("/api/breakdown/{item_id}")
def update_breakdown_item(
    item_id: int,
    payload: BreakdownItemUpdate,
) -> dict:
    data = payload.model_dump(
        exclude_none=True
    )

    if not data:
        raise HTTPException(
            400,
            "No hay cambios",
        )

    if "state" in data:
        data["state"] = normalize_breakdown_state(
            data["state"]
        )

    values = []

    for key, value in data.items():
        if isinstance(value, str):
            values.append(value.strip())
        else:
            values.append(value)

    assignments = ", ".join(
        f"{key} = ?"
        for key in data
    )

    with connect() as connection:
        cursor = connection.execute(
            f"""
            UPDATE breakdown_items
            SET {assignments}
            WHERE id = ?
            """,
            tuple(values + [item_id]),
        )

        if cursor.rowcount == 0:
            raise HTTPException(
                404,
                "Elemento de desglose no encontrado",
            )

        row = connection.execute(
            """
            SELECT *
            FROM breakdown_items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()

        return dict(row)


@app.get("/api/scenes/{scene_id}/breakdown")
def list_scene_breakdown(
    scene_id: int,
    category: str | None = Query(default=None),
    state: str | None = Query(default=None),
) -> list[dict]:
    filters = ["scene_id = ?"]
    params: list[Any] = [scene_id]

    if category:
        filters.append("category = ?")
        params.append(category.strip())

    if state:
        normalized_state = normalize_breakdown_state(
            state
        )
        filters.append("state = ?")
        params.append(normalized_state)

    where_clause = " AND ".join(filters)

    with connect() as connection:
        return rows(
            connection,
            f"""
            SELECT *
            FROM breakdown_items
            WHERE {where_clause}
            ORDER BY category, name
            """,
            tuple(params),
        )


@app.get("/api/scenes/{scene_id}/spelling")
def scene_spelling_review(
    scene_id: int,
) -> dict:
    with connect() as connection:
        scene = connection.execute(
            """
            SELECT id, heading, body, semantic_lines
            FROM scenes
            WHERE id = ?
            """,
            (scene_id,),
        ).fetchone()

        if scene is None:
            raise HTTPException(
                404,
                "Escena no encontrada",
            )

    try:
        from spellchecker import SpellChecker
    except ImportError as error:
        raise HTTPException(
            500,
            "No está disponible el corrector ortográfico",
        ) from error

    scene_data = dict(scene)
    candidates = spelling_candidates(scene_data)

    if not candidates:
        return {
            "scene_id": scene_id,
            "total_words": 0,
            "misspellings": [],
        }

    counter = Counter(
        normalized for _, normalized in candidates
    )

    checker = SpellChecker(language="es")
    semantic_lines = deserialize_semantic_lines(
        scene_data.get("semantic_lines")
    )
    cue_words = {
        word.lower()
        for line in semantic_lines
        if line.get("type") == "character"
        for word, _ in spelling_candidates({"body": line.get("text")})
    }
    unknown = {
        word
        for word in checker.unknown(counter.keys())
        if word not in cue_words and not checker.known([word])
    }

    # The Spanish frequency list omits some regular inflections. Keep words
    # whose candidate preserves the stem and supplies a normal ending.
    inflection_endings = (
        "a",
        "e",
        "o",
        "as",
        "es",
        "os",
        "an",
        "en",
        "amos",
        "emos",
        "imos",
    )
    filtered_unknown = set()

    for word in unknown:
        if not word.endswith(inflection_endings):
            filtered_unknown.add(word)
            continue

        stem = word[:-1]
        if word.endswith(("as", "es", "os", "an", "en")):
            stem = word[:-2]

        candidates_for_word = checker.candidates(word) or set()
        if not any(
            candidate.startswith(stem)
            and len(candidate) <= len(word) + 3
            for candidate in candidates_for_word
        ):
            filtered_unknown.add(word)

    unknown = filtered_unknown

    misspellings: list[dict] = []

    for word in sorted(
        unknown,
        key=lambda item: (-counter[item], item),
    ):
        suggestions = list(
            checker.candidates(word) or []
        )

        misspellings.append(
            {
                "word": word,
                "count": counter[word],
                "best": checker.correction(word),
                "suggestions": suggestions[:5],
            }
        )

    return {
        "scene_id": scene_id,
        "total_words": len(candidates),
        "misspellings": misspellings,
    }


@app.get("/api/projects/{project_id}/export/pdf")
def export_project_pdf(
    project_id: int,
):
    with connect() as connection:
        project = connection.execute(
            """
            SELECT *
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        if project is None:
            raise HTTPException(
                404,
                "Proyecto no encontrado",
            )

        scenes = rows(
            connection,
            """
            SELECT *
            FROM scenes
            WHERE project_id = ?
            ORDER BY scene_number
            """,
            (project_id,),
        )

    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.utils import simpleSplit
        from reportlab.pdfgen import canvas
    except ImportError as error:
        raise HTTPException(
            500,
            "No está disponible el exportador PDF",
        ) from error

    buffer = BytesIO()
    pdf = canvas.Canvas(
        buffer,
        pagesize=LETTER,
        pageCompression=0,
    )

    width, height = LETTER
    margin_left = 1.5 * 72
    margin_right = 1.0 * 72
    margin_top = 1.0 * 72
    margin_bottom = 1.0 * 72
    line_height = 14
    y = height - margin_top
    page_number = 1

    def finish_page() -> None:
        nonlocal page_number
        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Courier", 12)
        pdf.drawCentredString(width / 2, 36, str(page_number))
        pdf.showPage()
        page_number += 1

    def wrapped_lines(text: str, indent: float) -> list[str]:
        return simpleSplit(
            text,
            "Courier",
            12,
            width - margin_left - margin_right - indent,
        ) or [""]

    def ensure_space(lines_needed: int = 1) -> None:
        nonlocal y
        min_y = margin_bottom + (lines_needed * line_height)

        if y <= min_y:
            finish_page()
            y = height - margin_top

    title = str(project["title"])
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont("Courier", 12)
    pdf.drawString(margin_left, y, title)
    y -= line_height * 2

    pdf.setFont("Courier", 12)
    pdf.drawString(
        margin_left,
        y,
        "Exportado desde ADÜMN Alpha",
    )
    y -= line_height * 2

    for scene in scenes:
        scene_heading = (
            str(scene.get("heading") or "").strip()
            or "Sin encabezado"
        )

        ensure_space(4)

        pdf.setFont("Courier", 12)
        pdf.drawString(
            margin_left,
            y,
            f"ESCENA {scene['scene_number']}: {scene_heading}".upper(),
        )
        y -= line_height * 2

        lines = scene_lines_for_export(scene)

        for line_index, line in enumerate(lines):
            line_type = line.get("type") or "action"
            text = str(line.get("text") or "")

            if not text.strip():
                y -= line_height
                continue

            if line_type == "heading":
                indent = 0
                rendered = text.upper()
            elif line_type == "character":
                indent = 3.7 * 72 - margin_left
                rendered = text.upper()
            elif line_type == "dialogue":
                indent = 2.5 * 72 - margin_left
                rendered = text
            elif line_type == "parenthetical":
                indent = 3.1 * 72 - margin_left
                rendered = text
            elif line_type == "transition":
                indent = 0
                rendered = text.upper()
            else:
                indent = 0
                rendered = text

            wrapped = wrapped_lines(rendered, indent)

            if line_type == "character":
                next_types = [
                    next_line.get("type")
                    for next_line in lines[line_index + 1 : line_index + 3]
                ]
                opening_lines = 1 + int("parenthetical" in next_types)
                if "dialogue" in next_types:
                    opening_lines += 1
                ensure_space(opening_lines + 1)

            ensure_space(len(wrapped) + 1)

            pdf.setFont("Courier", 12)
            x = (
                width - margin_right - pdf.stringWidth(rendered, "Courier", 12)
                if line_type == "transition"
                else margin_left + indent
            )
            for chunk in wrapped:
                pdf.drawString(
                    x,
                    y,
                    chunk,
                )
                y -= line_height

            y -= 2

        y -= line_height

    finish_page()
    pdf.save()
    buffer.seek(0)

    safe_name = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        title,
    ).strip("_") or "adumn_project"

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{safe_name}.pdf"'
            )
        },
    )


@app.get("/api/projects/{project_id}/export/csv")
def export_project_csv(
    project_id: int,
):
    with connect() as connection:
        project = connection.execute(
            """
            SELECT *
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        if project is None:
            raise HTTPException(
                404,
                "Proyecto no encontrado",
            )

        scene_rows = connection.execute(
            """
            SELECT *
            FROM scenes
            WHERE project_id = ?
            ORDER BY scene_number
            """,
            (project_id,),
        ).fetchall()

        scenes = [
            scene_with_metadata(connection, row)
            for row in scene_rows
        ]

    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([
        "Escena", "Heading", "INT/EXT", "Locación", "Sublocación",
        "Tiempo", "Acción", "Sinopsis", "Personajes",
        "Props", "Vestuario", "Duración", "Notas",
    ])

    for scene in scenes:
        heading = str(scene.get("heading") or "").strip()
        fields = _parse_heading_fields(heading)

        # scene_with_metadata already deserializes semantic_lines to list[dict]
        semantic_lines = scene.get("semantic_lines") or []

        action_text = " / ".join(
            line["text"]
            for line in semantic_lines
            if line.get("type") == "action" and line.get("text", "").strip()
        )

        seen: set[str] = set()
        characters: list[str] = []
        for line in semantic_lines:
            if line.get("type") == "character":
                name = re.sub(
                    r"\s*\([^)]*\)\s*$", "", line["text"]
                ).strip().upper()
                if name and name not in seen and name not in _CSV_TRANSITION_SKIP:
                    seen.add(name)
                    characters.append(name)

        breakdown = scene.get("breakdown_items") or []
        props = [
            item["name"]
            for item in breakdown
            if item.get("category") == "prop"
        ]
        wardrobe = [
            item["name"]
            for item in breakdown
            if item.get("category") == "wardrobe"
        ]

        notes_text = " | ".join(
            str(note.get("body") or "").strip()
            for note in (scene.get("notes") or [])
            if str(note.get("body") or "").strip()
        )

        writer.writerow([
            scene.get("scene_number", ""),
            heading,
            fields["int_ext"],
            fields["location"],
            fields["sublocation"],
            fields["time_of_day"],
            action_text,
            str(scene.get("synopsis") or "").strip(),
            ", ".join(characters),
            ", ".join(props),
            ", ".join(wardrobe),
            format_seconds(scene.get("runtime_seconds") or 0),
            notes_text,
        ])

    # Explicit BOM bytes + UTF-8 content; avoids StreamingResponse re-encoding
    csv_bytes = b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")

    safe_name = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        str(project["title"]),
    ).strip("_") or "adumn_project"

    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{safe_name}_desglose.csv"'
            )
        },
    )


@app.get("/api/projects/{project_id}/runtime")
def project_runtime(
    project_id: int,
) -> dict:
    with connect() as connection:
        project_exists = connection.execute(
            """
            SELECT 1
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        if project_exists is None:
            raise HTTPException(
                404,
                "Proyecto no encontrado",
            )

        total = connection.execute(
            """
            SELECT
                COALESCE(
                    SUM(runtime_seconds),
                    0
                )
            FROM scenes
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()[0]

        minutes, seconds = divmod(
            total,
            60,
        )

        return {
            "seconds": total,
            "runtime_seconds": total,
            "formatted": (
                f"{minutes:02d}:"
                f"{seconds:02d}"
            ),
        }


@app.get(
    "/api/projects/{project_id}/scenes/{scene_id}/shots",
    response_model=List[ShotOut],
)
def list_shots(
    project_id: int,
    scene_id: int,
):
    with connect() as connection:
        _validate_project_and_scene(
            connection,
            project_id,
            scene_id,
        )

        shot_rows = connection.execute(
            """
            SELECT *
            FROM shots
            WHERE project_id = ?
              AND scene_id = ?
              AND is_archived = 0
            ORDER BY sort_order, created_at
            """,
            (project_id, scene_id),
        ).fetchall()

        return [
            {
                **dict(row),
                "has_image": bool(row["storage_key"]),
                "image_url": (
                   f"/api/projects/{project_id}/storyboard/shots/{row['id']}/image"
                    if row["storage_key"]
                    else None
                ),
            }
            for row in shot_rows
        ]
@app.post(
    "/api/projects/{project_id}/scenes/{scene_id}/shots",
    response_model=ShotOut,
    status_code=status.HTTP_201_CREATED,
)
def create_shot(
    project_id: int,
    scene_id: int,
    payload: ShotCreate,
):
    with connect() as connection:
        _validate_project_and_scene(
            connection,
            project_id,
            scene_id,
        )

        next_order = connection.execute(
            """
            SELECT COALESCE(MAX(sort_order), 0) + 1
            FROM shots
            WHERE project_id = ?
              AND scene_id = ?
              AND is_archived = 0
            """,
            (project_id, scene_id),
        ).fetchone()[0]

        shot_id = str(uuid.uuid4())
        now = get_utc_now_iso()

        connection.execute(
            """
            INSERT INTO shots (
                id,
                project_id,
                scene_id,
                sort_order,
                shot_type,
                camera_movement,
                description,
                notes,
                storage_key,
                is_archived,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', 0, ?, ?)
            """,
            (
                shot_id,
                project_id,
                scene_id,
                next_order,
                payload.shot_type,
                payload.camera_movement,
                payload.description,
                payload.notes,
                now,
                now,
            ),
        )
        connection.commit()

        return {
            "id": shot_id,
            "project_id": project_id,
            "scene_id": scene_id,
            "sort_order": next_order,
            "shot_type": payload.shot_type,
            "camera_movement": payload.camera_movement,
            "description": payload.description,
            "notes": payload.notes,
            "storage_key": "",
            "has_image": False,
            "image_url": None,
            "is_archived": 0,
            "created_at": now,
            "updated_at": now,
        }
@app.patch(
    "/api/projects/{project_id}/shots/{shot_id}",
    response_model=ShotOut,
)
def update_shot_metadata(
    project_id: int,
    shot_id: str,
    payload: ShotUpdate,
):
    with connect() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM shots
            WHERE id = ?
              AND project_id = ?
              AND is_archived = 0
            """,
            (shot_id, project_id),
        ).fetchone()

        if row is None:
            raise HTTPException(
                404,
                "Shot no encontrado",
            )

        shot = dict(row)
        updates = []
        values = []

        for field in (
            "shot_type",
            "camera_movement",
            "description",
            "notes",
        ):
            value = getattr(payload, field)
            if value is not None:
                updates.append(f"{field} = ?")
                values.append(value)
                shot[field] = value

        if updates:
            now = get_utc_now_iso()
            updates.append("updated_at = ?")
            values.append(now)
            shot["updated_at"] = now

            values.extend([shot_id, project_id])

            connection.execute(
                f"""
                UPDATE shots
                SET {", ".join(updates)}
                WHERE id = ?
                  AND project_id = ?
                """,
                values,
            )
            connection.commit()

        shot["has_image"] = bool(shot["storage_key"])
        shot["image_url"] = (
           f"/api/projects/{project_id}/storyboard/shots/{shot_id}/image"
            if shot["storage_key"]
            else None
        )

        return shot
@app.put(
    "/api/projects/{project_id}/shots/{shot_id}/image"
)
async def upload_shot_image(
    project_id: int,
    shot_id: str,
    request: Request,
):
    with connect() as connection:
        row = connection.execute(
            """
            SELECT storage_key
            FROM shots
            WHERE id = ?
              AND project_id = ?
              AND is_archived = 0
            """,
            (shot_id, project_id),
        ).fetchone()

        if row is None:
            raise HTTPException(
                404,
                "Shot no encontrado",
            )

        image_bytes = await request.body()

        if not image_bytes:
            raise HTTPException(
                400,
                "Cuerpo de petición vacío",
            )

        storage_key = (
            f"{project_id}/shots/"
            f"{shot_id}.png"
        )

        try:
            storage_service.save_image(
                storage_key,
                image_bytes,
            )
        except SecurityError as error:
            raise HTTPException(
                400,
                str(error),
            )

        now = get_utc_now_iso()

        connection.execute(
            """
            UPDATE shots
            SET storage_key = ?,
                updated_at = ?
            WHERE id = ?
              AND project_id = ?
            """,
            (
                storage_key,
                now,
                shot_id,
                project_id,
            ),
        )
        connection.commit()

        return {
            "status": "ok",
            "storage_key": storage_key,
            "updated_at": now,
        }
@app.get(
    "/api/projects/{project_id}/storyboard/shots/{shot_id}/image"
)
def get_shot_image(
    project_id: int,
    shot_id: str,
):
    with connect() as connection:
        row = connection.execute(
            """
            SELECT storage_key
            FROM shots
            WHERE id = ?
              AND project_id = ?
              AND is_archived = 0
            """,
            (shot_id, project_id),
        ).fetchone()

        if row is None or not row["storage_key"]:
            raise HTTPException(
                404,
                "Imagen no encontrada",
            )

        try:
            data = storage_service.read_image(
                row["storage_key"]
            )
        except (FileNotFoundError, SecurityError):
            raise HTTPException(
                404,
                "Archivo no disponible",
            )

        return Response(
            content=data,
            media_type="image/png",
        )
@app.post(
    "/api/projects/{project_id}/scenes/{scene_id}/reorder"
)
def reorder_shots(
    project_id: int,
    scene_id: int,
    payload: ShotReorderRequest,
):
    with connect() as connection:
        _validate_project_and_scene(
            connection,
            project_id,
            scene_id,
        )

        now = get_utc_now_iso()

        for new_order, shot_id in enumerate(
            payload.shot_ids,
            start=1,
        ):
            connection.execute(
                """
                UPDATE shots
                SET sort_order = ?,
                    updated_at = ?
                WHERE id = ?
                  AND project_id = ?
                  AND scene_id = ?
                  AND is_archived = 0
                """,
                (
                    new_order,
                    now,
                    shot_id,
                    project_id,
                    scene_id,
                ),
            )

        connection.commit()

        return {
            "status": "ok",
            "reordered_count": len(payload.shot_ids),
        } 
@app.delete(
    "/api/projects/{project_id}/shots/{shot_id}"
)
def delete_shot(
    project_id: int,
    shot_id: str,
):
    with connect() as connection:
        row = connection.execute(
            """
            SELECT storage_key
            FROM shots
            WHERE id = ?
              AND project_id = ?
            """,
            (shot_id, project_id),
        ).fetchone()

        if row is None:
            raise HTTPException(
                404,
                "Shot no encontrado",
            )

        storage_key = row["storage_key"]

        if storage_key:
            storage_service.delete_image(
                storage_key
            )

        connection.execute(
            """
            DELETE FROM shots
            WHERE id = ?
              AND project_id = ?
            """,
            (shot_id, project_id),
        )
        connection.commit()

        return {
            "status": "deleted",
            "id": shot_id,
        }           
@app.delete(
    "/api/projects/{project_id}/shots/{shot_id}"
)
def delete_shot(
    project_id: int,
    shot_id: str,
):
    with connect() as connection:
        row = connection.execute(
            """
            SELECT storage_key
            FROM shots
            WHERE id = ?
              AND project_id = ?
            """,
            (shot_id, project_id),
        ).fetchone()

        if row is None:
            raise HTTPException(
                404,
                "Shot no encontrado",
            )

        storage_key = row["storage_key"]

        if storage_key:
            storage_service.delete_image(
                storage_key
            )

        connection.execute(
            """
            DELETE FROM shots
            WHERE id = ?
              AND project_id = ?
            """,
            (shot_id, project_id),
        )
        connection.commit()

        return {
            "status": "deleted",
            "id": shot_id,
        }