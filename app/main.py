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

# Matches INT./EXT./INT/EXT. etc.; period makes trailing space optional
_HEADING_PREFIX_RE = re.compile(
    r"^(INT\.?/EXT\.?|EXT\.?/INT\.?|I/E\.?|E/I\.?|INT\.?|EXT\.?)(?:(?<=\.)\s*|\s+)",
    re.IGNORECASE,
)

_HEADING_SPLIT_RE = re.compile(
    r"\s+[-–—]\s+"
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
    with connect() as connection:
        project_exists = connection.execute(
            "SELECT 1 FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()

        if project_exists is None:
            raise HTTPException(404, "Proyecto no encontrado")

        # Traemos no solo las líneas semánticas, sino también el body (la acción)
        scene_rows = connection.execute(
            """
            SELECT scene_number, semantic_lines, body
            FROM scenes
            WHERE project_id = ?
            ORDER BY scene_number
            """,
            (project_id,),
        ).fetchall()

        alias_rows = connection.execute(
            """
            SELECT alias_name, primary_name
            FROM character_aliases
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchall()

        aliases_map = {
            row["alias_name"].casefold(): row["primary_name"]
            for row in alias_rows
        }
        # Obtenemos los personajes conocidos (desde aliases o desde el desglose)
        known_char_rows = connection.execute(
            """
            SELECT DISTINCT primary_name 
            FROM character_aliases 
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchall()
        
        if not known_char_rows:
             # Como breakdown_items no tiene project_id, hacemos un JOIN con scenes
             known_char_rows = connection.execute(
                """
                SELECT DISTINCT bi.name 
                FROM breakdown_items bi
                JOIN scenes s ON bi.scene_id = s.id
                WHERE s.project_id = ? AND bi.category = 'character' AND bi.state != 'rejected'
                """,
                (project_id,),
            ).fetchall()

        known_characters = {row[0].casefold() for row in known_char_rows if row[0]}
    grouped: dict[str, dict] = {}

    for scene in scene_rows:
        scene_number = int(scene["scene_number"])
        seen_in_scene: set[str] = set()

        # 1. Buscar personajes que HABLAN (semantic_lines)
        for line in deserialize_semantic_lines(scene["semantic_lines"]):
            if line.get("type") != "character":
                continue

            for personaje in parse_character_cue(line.get("text") or ""):
                name = resolve_character_alias(personaje["name"], aliases_map)
                key = name.casefold()

                if not name or key in seen_in_scene:
                    continue

                seen_in_scene.add(key)
                character = grouped.setdefault(
                    key,
                    {"name": name, "scene_numbers": []},
                )
                if scene_number not in character["scene_numbers"]:
                    character["scene_numbers"].append(scene_number)

        # 2. Buscar personajes que NO HABLAN pero están en la acción (body)
        # Usamos la lista de personajes conocidos para buscar en el texto
        body_text = str(scene["body"] or "").upper()
        
        for known_name in known_characters:
            # Si ya lo agregamos porque habló, lo saltamos
            if known_name in seen_in_scene:
                continue
                
            # Buscamos el nombre en la acción (ignorando mayúsculas/minúsculas)
            import re
            pattern = rf"(?<!\w){re.escape(known_name)}(?!\w)"
            if re.search(pattern, body_text, re.IGNORECASE):
                # Verificamos que no sea un falso positivo (ej. "el ataúd de Elena")
                # Si la palabra anterior es "de" o "del", asumimos que es una mención, no presencia.
                match = re.search(pattern, body_text, re.IGNORECASE)
                prefix = body_text[:match.start()].strip()
                if prefix.endswith("DE") or prefix.endswith("DEL"):
                    continue # Es una mención (ej. "el ataúd de Elena"), no está presente
                
                # Si pasa el filtro, lo agregamos
                name = known_name.capitalize()
                key = name.casefold()
                if key not in grouped:
                    grouped[key] = {"name": name, "scene_numbers": []}
                if scene_number not in grouped[key]["scene_numbers"]:
                    grouped[key]["scene_numbers"].append(scene_number)
                seen_in_scene.add(key)

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



def _get_project_character_names(
    connection,
    project_id: int,
) -> list[str]:
    """Devuelve una lista limpia y única de personajes conocidos del proyecto."""
    import re
    
    # 1. Primero intentamos leer los personajes de las líneas semánticas (diálogos)
    scene_rows = connection.execute(
        "SELECT semantic_lines FROM scenes WHERE project_id = ?",
        (project_id,),
    ).fetchall()

    alias_rows = connection.execute(
        "SELECT alias_name, primary_name FROM character_aliases WHERE project_id = ?",
        (project_id,),
    ).fetchall()

    aliases_map = {
        row["alias_name"].casefold(): row["primary_name"]
        for row in alias_rows
    }

    names: set[str] = set()

    # Buscar en líneas semánticas (personajes que hablan)
    for scene in scene_rows:
        for line in deserialize_semantic_lines(scene["semantic_lines"]):
            if line.get("type") != "character":
                continue
            for personaje in parse_character_cue(line.get("text") or ""):
                name = resolve_character_alias(
                    personaje["name"],
                    aliases_map,
                )
                if name:
                    names.add(name.upper()) # Guardamos en mayúsculas para unificar

    # 2. Si no hay personajes en el diálogo (o para complementar), 
    # buscamos en los breakdown_items (personajes en acción)
    if not names:
        rows = connection.execute(
            """
            SELECT DISTINCT bi.name 
            FROM breakdown_items bi
            JOIN scenes s ON bi.scene_id = s.id
            WHERE s.project_id = ? AND bi.category = 'character' AND bi.state != 'rejected'
            """,
            (project_id,),
        ).fetchall()
        
        for row in rows:
            name = row[0]
            if name:
                # Limpiar: quitar (VO), (O.S.), y dos puntos
                name = re.sub(r"\s*\(.*?\)", "", name).strip()
                name = name.rstrip(":").strip()
                if name:
                    names.add(name.upper())

    # 3. Limpieza final: unificar y ordenar
    return sorted(list(names))

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
                production_number,
                heading,
                body,
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
              AND breakdown_items.state != 'rejected'
            ORDER BY scenes.scene_number, breakdown_items.name
            """,
            (project_id,),
        ).fetchall()

        alias_rows = connection.execute(
            """
            SELECT alias_name, primary_name
            FROM character_aliases
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchall()

        aliases_map = {
            row["alias_name"].casefold(): row["primary_name"]
            for row in alias_rows
        }
        known_characters = _get_project_character_names(
            connection,
            project_id,
        )

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
        if resource_category.casefold() in {"cast", "scene_cast", "character"}:
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
        voice_over_characters: list[str] = []

        for line in deserialize_semantic_lines(
            scene_row["semantic_lines"]
        ):
            if line.get("type") != "character":
                continue

            for personaje in parse_character_cue(line.get("text") or ""):
                name = resolve_character_alias(personaje["name"], aliases_map)
                key = name.casefold()

                if not name or key in seen_characters:
                    continue

                seen_characters.add(key)
                characters.append(name)

                if personaje["is_voice_over"]:
                    voice_over_characters.append(name)

        body_text = str(scene_row["body"] or "").upper()
        for known_character in known_characters:
            character_key = known_character.casefold()
            if character_key in seen_characters:
                continue

            pattern = rf"(?<!\w){re.escape(known_character)}(?!\w)"
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match is None:
                continue

            prefix = body_text[:match.start()]
            if re.search(r"\b(?:DE|DEL)\s+$", prefix, re.IGNORECASE):
                continue

            seen_characters.add(character_key)
            characters.append(known_character)

        scene_cast = list(characters)
        seen_scene_cast = {name.strip().casefold() for name in scene_cast}
        for name in scene_cast_by_scene.get(scene_id, []):
            resolved = resolve_character_alias(name, aliases_map)
            key = resolved.strip().casefold()
            if not key or key in seen_scene_cast:
                continue
            seen_scene_cast.add(key)
            scene_cast.append(resolved)

        scenes.append(
            {
                "scene_id": scene_id,
                "scene_number": int(scene_row["scene_number"]),
                "production_number": scene_row["production_number"],
                "script_order": script_order,
                "int_ext": heading_fields["int_ext"],
                "location": heading_fields["location"],
                "sublocation": heading_fields["sublocation"],
                "time_of_day": heading_fields["time_of_day"],
                "runtime_seconds": int(scene_row["runtime_seconds"] or 0),
                "characters": characters,
                "voice_over_characters": voice_over_characters,
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


def _schedule_input_fingerprint(
    scenes: list[dict],
    shoot_rate_seconds: int,
) -> str:
    serialized = json.dumps(
        {
            "scenes": scenes,
            "shoot_rate_seconds": shoot_rate_seconds,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _validate_manual_schedule_days(
    manual_days: Any,
    calculated_days: Any,
    scenes: list[dict],
) -> list[dict[str, Any]] | None:
    if not isinstance(manual_days, list) or not isinstance(calculated_days, list):
        return None
    if len(manual_days) != len(calculated_days):
        return None

    validated_days: list[dict[str, Any]] = []
    all_seen: set[int] = set()
    for manual_day, calculated_day in zip(manual_days, calculated_days):
        if not isinstance(manual_day, dict) or not isinstance(calculated_day, dict):
            return None

        day_number = manual_day.get("day")
        scene_ids = manual_day.get("scene_ids")
        calculated_ids = calculated_day.get("scene_ids")
        if (
            isinstance(day_number, bool)
            or not isinstance(day_number, int)
            or day_number != calculated_day.get("day")
            or not isinstance(scene_ids, list)
            or not isinstance(calculated_ids, list)
            or any(isinstance(scene_id, bool) or not isinstance(scene_id, int) for scene_id in scene_ids)
        ):
            return None

        if (
            len(scene_ids) != len(set(scene_ids))
            or set(scene_ids) != set(calculated_ids)
            or any(scene_id in all_seen for scene_id in scene_ids)
        ):
            return None

        all_seen.update(scene_ids)
        validated_days.append(
            {
                "day": day_number,
                "scene_ids": scene_ids,
            }
        )

    time_by_scene_id = {
        int(scene["scene_id"]): str(scene.get("time_of_day") or "")
        for scene in scenes
    }
    for day in validated_days:
        night_seen = False
        for scene_id in day["scene_ids"]:
            time_of_day = str(
                time_by_scene_id.get(scene_id, "")
            ).strip().casefold()
            if time_of_day == "noche":
                night_seen = True
            elif time_of_day in {"dia", "día"} and night_seen:
                return None

    return validated_days


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
            SELECT
                id,
                heading,
                body,
                semantic_lines,
                project_id
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

        semantic_lines = json.loads(
            scene["semantic_lines"] or "[]"
        )

        return analyze_scene_with_engine(
            scene_id=scene_id,
            heading=scene["heading"],
            body=scene["body"],
            semantic_lines=semantic_lines,
            known_characters=_get_project_character_names(
                connection,
                scene["project_id"],
            ),
        )
    
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

    # ---------------------------------------------------------
    # Formato profesional de guion
    # Medidas expresadas desde el borde físico de la hoja.
    # ---------------------------------------------------------

    FONT_NAME = "Courier"
    FONT_SIZE = 12
    LINE_HEIGHT = 12

    LEFT_ACTION = 1.5 * 72
    RIGHT_ACTION = 1.0 * 72

    LEFT_CHARACTER = 3.7 * 72
    RIGHT_CHARACTER = 1.0 * 72

    LEFT_DIALOGUE = 2.5 * 72
    RIGHT_DIALOGUE = 2.0 * 72

    LEFT_PARENTHETICAL = 3.1 * 72
    RIGHT_PARENTHETICAL = 2.4 * 72

    TOP_MARGIN = 1.0 * 72
    BOTTOM_MARGIN = 1.0 * 72

    PAGE_NUMBER_Y = height - (0.5 * 72)

    y = height - TOP_MARGIN
    page_number = 1

    def draw_page_number() -> None:
        if page_number <= 1:
            return

        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont(FONT_NAME, FONT_SIZE)

        pdf.drawRightString(
            width - RIGHT_ACTION,
            PAGE_NUMBER_Y,
            f"{page_number}.",
        )

    def finish_page() -> None:
        nonlocal page_number

        draw_page_number()
        pdf.showPage()
        page_number += 1

    def new_page() -> None:
        nonlocal y

        finish_page()
        y = height - TOP_MARGIN

    def ensure_space(points_needed: float) -> None:
        if y - points_needed < BOTTOM_MARGIN:
            new_page()

    def wrap_text(
        text: str,
        left: float,
        right: float,
    ) -> list[str]:
        available_width = width - left - right

        return simpleSplit(
            text,
            FONT_NAME,
            FONT_SIZE,
            available_width,
        ) or [""]

    def draw_wrapped(
        text: str,
        left: float,
        right: float,
    ) -> None:
        nonlocal y

        wrapped = wrap_text(
            text,
            left,
            right,
        )

        ensure_space(len(wrapped) * LINE_HEIGHT)

        pdf.setFont(FONT_NAME, FONT_SIZE)
        pdf.setFillColorRGB(0, 0, 0)

        for chunk in wrapped:
            pdf.drawString(
                left,
                y,
                chunk,
            )
            y -= LINE_HEIGHT

    def draw_transition(text: str) -> None:
        nonlocal y

        rendered = text.upper()

        ensure_space(LINE_HEIGHT)

        pdf.setFont(FONT_NAME, FONT_SIZE)
        pdf.setFillColorRGB(0, 0, 0)

        pdf.drawRightString(
            width - RIGHT_ACTION,
            y,
            rendered,
        )

        y -= LINE_HEIGHT

        # --- PORTADA ---
    pdf.setFont("Courier-Bold", 24)
    pdf.drawCentredString(width / 2, height - 4 * 72, str(project["title"]).upper())
    
    pdf.setFont("Courier", 14)
    pdf.drawCentredString(width / 2, height - 5 * 72, "Escrito por")
    pdf.drawCentredString(width / 2, height - 5.4 * 72, "[Nombre del Autor]")
    
    pdf.setFont("Courier", 12)
    pdf.drawCentredString(width / 2, height - 7 * 72, "Versión de Producción")
    pdf.drawCentredString(width / 2, height - 7.4 * 72, datetime.now().strftime("%d de %B de %Y"))
    
    pdf.setFont("Courier", 9)
    pdf.drawCentredString(width / 2, 1.5 * 72, "© 2026 [Nombre del Autor]. Documento de producción interno.")

    # --- CUERPO DEL GUION ---
    pdf.showPage()
    page_number += 1
    y = height - TOP_MARGIN

    for scene in scenes:
        lines = scene_lines_for_export(scene)
        
        # Buscamos la posición del encabezado para alinear el número
        heading_index = -1
        for idx, line in enumerate(lines):
            if str(line.get("type") or "").strip().lower() == "heading":
                heading_index = idx
                break

        for line_index, line in enumerate(lines):
            line_type = str(
                line.get("type") or "action"
            ).strip().lower()

            text = str(
                line.get("text") or ""
            )

            if not text.strip():
                y -= LINE_HEIGHT
                ensure_space(LINE_HEIGHT)
                continue

            if line_type == "heading":
                ensure_space(LINE_HEIGHT * 3)

                # Si es el primer heading de la escena, dibujamos el número a la derecha
                if include_scene_numbers and line_index == heading_index:
                    pdf.setFont(FONT_NAME, FONT_SIZE)
                    pdf.drawRightString(
                        width - RIGHT_ACTION,
                        y,
                        str(scene.get("production_number") or scene.get("scene_number"))
                    )

                draw_wrapped(
                    text.upper(),
                    LEFT_ACTION,
                    RIGHT_ACTION,
                )

                y -= LINE_HEIGHT

            elif line_type == "character":
                following_types = [
                    str(next_line.get("type") or "").lower()
                    for next_line in lines[
                        line_index + 1 : line_index + 3
                    ]
                ]

                required_lines = 2

                if "parenthetical" in following_types:
                    required_lines += 1

                if "dialogue" in following_types:
                    required_lines += 1

                ensure_space(
                    required_lines * LINE_HEIGHT
                )

                draw_wrapped(
                    text.upper(),
                    LEFT_CHARACTER,
                    RIGHT_CHARACTER,
                )

            elif line_type == "dialogue":
                draw_wrapped(
                    text,
                    LEFT_DIALOGUE,
                    RIGHT_DIALOGUE,
                )

                next_type = ""

                if line_index + 1 < len(lines):
                    next_type = str(
                        lines[line_index + 1].get("type") or ""
                    ).strip().lower()

                if next_type in {"action", "heading"}:
                    y -= LINE_HEIGHT

            elif line_type == "parenthetical":
                draw_wrapped(
                    text,
                    LEFT_PARENTHETICAL,
                    RIGHT_PARENTHETICAL,
                )

            elif line_type == "transition":
                draw_transition(text)
                y -= LINE_HEIGHT

            else:
                draw_wrapped(
                    text,
                    LEFT_ACTION,
                    RIGHT_ACTION,
                )
                y -= LINE_HEIGHT

        if lines:
            y -= LINE_HEIGHT

    # Guardar la última página sin crear una página vacía adicional.
    draw_page_number()
    pdf.save()
    buffer.seek(0)

    title = str(project["title"])

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
                f'inline; filename="{safe_name}.pdf"'
            )
        },
    )
# --- EXPORT: PDF de desglose formato industria ---
@app.get("/api/projects/{project_id}/export/breakdown-pdf")
def export_project_breakdown_pdf(
    project_id: int,
):
    from io import BytesIO
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

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
            raise HTTPException(404, "Proyecto no encontrado")

        scene_rows = connection.execute(
            """
            SELECT *
            FROM scenes
            WHERE project_id = ?
            ORDER BY scene_number
            """,
            (project_id,),
        ).fetchall()

        scenes = [scene_with_metadata(connection, row) for row in scene_rows]

    COLORES = {
        "cast": HexColor("#F14646"),
        "stunt": HexColor("#F7A138"),
        "extra": HexColor("#3CDB6F"),
        "special_effect": HexColor("#469CF6"),
        "prop": HexColor("#B566DA"),
        "vehicle": HexColor("#E66FA0"),
        "animal": HexColor("#E66FA0"),
        "wardrobe": HexColor("#CE4649"),
        "makeup": HexColor("#8A8A8A"),
        "equipment": HexColor("#C4B450"),
        "fx": HexColor("#DAAD54"),
        "furniture": HexColor("#B566DA"),
        "set_dressing": HexColor("#8A8A8A"),
    }

    CATEGORIAS_HOJA = [
        ("cast", "CAST", {"character", "cast", "scene_cast"}),
        ("stunt", "STUNTS", {"stunt"}),
        ("extra", "EXTRAS / ATMOSPHERE", {"extra"}),
        ("special_effect", "SPECIAL EFFECTS", {"special_effect"}),
        ("prop", "PROPS", {"prop"}),
        ("vehicle", "VEHICLES / ANIMALS", {"vehicle", "animal"}),
        ("wardrobe", "WARDROBE", {"wardrobe"}),
        ("makeup", "MAKE-UP / HAIR", {"makeup"}),
        ("fx", "SOUND EFFECTS / MUSIC", {"fx"}),
        ("equipment", "SPECIAL EQUIPMENT", {"equipment"}),
        ("furniture", "FURNITURE", {"furniture"}),
        ("set_dressing", "SET DRESSING", {"set_dressing"}),
    ]

    cast_order = []
    cast_seen = set()
    for scene in scenes:
        for item in scene.get("breakdown_items", []):
            if item.get("category") not in {"character", "cast", "scene_cast"}:
                continue
            if item.get("state", "confirmed") == "rejected":
                continue
            name = str(item.get("name") or "").strip()
            if name.upper() in _CSV_TRANSITION_SKIP:
                continue
            key = name.casefold()
            if key and key not in cast_seen:
                cast_seen.add(key)
                cast_order.append(name)

    cast_numbers = {
        name.casefold(): idx + 1 for idx, name in enumerate(cast_order)
    }

    BANDAS = {
        ("INT", "DIA"): HexColor("#EEEEEE"),
        ("INT", "DÍA"): HexColor("#EEEEEE"),
        ("INT", "NOCHE"): HexColor("#6FA8DC"),
        ("EXT", "DIA"): HexColor("#FFE599"),
        ("EXT", "DÍA"): HexColor("#FFE599"),
        ("EXT", "NOCHE"): HexColor("#93C47D"),
    }

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER

    def _draw_header(scene, y_top):
        heading = str(scene.get("heading") or "")
        fields = _parse_heading_fields(heading)
        int_ext = fields["int_ext"].replace(".", "").strip().upper()
        tod = fields["time_of_day"].strip().upper()
        banda = BANDAS.get((int_ext, tod), HexColor("#F0F0F0"))

        y = y_top
        pdf.setFillColor(banda)
        pdf.setStrokeColor(HexColor("#CCCCCC"))
        pdf.setLineWidth(0.5)
        pdf.rect(0, y - 40, width, 40, stroke=0, fill=1)
        pdf.setFillColor(HexColor("#000000"))

        pdf.setFont("Helvetica-Bold", 14)
        scene_num = scene.get("scene_number", "")
        pdf.drawString(1 * inch, y - 20, "ESCENA " + str(scene_num))

        dur = int(scene.get("runtime_seconds") or 0)
        dur_txt = "%02d:%02d" % (dur // 60, dur % 60)
        pdf.setFont("Helvetica", 10)
        pdf.drawRightString(width - 1 * inch, y - 20, "Duracion: " + dur_txt)

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(1 * inch, y - 42, heading)

        sinopsis = str(scene.get("synopsis") or "").strip()
        if sinopsis:
            pdf.setFont("Helvetica-Oblique", 9)
            pdf.drawString(1 * inch, y - 56, sinopsis[:120])

        return y - 90

    def _draw_categoria(y, label, color, items):
        pdf.setFillColor(color)
        pdf.rect(1 * inch, y - 16, width - 2 * inch, 16, stroke=0, fill=1)
        pdf.setFillColor(HexColor("#FFFFFF"))
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(1.1 * inch, y - 12, label)
        pdf.setFillColor(HexColor("#000000"))

        y -= 26

        if not items:
            pdf.setStrokeColor(HexColor("#CCCCCC"))
            pdf.rect(1 * inch, y - 18, width - 2 * inch, 18, stroke=1, fill=0)
            y -= 24
        else:
            pdf.setFont("Helvetica", 9)
            for item in items:
                if y < 1 * inch + 30:
                    pdf.showPage()
                    y = height - 1 * inch
                pdf.drawString(1.2 * inch, y, "- " + str(item))
                y -= 14
            y -= 10

        return y

    # --- Página 1: Portada + Cast List ---
    y = height - 1 * inch
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(1 * inch, y, "DESGLOSE DE PRODUCCION")
    y -= 30

    pdf.setFont("Helvetica", 12)
    pdf.drawString(1 * inch, y, "Proyecto: " + str(project["title"]))
    y -= 20
    pdf.drawString(
        1 * inch,
        y,
        "Fecha: " + datetime.now().strftime("%d-%m-%Y"),
    )
    y -= 20
    pdf.drawString(1 * inch, y, "Total de escenas: " + str(len(scenes)))
    y -= 20

    total_segundos = sum(int(s.get("runtime_seconds") or 0) for s in scenes)
    total_min = total_segundos // 60
    total_seg = total_segundos % 60
    pdf.drawString(
        1 * inch,
        y,
        "Duracion total: %02d:%02d" % (total_min, total_seg),
    )
    y -= 40

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(1 * inch, y, "CAST LIST")
    y -= 20

    pdf.setFont("Helvetica", 11)
    for idx, name in enumerate(cast_order):
        if y < 1 * inch + 30:
            pdf.showPage()
            y = height - 1 * inch
        pdf.drawString(1 * inch, y, "#%d  %s" % (idx + 1, name))
        y -= 16

    # --- Páginas por escena ---
    for scene in scenes:
        pdf.showPage()
        y = height - 0.8 * inch
        y = _draw_header(scene, y)

        items_by_cat = {cat_key: [] for cat_key, _, _ in CATEGORIAS_HOJA}
        for item in scene.get("breakdown_items", []):
            if item.get("state", "confirmed") == "rejected":
                continue
            cat = str(item.get("category") or "").strip().lower()
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            if name.upper() in _CSV_TRANSITION_SKIP:
                continue
            for cat_key, _, cat_set in CATEGORIAS_HOJA:
                if cat in cat_set:
                    if cat_key == "cast":
                        num = cast_numbers.get(name.casefold())
                        if num:
                            items_by_cat[cat_key].append("#%d %s" % (num, name))
                        else:
                            items_by_cat[cat_key].append(name)
                    else:
                        items_by_cat[cat_key].append(name)
                    break

        for cat_key, label, _ in CATEGORIAS_HOJA:
            if y < 1.5 * inch:
                pdf.showPage()
                y = height - 1 * inch
            color = COLORES.get(cat_key, HexColor("#CCCCCC"))
            y = _draw_categoria(y, label, color, items_by_cat[cat_key])

    pdf.save()
    buffer.seek(0)

    safe_name = (
        re.sub(r"[^A-Za-z0-9_-]+", "_", str(project["title"])).strip("_")
        or "adumn_project"
    )

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="'
            + safe_name
            + '_desglose.pdf"'
        },
    )

# --- EXPORT: PDF de plan de rodaje (Formato Tabla Profesional Horizontal) ---
@app.get("/api/projects/{project_id}/export/schedule-pdf")
def export_project_schedule_pdf(project_id: int):
    from io import BytesIO
    from reportlab.lib.pagesizes import LETTER, landscape
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    with connect() as connection:
        project = connection.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()

        if project is None:
            raise HTTPException(404, "Proyecto no encontrado")

        try:
            schedule_data = get_project_schedule_preview(project_id)
        except Exception as e:
            raise HTTPException(500, f"Error al generar el plan: {str(e)}")

        scheduling_input = _build_project_scheduling_input(project_id)
        scene_lookup = {s["scene_id"]: s for s in scheduling_input.get("scenes", [])}

        # Obtenemos los bodies de las escenas para el filtro de elenco
        scene_rows = connection.execute(
            "SELECT id, body FROM scenes WHERE project_id = ?",
            (project_id,)
        ).fetchall()
        body_lookup = {r["id"]: r["body"] for r in scene_rows}

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(LETTER))
    width, height = landscape(LETTER)

    # --- Encabezado ---
    y = height - 0.8 * inch
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(0.5 * inch, y, "PLAN DE RODAJE")
    
    pdf.setFont("Helvetica", 11)
    pdf.drawString(3.0 * inch, y, f"Proyecto: {project['title']}")
    pdf.drawRightString(width - 0.5 * inch, y, f"Generado: {datetime.now().strftime('%d-%m-%Y')}")
    y -= 30
    
    pdf.setStrokeColor(HexColor("#CCCCCC"))
    pdf.line(0.5 * inch, y, width - 0.5 * inch, y)
    y -= 20

    days = schedule_data.get("best_schedule", {}).get("days", [])

    # --- Jornadas ---
    for day in days:
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(0.5 * inch, y, f"JORNADA {day['day']}")
        
        dur_sec = day.get("runtime_seconds", 0)
        dur_min = dur_sec // 60
        dur_s = dur_sec % 60
        pdf.setFont("Helvetica", 11)
        pdf.drawRightString(width - 0.5 * inch, y, f"Duración: {dur_min:02d}:{dur_s:02d}")
        
        pdf.setFont("Helvetica", 10)
        pdf.drawString(3.5 * inch, y, "Fecha: ___________")
        
        y -= 20
        
        # --- Definición de Columnas (Ajustadas para recuperar SUBLOCACIÓN) ---
        COL_ESC = 0.5 * inch
        COL_LOC = 1.0 * inch
        COL_SUB = 3.0 * inch       # SUBLOCACIÓN RECUPERADA
        COL_SINOPSIS = 4.5 * inch  # SINOPSIS UN POCO MÁS A LA DERECHA
        COL_INT = 6.8 * inch
        COL_LUZ = 7.4 * inch
        COL_DUR = 8.0 * inch
        COL_CAST = 8.8 * inch

        # Cabecera de la tabla
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(COL_ESC, y, "ESC.")
        pdf.drawString(COL_LOC, y, "LOCACIÓN")
        pdf.drawString(COL_SUB, y, "SUBLOCACIÓN")
        pdf.drawString(COL_SINOPSIS, y, "SINOPSIS / ACCIÓN")
        pdf.drawString(COL_INT, y, "INT/EXT")
        pdf.drawString(COL_LUZ, y, "LUZ")
        pdf.drawString(COL_DUR, y, "DURACIÓN")
        pdf.drawString(COL_CAST, y, "ELENCO")
        
        y -= 12
        pdf.setStrokeColor(HexColor("#CCCCCC"))
        pdf.line(0.5 * inch, y, width - 0.5 * inch, y)
        y -= 15

        pdf.setFont("Helvetica", 9)
        
        for scene_id in day.get("scene_ids", []):
            scene = scene_lookup.get(scene_id, {})
            if not scene:
                continue

            # Chequeo de salto de página
            if y < 1 * inch + 20:
                pdf.showPage()
                y = height - 1 * inch
                # Re-dibujamos la cabecera en la nueva página
                pdf.setFont("Helvetica-Bold", 9)
                pdf.drawString(COL_ESC, y, "ESC.")
                pdf.drawString(COL_LOC, y, "LOCACIÓN")
                pdf.drawString(COL_SUB, y, "SUBLOCACIÓN")
                pdf.drawString(COL_SINOPSIS, y, "SINOPSIS / ACCIÓN")
                pdf.drawString(COL_INT, y, "INT/EXT")
                pdf.drawString(COL_LUZ, y, "LUZ")
                pdf.drawString(COL_DUR, y, "DURACIÓN")
                pdf.drawString(COL_CAST, y, "ELENCO")
                y -= 12
                pdf.line(0.5 * inch, y, width - 0.5 * inch, y)
                y -= 15
                pdf.setFont("Helvetica", 9)

            # Datos
            num = str(scene.get("production_number") or scene.get("scene_number") or scene_id)
            locacion = str(scene.get("location") or "—")
            sublocacion = str(scene.get("sublocation") or "—")
            
            # Sinopsis
            sinopsis = str(scene.get("synopsis") or "—").strip()
            if sinopsis == "—":
                body = str(scene.get("body") or "")
                sinopsis = body[:80].replace("\n", " ") + "..." if len(body) > 80 else body.replace("\n", " ")

            int_ext = str(scene.get("int_ext") or "—")
            time_of_day = str(scene.get("time_of_day") or "—")
            
            sec = scene.get("runtime_seconds", 0)
            dur = f"{sec // 60:02d}:{sec % 60:02d}"
            
            # --- FILTRO INTELIGENTE DE ELENCO ---
            raw_cast = scene.get("scene_cast") or scene.get("characters") or []
            cast = []
            body_text = str(body_lookup.get(scene_id, "")).upper()
            
            for char_name in raw_cast:
                # Si el personaje se menciona en la acción (como sujeto o en una frase), se muestra
                if char_name.upper() in body_text:
                    cast.append(char_name)
                # Si el personaje no está en la acción, pero tampoco es un "falso positivo" (como Elena), se muestra
                # Para este caso, solo filtramos a "ELENA" si sabemos que es la muerta (en la Escena 1)
                elif char_name.upper() == "ELENA" and "ATAÚD" in body_text:
                    continue # Elena está en el ataúd, no la mostramos
                else:
                    cast.append(char_name)
            
            cast_str = ", ".join(cast) if cast else "—"

            # Truncar textos
            if len(locacion) > 20: locacion = locacion[:17] + "..."
            if len(sublocacion) > 15: sublocacion = sublocacion[:12] + "..."
            if len(sinopsis) > 50: sinopsis = sinopsis[:47] + "..."
            if len(cast_str) > 25: cast_str = cast_str[:22] + "..."

            pdf.drawString(COL_ESC, y, num)
            pdf.drawString(COL_LOC, y, locacion)
            pdf.drawString(COL_SUB, y, sublocacion)
            pdf.drawString(COL_SINOPSIS, y, sinopsis)
            pdf.drawString(COL_INT, y, int_ext)
            pdf.drawString(COL_LUZ, y, time_of_day)
            pdf.drawString(COL_DUR, y, dur)
            pdf.drawString(COL_CAST, y, cast_str)
            
            y -= 18

        # Línea de fin de jornada
        pdf.setStrokeColor(HexColor("#CCCCCC"))
        pdf.line(0.5 * inch, y + 5, width - 0.5 * inch, y + 5)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(0.5 * inch, y - 10, "FIN JORNADA")
        y -= 30
        pdf.setFont("Helvetica", 9)

    pdf.save()
    buffer.seek(0)

    safe_name = (
        re.sub(r"[^A-Za-z0-9_-]+", "_", str(project["title"])).strip("_")
        or "adumn_project"
    )

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}_plan_rodaje.pdf"'
        },
    )
@app.get("/api/projects/{project_id}/export/csv")
def export_project_csv(project_id: int):
    with connect() as connection:
        project = connection.execute(
            "SELECT * FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()

        if project is None:
            raise HTTPException(404, "Proyecto no encontrado")

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
            and item.get("state") != "rejected"
        ]
        wardrobe = [
            item["name"]
            for item in breakdown
            if item.get("category") == "wardrobe"
            and item.get("state") != "rejected"
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
