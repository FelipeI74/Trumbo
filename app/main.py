from __future__ import annotations

from collections import Counter
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .database import connect, initialize, rows
from .domain import estimate_runtime, screenplay_summary
from .services.engine_analysis_adapter import analyze_scene_with_engine
from .schemas import (
    BreakdownItemCreate,
    BreakdownItemUpdate,
    NoteCreate,
    ProjectCreate,
    ProjectUpdate,
    SceneCreate,
    SceneUpdate,
)


app = FastAPI(
    title="Trumbo Alpha",
    version="0.3.1",
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
            scene = scene_to_dict(
                scene_row
            )

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

            scenes.append(scene)

        return {
            "project": dict(project),
            "scenes": scenes,
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
            SELECT id, heading, body
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

    candidates = spelling_candidates(dict(scene))

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
    unknown = checker.unknown(counter.keys())

    misspellings: list[dict] = []

    for word in sorted(
        unknown,
        key=lambda item: (-counter[item], item),
    ):
        suggestions = list(
            checker.candidates(word)
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
    )

    width, height = LETTER
    margin_x = 50
    margin_y = 50
    y = height - margin_y

    def ensure_space(lines_needed: int = 1) -> None:
        nonlocal y
        min_y = margin_y + (lines_needed * 14)

        if y <= min_y:
            pdf.showPage()
            y = height - margin_y

    title = str(project["title"])
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(margin_x, y, title)
    y -= 24

    pdf.setFont("Helvetica", 10)
    pdf.drawString(
        margin_x,
        y,
        "Exportado desde Trumbo Alpha",
    )
    y -= 24

    for scene in scenes:
        scene_heading = (
            str(scene.get("heading") or "").strip()
            or "Sin encabezado"
        )

        ensure_space(3)

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(
            margin_x,
            y,
            f"ESCENA {scene['scene_number']}: {scene_heading}",
        )
        y -= 18

        lines = scene_lines_for_export(scene)

        for line in lines:
            line_type = line.get("type") or "action"
            text = str(line.get("text") or "")

            if not text.strip():
                y -= 10
                continue

            if line_type == "heading":
                font_name = "Helvetica-Bold"
                indent = 0
                rendered = text.upper()
            elif line_type == "character":
                font_name = "Helvetica-Bold"
                indent = 150
                rendered = text.upper()
            elif line_type == "dialogue":
                font_name = "Helvetica"
                indent = 120
                rendered = text
            elif line_type == "parenthetical":
                font_name = "Helvetica-Oblique"
                indent = 130
                rendered = text
            elif line_type == "transition":
                font_name = "Helvetica-Bold"
                indent = 280
                rendered = text.upper()
            else:
                font_name = "Helvetica"
                indent = 20
                rendered = text

            pdf.setFont(font_name, 11)

            wrapped = simpleSplit(
                rendered,
                font_name,
                11,
                width - margin_x - indent - 30,
            )

            ensure_space(len(wrapped) + 1)

            for chunk in wrapped:
                pdf.drawString(
                    margin_x + indent,
                    y,
                    chunk,
                )
                y -= 14

            y -= 2

        y -= 10

    pdf.save()
    buffer.seek(0)

    safe_name = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        title,
    ).strip("_") or "trumbo_project"

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{safe_name}.pdf"'
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
    