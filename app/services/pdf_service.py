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
