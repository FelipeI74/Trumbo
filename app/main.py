from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
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
from .domain import estimate_runtime, format_seconds, parse_character_cue, resolve_character_alias, screenplay_summary
from .scheduling.optimizer import optimize_schedule
from .services.engine_analysis_adapter import analyze_scene_with_engine
from .services.character_service import (
    deserialize_semantic_lines,
    get_project_character_names,
    get_project_character_names as _get_project_character_names,
    list_project_characters as _list_project_characters,
)
from .services.scheduling_service import (
    build_project_scheduling_input,
    build_project_scheduling_input as _build_project_scheduling_input,
    _schedule_input_fingerprint,
    _validate_manual_schedule_days,
    parse_heading_fields,
    parse_heading_fields as _parse_heading_fields,
)
from .services.pdf_service import (
    export_project_pdf as _export_project_pdf,
    export_project_breakdown_pdf as _export_project_breakdown_pdf,
    export_project_schedule_pdf as _export_project_schedule_pdf,
    export_project_csv as _export_project_csv,
    scene_to_dict,
    scene_with_metadata,
    scene_lines_for_export,
)
from .services.gemini_service import (
    GeminiServiceError,
    analyze_scene_with_gemini,
)
from .storage import SecurityError, StoryboardStorage
from .schemas import (
    BreakdownItemCreate,
    BreakdownItemUpdate,
    CharacterAliasList,
    NoteCreate,
    ProjectCreate,
    ProjectUpdate,
    SceneCreate,
    SceneUpdate,
    ScheduleManualOrder,
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


@app.get("/api/projects/{project_id}/reports/breakdown")
def get_project_breakdown_report(project_id: int) -> dict:
    with connect() as connection:
        project = connection.execute(
            "SELECT id, title FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if project is None:
            raise HTTPException(404, "Proyecto no encontrado")

        scene_rows = connection.execute(
            """
            SELECT *
            FROM scenes
            WHERE project_id = ?
            ORDER BY scene_number, id
            """,
            (project_id,),
        ).fetchall()

        scenes = []
        totals = {"confirmed": 0, "detected": 0, "by_category": {}}
        for scene_row in scene_rows:
            scene = scene_with_metadata(connection, scene_row)
            unique_resources = {}
            for item in scene["breakdown_items"]:
                item_state = item["state"]
                if item_state not in {"confirmed", "detected"}:
                    continue

                category = str(item["category"] or "").strip()
                name = str(item["name"] or "").strip()
                if not category or not name:
                    continue

                key = (category.casefold(), name.casefold())
                existing = unique_resources.get(key)
                if existing is None or (
                    existing["state"] == "detected"
                    and item_state == "confirmed"
                ):
                    unique_resources[key] = {
                        "category": category,
                        "name": name,
                        "state": item_state,
                    }

            resources = list(unique_resources.values())
            for item in resources:
                totals[item["state"]] += 1
                totals["by_category"][item["category"]] = (
                    totals["by_category"].get(item["category"], 0) + 1
                )

            scenes.append(
                {
                    "scene_id": scene["id"],
                    "scene_number": scene["scene_number"],
                    "production_number": scene["production_number"],
                    "heading": scene["heading"],
                    "runtime_seconds": scene["runtime_seconds"],
                    "resources": resources,
                }
            )

    return {
        "project": {"id": project["id"], "title": project["title"]},
        "total_scenes": len(scenes),
        "totals": totals,
        "scenes": scenes,
    }

@app.get("/api/projects/{project_id}/characters")
def list_project_characters(
    project_id: int,
) -> dict:
    return _list_project_characters(project_id)


@app.get("/api/projects/{project_id}/character-aliases")
def list_project_character_aliases(
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

        alias_rows = connection.execute(
            """
            SELECT primary_name, alias_name
            FROM character_aliases
            WHERE project_id = ?
            ORDER BY primary_name, alias_name
            """,
            (project_id,),
        ).fetchall()

    return {
        "project_id": project_id,
        "aliases": [
            {
                "primary_name": row["primary_name"],
                "alias_name": row["alias_name"],
            }
            for row in alias_rows
        ],
    }


@app.put("/api/projects/{project_id}/character-aliases")
def replace_project_character_aliases(
    project_id: int,
    payload: CharacterAliasList,
) -> dict:
    # Validar duplicados en el payload antes de tocar la base de datos
    seen_alias_keys: set[str] = set()
    normalized_entries: list[dict] = []

    for entry in payload.aliases:
        primary = entry.primary_name.strip()
        alias = entry.alias_name.strip()

        if not primary or not alias:
            raise HTTPException(
                400,
                "Los nombres de personaje no pueden estar vacios",
            )

        if primary.casefold() == alias.casefold():
            raise HTTPException(
                400,
                f"El alias '{alias}' es igual al nombre principal",
            )

        alias_key = alias.casefold()
        if alias_key in seen_alias_keys:
            raise HTTPException(
                400,
                f"Alias duplicado en la peticion: '{alias}'",
            )
        seen_alias_keys.add(alias_key)

        normalized_entries.append(
            {
                "primary_name": primary,
                "alias_name": alias,
            }
        )

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

        connection.execute(
            "DELETE FROM character_aliases WHERE project_id = ?",
            (project_id,),
        )

        for entry in normalized_entries:
            connection.execute(
                """
                INSERT INTO character_aliases(
                    project_id,
                    primary_name,
                    alias_name
                )
                VALUES (?, ?, ?)
                """,
                (
                    project_id,
                    entry["primary_name"],
                    entry["alias_name"],
                ),
            )

        alias_rows = connection.execute(
            """
            SELECT primary_name, alias_name
            FROM character_aliases
            WHERE project_id = ?
            ORDER BY primary_name, alias_name
            """,
            (project_id,),
        ).fetchall()

    return {
        "project_id": project_id,
        "aliases": [
            {
                "primary_name": row["primary_name"],
                "alias_name": row["alias_name"],
            }
            for row in alias_rows
        ],
    }


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
                scenes.production_number,
                scenes.scene_number
            FROM breakdown_items
            JOIN scenes
                ON scenes.id = breakdown_items.scene_id
            WHERE scenes.project_id = ?
              AND breakdown_items.state != 'rejected'
            ORDER BY scenes.scene_number, breakdown_items.name, breakdown_items.category
            """,
            (project_id,),
        ).fetchall()

    grouped: dict[tuple[str, str], dict] = {}
    seen_in_scene: set[tuple[str, str, str]] = set()

    for resource in resource_rows:
        name = str(resource["name"] or "").strip()
        category = str(resource["category"] or "").strip()
        
        # Usamos production_number (87) como prioridad; si está vacío, usamos scene_number (90)
        scene_number = str(resource["production_number"] or resource["scene_number"]).strip()
        
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

@app.get("/api/projects/{project_id}/scheduling-input")
def get_project_scheduling_input(
    project_id: int,
) -> dict:
    return build_project_scheduling_input(
        project_id
    )


@app.get("/api/projects/{project_id}/schedule-preview")
def get_project_schedule_preview(
    project_id: int,
    shoot_rate_seconds: int = 420,
) -> dict:
    if shoot_rate_seconds <= 0 or shoot_rate_seconds > 3600:
        raise HTTPException(
            422,
            "shoot_rate_seconds debe estar entre 1 y 3600",
        )

    scheduling_input = _build_project_scheduling_input(
        project_id
    )

    calculated = optimize_schedule(
        scheduling_input["scenes"],
        shoot_rate_seconds=shoot_rate_seconds,
    )
    fingerprint = _schedule_input_fingerprint(
        scheduling_input["scenes"],
        shoot_rate_seconds,
    )

    with connect() as connection:
        stored = connection.execute(
            """
            SELECT days_json, input_fingerprint
            FROM schedule_manual_orders
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()

    if stored is None or stored["input_fingerprint"] != fingerprint:
        return calculated

    try:
        manual_days = json.loads(stored["days_json"])
    except (json.JSONDecodeError, TypeError):
        return calculated

    validated_days = _validate_manual_schedule_days(
        manual_days,
        calculated.get("best_schedule", {}).get("days"),
        scheduling_input["scenes"],
    )
    if validated_days is None:
        return calculated

    return {
        **calculated,
        "best_schedule": {
            **calculated["best_schedule"],
            "days": [
                {
                    **calculated_day,
                    "scene_ids": manual_day["scene_ids"],
                }
                for calculated_day, manual_day in zip(
                    calculated["best_schedule"]["days"],
                    validated_days,
                )
            ],
        },
    }


@app.put("/api/projects/{project_id}/schedule-manual-order")
def save_project_schedule_manual_order(
    project_id: int,
    payload: ScheduleManualOrder,
) -> dict:
    scheduling_input = _build_project_scheduling_input(project_id)
    calculated = optimize_schedule(
        scheduling_input["scenes"],
        shoot_rate_seconds=payload.shoot_rate_seconds,
    )
    manual_days = [day.model_dump() for day in payload.days]
    validated_days = _validate_manual_schedule_days(
        manual_days,
        calculated.get("best_schedule", {}).get("days"),
        scheduling_input["scenes"],
    )
    if validated_days is None:
        raise HTTPException(
            400,
            "El orden manual debe conservar jornadas y escenas, sin duplicados y con DÍA antes de NOCHE",
        )

    fingerprint = _schedule_input_fingerprint(
        scheduling_input["scenes"],
        payload.shoot_rate_seconds,
    )
    days_json = json.dumps(
        validated_days,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO schedule_manual_orders(
                project_id,
                days_json,
                input_fingerprint,
                updated_at
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(project_id) DO UPDATE SET
                days_json = excluded.days_json,
                input_fingerprint = excluded.input_fingerprint,
                updated_at = CURRENT_TIMESTAMP
            """,
            (project_id, days_json, fingerprint),
        )

    return {"status": "ok", "days": validated_days}


@app.delete("/api/projects/{project_id}/schedule-manual-order")
def delete_project_schedule_manual_order(
    project_id: int,
) -> dict:
    with connect() as connection:
        project = connection.execute(
            "SELECT 1 FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if project is None:
            raise HTTPException(404, "Proyecto no encontrado")

        connection.execute(
            "DELETE FROM schedule_manual_orders WHERE project_id = ?",
            (project_id,),
        )

    return {"status": "deleted", "project_id": project_id}
@app.delete("/api/projects/{project_id}")
def delete_project(
    project_id: int,
) -> dict:
    with connect() as connection:
        project = connection.execute(
            "SELECT id, title FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()

        if project is None:
            raise HTTPException(
                404,
                "Proyecto no encontrado",
            )

        # 1. Borrar breakdown items (dependen de las escenas)
        connection.execute(
            "DELETE FROM breakdown_items WHERE scene_id IN (SELECT id FROM scenes WHERE project_id = ?)",
            (project_id,),
        )

        # 2. Borrar notas (dependen de las escenas)
        connection.execute(
            "DELETE FROM notes WHERE scene_id IN (SELECT id FROM scenes WHERE project_id = ?)",
            (project_id,),
        )

        # 3. Borrar revisiones (dependen de las escenas)
        connection.execute(
            "DELETE FROM revisions WHERE scene_id IN (SELECT id FROM scenes WHERE project_id = ?)",
            (project_id,),
        )

        # 4. Borrar los planos del storyboard (dependen del proyecto)
        connection.execute(
            "DELETE FROM shots WHERE project_id = ?",
            (project_id,),
        )

        # 5. Borrar las escenas
        connection.execute(
            "DELETE FROM scenes WHERE project_id = ?",
            (project_id,),
        )

        # 6. Borrar aliases de personajes
        connection.execute(
            "DELETE FROM character_aliases WHERE project_id = ?",
            (project_id,),
        )

        # 7. Borrar el orden manual del plan de rodaje (el que ya tenías)
        connection.execute(
            "DELETE FROM schedule_manual_orders WHERE project_id = ?",
            (project_id,),
        )

        # 8. Finalmente, borrar el proyecto
        connection.execute(
            "DELETE FROM projects WHERE id = ?",
            (project_id,),
        )

        return {
            "ok": True,
            "deleted_project_id": project_id,
            "title": project["title"],
        }

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


# --- NUEVA FUNCIÓN DE NORMALIZACIÓN PARA PRODUCTION_NUMBER ---
def normalize_production_number(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if normalized == "":
        return None
    return normalized
# --- FIN NUEVA FUNCIÓN ---


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

        # Normalizar production_number
        prod_num = normalize_production_number(payload.production_number)

        cursor = connection.execute(
            """
            INSERT INTO scenes(
                project_id,
                scene_number,
                production_number,
                heading,
                body,
                semantic_lines,
                synopsis,
                runtime_seconds
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                next_number,
                prod_num,
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
    # Obtener solo los campos enviados explícitamente
    sent = payload.model_dump(exclude_unset=True)
    if not sent:
        raise HTTPException(400, "No hay cambios")

    # Construir data: permitir actualizar production_number a NULL,
    # pero ignorar otros campos con valor None (no deben actualizarse)
    data = {k: v for k, v in sent.items() if v is not None}
    if "production_number" in sent:
        data["production_number"] = normalize_production_number(sent["production_number"])

    if not data:
        raise HTTPException(400, "No hay cambios")

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
            SELECT id, heading, body, semantic_lines, project_id
            FROM scenes
            WHERE id = ?
            """,
            (scene_id,),
        ).fetchone()

        if scene is None:
            raise HTTPException(404, "Escena no encontrada")

        semantic_lines = json.loads(scene["semantic_lines"] or "[]")

        # Obtener los alias del proyecto
        alias_rows = connection.execute(
            """
            SELECT alias_name, primary_name
            FROM character_aliases
            WHERE project_id = ?
            """,
            (scene["project_id"],),
        ).fetchall()

        import unicodedata
        def normalize_name(name: str) -> str:
            if not name:
                return ""
            normalized = unicodedata.normalize("NFD", name)
            return "".join(c for c in normalized if unicodedata.category(c) != "Mn").casefold()

        aliases_map = {
            normalize_name(row["alias_name"]): row["primary_name"]
            for row in alias_rows
        }

        analysis = analyze_scene_with_engine(
            scene_id=scene_id,
            heading=scene["heading"],
            body=scene["body"],
            semantic_lines=semantic_lines,
            known_characters=_get_project_character_names(
                connection,
                scene["project_id"],
            ),
        )

        # Aplicar alias a los personajes detectados
        if "characters" in analysis and analysis["characters"]:
            normalized_chars = []
            for char in analysis["characters"]:
                normalized = normalize_name(char)
                primary = aliases_map.get(normalized, char)
                if primary not in normalized_chars:
                    normalized_chars.append(primary)
            analysis["characters"] = normalized_chars

        return analysis
    
@app.post("/api/scenes/{scene_id}/gemini-analysis")
def analyze_scene_gemini(
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

        heading = scene["heading"] or ""
        body = scene["body"] or ""

    try:
        suggestions = analyze_scene_with_gemini(
            heading=heading,
            body=body,
        )
    except GeminiServiceError as err:
        raise HTTPException(
            status_code=502,
            detail=str(err),
        )

    return {
        "scene_id": scene_id,
        "suggestions": suggestions,
    }


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
    category = payload.category.strip()
    name = payload.name.strip()
    source = payload.source.strip()
    state = normalize_breakdown_state(payload.state)
    
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")

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

        existing_item = connection.execute(
            """
            SELECT *
            FROM breakdown_items
            WHERE scene_id = ?
              AND category = ?
              AND name = ?
            ORDER BY id
            LIMIT 1
            """,
            (
                scene_id,
                category,
                name,
            ),
        ).fetchone()
       
        if existing_item is not None:
            return dict(existing_item)

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
                category,
                name,
                source,
                state,
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
    include_scene_numbers: bool = True,
):
    return _export_project_pdf(
        project_id=project_id,
        include_scene_numbers=include_scene_numbers,
    )


@app.get("/api/projects/{project_id}/export/breakdown-pdf")
def export_project_breakdown_pdf(
    project_id: int,
):
    return _export_project_breakdown_pdf(project_id=project_id)


@app.get("/api/projects/{project_id}/export/schedule-pdf")
def export_project_schedule_pdf(project_id: int):
    return _export_project_schedule_pdf(project_id=project_id)


@app.get("/api/projects/{project_id}/export/csv")
def export_project_csv(project_id: int):
    return _export_project_csv(project_id=project_id)


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
@app.get("/api/projects/{project_id}/storyboard")
def get_project_storyboard(
    project_id: int,
):
    with connect() as connection:
        project = connection.execute(
            """
            SELECT id
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

        if project is None:
            raise HTTPException(
                status_code=404,
                detail="Proyecto no encontrado",
            )

        scene_rows = connection.execute(
            """
            SELECT id, scene_number, production_number, heading
            FROM scenes
            WHERE project_id = ?
            ORDER BY scene_number, id
            """,
            (project_id,),
        ).fetchall()

        storyboard = []

        for scene_row in scene_rows:
            shot_rows = connection.execute(
                """
                SELECT *
                FROM shots
                WHERE project_id = ?
                  AND scene_id = ?
                  AND is_archived = 0
                ORDER BY sort_order, created_at
                """,
                (
                    project_id,
                    scene_row["id"],
                ),
            ).fetchall()

            shots = [
                {
                    **dict(row),
                    "has_image": bool(
                        row["storage_key"]
                    ),
                    "image_url": (
                        f"/api/projects/{project_id}/storyboard/shots/{row['id']}/image"
                        if row["storage_key"]
                        else None
                    ),
                }
                for row in shot_rows
            ]

            storyboard.append(
                {
                    "scene_id": scene_row["id"],
                    "scene_number": scene_row[
                        "scene_number"
                    ],
                    "production_number": scene_row[
                        "production_number"
                    ],
                    "heading": scene_row["heading"],
                    "shots": shots,
                }
            )

        return {
            "project_id": project_id,
            "scenes": storyboard,
        }
    
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

        if len(image_bytes) > 10 * 1024 * 1024:
            raise HTTPException(
                400,
                "La imagen supera el tamaño máximo de 10 MB",
            )

        valid_image_signature = (
            image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
            or image_bytes.startswith(b"\xff\xd8\xff")
            or (
                image_bytes.startswith(b"RIFF")
                and image_bytes[8:12] == b"WEBP"
            )
        )

        if not valid_image_signature:
            raise HTTPException(
                400,
                "Formato de imagen no compatible",
            )

        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            extension = "png"
        elif image_bytes.startswith(b"\xff\xd8\xff"):
            extension = "jpg"
        else:
            extension = "webp"

        storage_key = f"{project_id}/shots/{shot_id}.{extension}"

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

        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(Path(row["storage_key"]).suffix.lower(), "application/octet-stream")

        return Response(content=data, media_type=media_type)
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

        active_shot_ids = {
            row["id"]
            for row in connection.execute(
                """
                SELECT id
                FROM shots
                WHERE project_id = ?
                  AND scene_id = ?
                  AND is_archived = 0
                """,
                (project_id, scene_id),
            ).fetchall()
        }
        requested_shot_ids = payload.shot_ids
        if (
            len(requested_shot_ids) != len(active_shot_ids)
            or len(set(requested_shot_ids)) != len(requested_shot_ids)
            or set(requested_shot_ids) != active_shot_ids
        ):
            raise HTTPException(
                400,
                "El orden debe incluir exactamente una vez todos los planos activos de la escena",
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
@app.get("/api/projects/{project_id}/calendar")
def get_project_calendar(project_id: int) -> dict:
    with connect() as connection:
        project = connection.execute(
            "SELECT start_date, work_days, day_type FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if project is None:
            raise HTTPException(404, "Proyecto no encontrado")
        return dict(project)

@app.put("/api/projects/{project_id}/calendar")
def update_project_calendar(project_id: int, payload: dict) -> dict:
    with connect() as connection:
        project = connection.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if project is None:
            raise HTTPException(404, "Proyecto no encontrado")

        connection.execute(
            """
            UPDATE projects
            SET start_date = ?, work_days = ?, day_type = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                payload.get("start_date"),
                payload.get("work_days", "1,2,3,4,5"),
                payload.get("day_type", "estandar"),
                project_id,
            ),
        )
        return {"status": "ok"}