from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import connect, initialize, rows
from .domain import estimate_runtime
from .schemas import BreakdownItemCreate, NoteCreate, ProjectCreate, ProjectUpdate, SceneCreate, SceneUpdate

app = FastAPI(title="Trumbo Alpha", version="0.1.0")
STATIC_DIR = Path(__file__).resolve().parent / "static"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def startup() -> None:
    initialize()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/projects")
def list_projects() -> list[dict]:
    with connect() as connection:
        return rows(connection, "SELECT * FROM projects ORDER BY updated_at DESC, id DESC")


@app.post("/api/projects")
def create_project(payload: ProjectCreate) -> dict:
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO projects(title, format) VALUES (?, ?)",
            (payload.title.strip(), payload.format.strip()),
        )
        project_id = cursor.lastrowid
        connection.execute("INSERT INTO scenes(project_id, scene_number) VALUES (?, 1)", (project_id,))
        return dict(connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())


@app.patch("/api/projects/{project_id}")
def update_project(project_id: int, payload: ProjectUpdate) -> dict:
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "No hay cambios")

    assignments = ", ".join(f"{key} = ?" for key in data)
    values = [value.strip() if isinstance(value, str) else value for value in data.values()]
    values.append(project_id)

    with connect() as connection:
        cursor = connection.execute(
            f"UPDATE projects SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            tuple(values),
        )
        if cursor.rowcount == 0:
            raise HTTPException(404, "Proyecto no encontrado")
        return dict(connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())


@app.get("/api/projects/{project_id}")
def get_project(project_id: int) -> dict:
    with connect() as connection:
        project = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if project is None:
            raise HTTPException(404, "Proyecto no encontrado")

        scenes = rows(connection, "SELECT * FROM scenes WHERE project_id = ? ORDER BY scene_number", (project_id,))
        for scene in scenes:
            scene["notes"] = rows(
                connection,
                "SELECT * FROM notes WHERE scene_id = ? ORDER BY id DESC",
                (scene["id"],),
            )
            scene["breakdown_items"] = rows(
                connection,
                "SELECT * FROM breakdown_items WHERE scene_id = ? ORDER BY category, name",
                (scene["id"],),
            )

        return {"project": dict(project), "scenes": scenes}


@app.post("/api/projects/{project_id}/scenes")
def create_scene(project_id: int, payload: SceneCreate) -> dict:
    runtime = estimate_runtime(payload.body)
    with connect() as connection:
        exists = connection.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
        if exists is None:
            raise HTTPException(404, "Proyecto no encontrado")

        next_number = connection.execute(
            "SELECT COALESCE(MAX(scene_number), 0) + 1 FROM scenes WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]

        cursor = connection.execute(
            """
            INSERT INTO scenes(project_id, scene_number, heading, body, synopsis, runtime_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, next_number, payload.heading, payload.body, payload.synopsis, runtime.seconds),
        )
        return dict(connection.execute("SELECT * FROM scenes WHERE id = ?", (cursor.lastrowid,)).fetchone())


@app.patch("/api/scenes/{scene_id}")
def update_scene(scene_id: int, payload: SceneUpdate) -> dict:
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "No hay cambios")

    with connect() as connection:
        current = connection.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,)).fetchone()
        if current is None:
            raise HTTPException(404, "Escena no encontrada")

        new_heading = data.get("heading", current["heading"])
        new_body = data.get("body", current["body"])

        if new_heading != current["heading"] or new_body != current["body"]:
            connection.execute(
                "INSERT INTO revisions(scene_id, previous_heading, previous_body) VALUES (?, ?, ?)",
                (scene_id, current["heading"], current["body"]),
            )

        data["runtime_seconds"] = estimate_runtime(new_body).seconds
        assignments = ", ".join(f"{key} = ?" for key in data)
        values = list(data.values()) + [scene_id]

        connection.execute(
            f"UPDATE scenes SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            tuple(values),
        )
        connection.execute(
            """
            UPDATE projects SET updated_at = CURRENT_TIMESTAMP
            WHERE id = (SELECT project_id FROM scenes WHERE id = ?)
            """,
            (scene_id,),
        )
        return dict(connection.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,)).fetchone())


@app.post("/api/scenes/{scene_id}/notes")
def add_note(scene_id: int, payload: NoteCreate) -> dict:
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO notes(scene_id, category, body) VALUES (?, ?, ?)",
            (scene_id, payload.category, payload.body.strip()),
        )
        return dict(connection.execute("SELECT * FROM notes WHERE id = ?", (cursor.lastrowid,)).fetchone())


@app.post("/api/scenes/{scene_id}/breakdown")
def add_breakdown_item(scene_id: int, payload: BreakdownItemCreate) -> dict:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO breakdown_items(scene_id, category, name, source, state)
            VALUES (?, ?, ?, ?, ?)
            """,
            (scene_id, payload.category.strip(), payload.name.strip(), payload.source, payload.state),
        )
        return dict(
            connection.execute("SELECT * FROM breakdown_items WHERE id = ?", (cursor.lastrowid,)).fetchone()
        )


@app.get("/api/projects/{project_id}/runtime")
def project_runtime(project_id: int) -> dict:
    with connect() as connection:
        total = connection.execute(
            "SELECT COALESCE(SUM(runtime_seconds), 0) FROM scenes WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        minutes, seconds = divmod(total, 60)
        return {"seconds": total, "formatted": f"{minutes:02d}:{seconds:02d}"}
