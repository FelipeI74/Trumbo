from __future__ import annotations

from datetime import datetime

import csv
import hashlib
from io import BytesIO, StringIO
import json
import re
from typing import Any

from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse
from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from app.database import connect, rows
from app.domain import estimate_runtime, format_seconds, screenplay_summary
from .character_service import deserialize_semantic_lines
from .scheduling_service import (
    build_project_scheduling_input,
    parse_heading_fields,
    parse_heading_fields as _parse_heading_fields,
)


_CSV_TRANSITION_SKIP = frozenset({
    "CUT TO:", "FADE IN:", "FADE OUT:", "FADE TO:", "DISSOLVE TO:",
    "CORTE A:", "CORTE:", "FUNDIDO A:", "FUNDIDO:", "DISOLVENCIA A:",
    "MATCH CUT:", "JUMP CUT:", "IRIS OUT:", "IRIS IN:", "SMASH CUT TO:",
})


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
        from reportlab.lib.utils import simpleSplit
        from reportlab.pdfgen import canvas
    except ImportError as error:
        raise HTTPException(
            500,
            "No está disponible el exportador PDF",
        ) from error

    buffer = BytesIO()

    PAGE_WIDTH, PAGE_HEIGHT = 612, 792
    pdf = canvas.Canvas(
        buffer,
        pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
        pageCompression=0,
    )

    # ---------------------------------------------------------
    # Formato profesional de guion
    # Medidas expresadas desde el borde físico de la hoja.
    # ---------------------------------------------------------

    FONT_NAME = "Courier"
    FONT_SIZE = 12
    TOP_MARGIN = 1.0 * 72
    BOTTOM_MARGIN = 1.0 * 72

    X_SCENE = 1.5 * 72
    X_ACTION = 1.5 * 72
    X_CHARACTER = 3.8 * 72
    X_DIALOGUE = 2.5 * 72
    X_PARENTHETICAL = 3.0 * 72
    X_TRANSITION = 7.5 * 72

    ACTION_WIDTH = 6.0 * 72
    DIALOGUE_WIDTH = 3.5 * 72
    PARENTHETICAL_WIDTH = 2.5 * 72
    CHARACTER_WIDTH = X_TRANSITION - X_CHARACTER

    LINE_HEIGHT = 12
    PAGE_NUMBER_Y = PAGE_HEIGHT - 0.5 * 72

    y = PAGE_HEIGHT - TOP_MARGIN
    page_number = 1

    def draw_page_number() -> None:
        if page_number <= 1:
            return

        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont(FONT_NAME, FONT_SIZE)

        pdf.drawRightString(
            PAGE_WIDTH - 1.0 * 72,
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
        y = PAGE_HEIGHT - TOP_MARGIN

    def ensure_space(points_needed: float) -> None:
        if y - points_needed < BOTTOM_MARGIN:
            new_page()

    def wrap_text(
        text: str,
        max_width: float,
    ) -> list[str]:
        return simpleSplit(
            text,
            FONT_NAME,
            FONT_SIZE,
            max_width,
        ) or [""]

    def draw_wrapped(
        wrapped: list[str],
        x: float,
    ) -> None:
        nonlocal y

        pdf.setFont(FONT_NAME, FONT_SIZE)
        pdf.setFillColorRGB(0, 0, 0)

        for chunk in wrapped:
            pdf.drawString(x, y, chunk)
            y -= LINE_HEIGHT

    author_name = (
        project["author"]
        if project and project["author"]
        else "[Nombre del Autor]"
    )
    project_type = (
        project["project_type"]
        if project and project["project_type"]
        else ""
    )
    season = project["season"] if project and project["season"] else None
    episode = project["episode"] if project and project["episode"] else None

    series_tag = ""
    if project_type in {"Serie", "Miniserie", "Sitcom"} and season and episode:
        series_tag = f" | T{season:02d}:E{episode:02d}"

    title_text = (
        project["title"]
        if project and project["title"]
        else "PROYECTO"
    )

    # --- PORTADA ---
    pdf.setFont("Courier-Bold", 24)
    pdf.drawCentredString(
        PAGE_WIDTH / 2,
        PAGE_HEIGHT - 4 * 72,
        f"{title_text}{series_tag}".upper(),
    )
    
    pdf.setFont("Courier", 14)
    pdf.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 5 * 72, "Escrito por")
    pdf.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 5.4 * 72, author_name)
    
    pdf.setFont("Courier", 12)
    pdf.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 7 * 72, "Versión de Producción")
    pdf.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 7.4 * 72, datetime.now().strftime("%d de %B de %Y"))
    
    pdf.setFont("Courier", 9)
    pdf.drawCentredString(
        PAGE_WIDTH / 2,
        1.5 * 72,
        f"© 2026 {author_name}. Documento de producción interno.",
    )

    # --- CUERPO DEL GUION ---
    pdf.showPage()
    page_number += 1
    y = PAGE_HEIGHT - TOP_MARGIN

    for scene in scenes:
        lines = scene_lines_for_export(scene)
        
        # Buscamos la posición del encabezado para alinear el número
        heading_index = -1
        for idx, line in enumerate(lines):
            if str(line.get("type") or "").strip().lower() in {
                "heading",
                "scene_heading",
            }:
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
                ensure_space(LINE_HEIGHT)
                y -= LINE_HEIGHT
                continue

            blank_lines_before = {
                "heading": 2,
                "scene_heading": 2,
                "action": 1,
                "character": 1,
                "dialogue": 0,
                "parenthetical": 0,
                "transition": 1,
            }.get(line_type, 1)

            if line_type in {"heading", "scene_heading"}:
                rendered_text = text.upper()
                x_position = X_SCENE
                max_width = ACTION_WIDTH
            elif line_type == "character":
                rendered_text = text.upper()
                x_position = X_CHARACTER
                max_width = CHARACTER_WIDTH
            elif line_type == "dialogue":
                rendered_text = text
                x_position = X_DIALOGUE
                max_width = DIALOGUE_WIDTH
            elif line_type == "parenthetical":
                rendered_text = text
                x_position = X_PARENTHETICAL
                max_width = PARENTHETICAL_WIDTH
            elif line_type == "transition":
                rendered_text = text.upper()
                x_position = X_TRANSITION
                max_width = None
            else:
                rendered_text = text
                x_position = X_ACTION
                max_width = ACTION_WIDTH

            wrapped = (
                [rendered_text]
                if max_width is None
                else wrap_text(rendered_text, max_width)
            )
            if line_type == "character":
                block_height = (
                    blank_lines_before + len(wrapped)
                ) * LINE_HEIGHT
                minimum_block_height = block_height
                dialogue_lines_in_minimum = 0

                for next_line in lines[line_index + 1 :]:
                    next_type = str(
                        next_line.get("type") or "action"
                    ).strip().lower()
                    if next_type not in {"parenthetical", "dialogue"}:
                        break

                    next_text = str(next_line.get("text") or "")
                    if not next_text.strip():
                        continue

                    next_width = (
                        PARENTHETICAL_WIDTH
                        if next_type == "parenthetical"
                        else DIALOGUE_WIDTH
                    )
                    next_wrapped = wrap_text(next_text, next_width)
                    next_height = len(next_wrapped) * LINE_HEIGHT
                    block_height += next_height

                    if dialogue_lines_in_minimum < 2:
                        minimum_dialogue_lines = min(
                            len(next_wrapped),
                            2 - dialogue_lines_in_minimum,
                        )
                        minimum_block_height += next_height
                        if next_type == "dialogue":
                            minimum_block_height -= (
                                len(next_wrapped) - minimum_dialogue_lines
                            ) * LINE_HEIGHT
                            dialogue_lines_in_minimum += minimum_dialogue_lines

                available_page_height = (
                    PAGE_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN
                )
                if (
                    y - block_height < BOTTOM_MARGIN
                    and block_height <= available_page_height
                ) or y - minimum_block_height < BOTTOM_MARGIN:
                    new_page()
            elif line_type == "action":
                available_action_lines = max(
                    0,
                    int(
                        (
                            y
                            - BOTTOM_MARGIN
                            - blank_lines_before * LINE_HEIGHT
                        )
                        // LINE_HEIGHT
                    ),
                )
                if (
                    len(wrapped) > available_action_lines
                    and available_action_lines < 3
                ):
                    new_page()

            required_space = (
                blank_lines_before + len(wrapped)
            ) * LINE_HEIGHT
            ensure_space(required_space)
            y -= blank_lines_before * LINE_HEIGHT

            if (
                line_type in {"heading", "scene_heading"}
                and include_scene_numbers
                and line_index == heading_index
            ):
                pdf.setFont(FONT_NAME, FONT_SIZE)
                pdf.drawRightString(
                    X_TRANSITION,
                    y,
                    str(scene.get("production_number") or scene.get("scene_number")),
                )

            pdf.setFont(FONT_NAME, FONT_SIZE)
            pdf.setFillColorRGB(0, 0, 0)
            if line_type == "transition":
                pdf.drawRightString(X_TRANSITION, y, rendered_text)
                y -= LINE_HEIGHT
            else:
                draw_wrapped(wrapped, x_position)

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

    scheduling_input = build_project_scheduling_input(project_id)
    cast_by_scene_id = {
        int(scene["scene_id"]): scene.get("cast", [])
        for scene in scheduling_input.get("scenes", [])
    }

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
    for scene in scheduling_input.get("scenes", []):
        for raw_name in scene.get("cast", []):
            name = str(raw_name or "").strip()
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
            if cat in {"character", "cast", "scene_cast"}:
                continue
            for cat_key, _, cat_set in CATEGORIAS_HOJA:
                if cat in cat_set:
                    items_by_cat[cat_key].append(name)
                    break

        for name in cast_by_scene_id.get(int(scene["id"]), []):
            num = cast_numbers.get(str(name).casefold())
            items_by_cat["cast"].append(
                "#%d %s" % (num, name) if num else str(name)
            )

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
            from app.main import get_project_schedule_preview

            schedule_data = get_project_schedule_preview(project_id)
        except Exception as e:
            raise HTTPException(500, f"Error al generar el plan: {str(e)}")

        from app.services.scheduling_service import build_project_scheduling_input

        scheduling_input = build_project_scheduling_input(project_id)
        scene_lookup = {s["scene_id"]: s for s in scheduling_input.get("scenes", [])}

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

    COL_ESC = 0.5 * inch
    COL_LOC = 1.0 * inch
    COL_SUB = 3.0 * inch
    COL_SINOPSIS = 4.5 * inch
    COL_INT = 6.8 * inch
    COL_LUZ = 7.4 * inch
    COL_DUR = 8.0 * inch
    COL_CAST = 8.8 * inch

    def draw_table_header(header_y):
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(COL_ESC, header_y, "ESC.")
        pdf.drawString(COL_LOC, header_y, "LOCACIÓN")
        pdf.drawString(COL_SUB, header_y, "SUBLOCACIÓN")
        pdf.drawString(COL_SINOPSIS, header_y, "SINOPSIS / ACCIÓN")
        pdf.drawString(COL_INT, header_y, "INT/EXT")
        pdf.drawString(COL_LUZ, header_y, "LUZ")
        pdf.drawString(COL_DUR, header_y, "DURACIÓN")
        pdf.drawString(COL_CAST, header_y, "ELENCO")
        header_y -= 12
        pdf.setStrokeColor(HexColor("#CCCCCC"))
        pdf.line(0.5 * inch, header_y, width - 0.5 * inch, header_y)
        pdf.setFont("Helvetica", 9)
        return header_y - 15

    # --- Jornadas ---
    table_header_drawn_on_page = False
    for day in days:
        day_num = day.get("day", "—")
        shoot_date = day.get("shoot_date")
        fecha_str = "Por definir"
        if shoot_date:
            try:
                fecha_str = datetime.strptime(
                    str(shoot_date),
                    "%Y-%m-%d",
                ).strftime("%d/%m/%Y")
            except (TypeError, ValueError):
                fecha_str = "Por definir"

        if y < 100:
            pdf.showPage()
            y = height - 50
            table_header_drawn_on_page = False

        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(0.5 * inch, y, f"JORNADA {day_num}")
        
        dur_sec = day.get("runtime_seconds", 0)
        dur_min = dur_sec // 60
        dur_s = dur_sec % 60
        pdf.setFont("Helvetica", 11)
        pdf.drawRightString(width - 0.5 * inch, y, f"Duración: {dur_min:02d}:{dur_s:02d}")
        
        pdf.setFont("Helvetica", 10)
        pdf.drawString(3.5 * inch, y, f"Fecha: {fecha_str}")
        
        y -= 20
        
        if not table_header_drawn_on_page:
            y = draw_table_header(y)
            table_header_drawn_on_page = True

        pdf.setFont("Helvetica", 9)
        
        for scene_id in day.get("scene_ids", []):
            scene = scene_lookup.get(scene_id, {})
            if not scene:
                continue

            # Chequeo de salto de página
            if y < 1 * inch + 20:
                pdf.showPage()
                y = height - 50
                pdf.setFont("Helvetica-Bold", 11)
                pdf.drawString(
                    0.5 * inch,
                    y,
                    f"JORNADA {day_num} (continuación) — Fecha: {fecha_str}",
                )
                y -= 20
                y = draw_table_header(y)
                table_header_drawn_on_page = True

            # Datos
            num = str(scene.get("production_number") or scene.get("scene_number") or scene_id)
            locacion = str(scene.get("location") or "—")
            sublocacion = str(scene.get("sublocation") or "—")
            
            # Sinopsis
            sinopsis = str(scene.get("synopsis") or "").strip()
            if not sinopsis:
                body = str(scene.get("body") or "")
                sinopsis = (
                    body[:80].replace("\n", " ") + "..."
                    if len(body) > 80
                    else body.replace("\n", " ").strip()
                )
            if not sinopsis:
                sinopsis = "Sin sinopsis"

            int_ext = str(scene.get("int_ext") or "—")
            time_of_day = str(scene.get("time_of_day") or "—")
            
            sec = scene.get("runtime_seconds", 0)
            dur = f"{sec // 60:02d}:{sec % 60:02d}"
            
            cast = scene.get("cast") or []
            cast_str = ", ".join(str(name) for name in cast) if cast else "—"

            # Truncar textos
            if len(locacion) > 20: locacion = locacion[:17] + "..."
            if len(sublocacion) > 15: sublocacion = sublocacion[:12] + "..."
            sinopsis = sinopsis.strip()
            cast_str = cast_str.strip()
            if len(sinopsis) > 30:
                sinopsis = sinopsis[:30] + "..."
            if len(cast_str) > 30:
                cast_str = cast_str[:30] + "..."

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
