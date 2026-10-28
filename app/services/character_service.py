from __future__ import annotations

import json
import re
from typing import Any
import unicodedata

from fastapi import HTTPException

from app.database import connect
from app.domain import parse_character_cue, resolve_character_alias


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


def get_project_character_names(
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

_get_project_character_names = get_project_character_names


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
                # Aplicar alias al nombre
                original_name = personaje["name"]
                normalized = normalize_name(original_name)
                name = aliases_map.get(normalized, original_name)
                
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
        body_text = str(scene["body"] or "").upper()
        
        for known_name in known_characters:
            if known_name in seen_in_scene:
                continue
                
            pattern = rf"(?<!\w){re.escape(known_name)}(?!\w)"
            match = re.search(pattern, body_text, re.IGNORECASE)
            
            if match:
                prefix = body_text[:match.start()].strip().upper()
                if prefix.endswith("DE") or prefix.endswith("DEL"):
                    continue 
                
                # Aplicar alias al nombre
                normalized = normalize_name(known_name)
                final_name = aliases_map.get(normalized, known_name)
                key = final_name.casefold()
                
                if key not in grouped:
                    grouped[key] = {"name": final_name, "scene_numbers": []}
                if scene_number not in grouped[key]["scene_numbers"]:
                    grouped[key]["scene_numbers"].append(scene_number)
                seen_in_scene.add(key)

    # --- APLICAR ALIAS Y UNIFICAR ---
    unified = {}
    for char in grouped.values():
        normalized = normalize_name(char["name"])
        primary = aliases_map.get(normalized, char["name"])
        
        if primary not in unified:
            unified[primary] = {
                "name": primary,
                "scene_count": 0,
                "first_scene": char["scene_numbers"][0] if char["scene_numbers"] else 0,
                "scene_numbers": [],
            }
        
        unified[primary]["scene_count"] += len(char["scene_numbers"])
        unified[primary]["scene_numbers"].extend(char["scene_numbers"])
        unified[primary]["scene_numbers"] = sorted(set(unified[primary]["scene_numbers"]))

    characters = list(unified.values())
    characters.sort(key=lambda c: c["name"].casefold())

    return {"characters": characters}
