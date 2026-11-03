from __future__ import annotations

import json
import os
import re
from typing import Any
import urllib.error
import urllib.request

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class DeepSeekServiceError(Exception):
    """Excepción para errores controlados al interactuar con DeepSeek API."""
    pass


DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
API_TIMEOUT_SECONDS = 30
MAX_SUGGESTIONS = 30

VALID_CATEGORIES: frozenset[str] = frozenset({
    "animal",
    "character",
    "equipment",
    "extra",
    "furniture",
    "fx",
    "location",
    "makeup",
    "prop",
    "set_dressing",
    "special_effect",
    "stunt",
    "vehicle",
    "wardrobe",
})


def build_system_prompt(known_elements: list[str] | None = None) -> str:
    """Construye el prompt de sistema inyectando los elementos ya detectados por el motor local."""
    known_str = ", ".join(known_elements) if known_elements else "ninguno"
    return (
        "Eres un experto 1er Asistente de Dirección de cine en Latinoamérica.\n"
        "Analiza el texto de la escena y extrae el desglose de producción.\n\n"
        "REGLAS ESTRICTAS:\n"
        "1. IDIOMA: Responde SIEMPRE en ESPAÑOL (ej. \"HOMBRE\", \"CONDUCTOR\", \"Mochila\").\n"
        "2. STUNTS: Si hay caídas, golpes, vehículos a alta velocidad o riesgo físico (ej. \"frenazo brusco\", \"mejilla aplastada\"), "
        "DEBES agregar la categoría \"Stunt\" (ej. \"Doble de acción para HOMBRE\").\n"
        "3. CONTEXTO: Si están dentro de un AUTO, el \"Cinturón\" es del auto, no vestuario. "
        "El \"Frente\" es una dirección, no un animal.\n"
        f"4. NO REPETIR: El motor local ya ha detectado [{known_str}]. "
        "Tu tarea es SOLO sugerir elementos nuevos (como Stunts, VFX o errores corregidos) que el motor local no vio.\n\n"
        "Devuelve estrictamente un JSON con esta estructura:\n"
        "[\n"
        "  {\"category\": \"Stunt\", \"name\": \"Doble de acción para HOMBRE\"}\n"
        "]"
    )


SYSTEM_PROMPT = build_system_prompt()


def _clean_json_markdown(text: str) -> str:
    """Remueve bloques delimitadores markdown (```json ... ```) si están presentes."""
    stripped = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return stripped


def analyze_scene_with_deepseek(
    heading: str,
    body: str,
    known_elements: list[str] | None = None,
) -> list[dict[str, str]]:
    """Analiza una escena usando la API de DeepSeek para sugerir elementos de desglose.

    Parámetros:
        heading: Encabezado de la escena (ej. 'INT. COCINA - DIA').
        body: Contenido o acciones y diálogos de la escena.
        known_elements: Lista de elementos previamente detectados para evitar duplicación.

    Retorna:
        Lista de hasta 30 sugerencias sin duplicados, cada una con 'category' y 'name'.

    Lanza:
        DeepSeekServiceError si la API key falta, expira el timeout, ocurre un error HTTP,
        la respuesta se trunca o no cumple con el formato esperado.
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip().strip('"').strip("'")
    if not api_key:
        raise DeepSeekServiceError(
            "La variable de entorno DEEPSEEK_API_KEY no está configurada o está vacía."
        )

    model = os.environ.get("DEEPSEEK_MODEL", "").strip() or DEFAULT_DEEPSEEK_MODEL
    url = DEEPSEEK_API_URL

    system_content = build_system_prompt(known_elements)
    user_content = (
        f"Analiza la siguiente escena de guion audiovisual y sugiere elementos nuevos "
        f"para el desglose de producción en formato JSON.\n\n"
        f"ENCABEZADO:\n{heading.strip()}\n\n"
        f"CUERPO:\n{body.strip()}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 2048,
    }

    req_data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=req_data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            raw_response = response.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        status = err.code
        if status in (401, 403):
            detail = "Credenciales de DeepSeek inválidas o no autorizadas."
        elif status == 404:
            detail = "El modelo o endpoint de DeepSeek no fue encontrado."
        elif status == 429:
            detail = "Cuota de DeepSeek excedida o límite de solicitudes alcanzado."
        elif status in (500, 502, 503, 504):
            detail = "El servicio de DeepSeek no se encuentra disponible temporalmente."
        else:
            detail = f"Error HTTP {status} al comunicarse con DeepSeek."
        raise DeepSeekServiceError(detail) from None
    except urllib.error.URLError as err:
        if isinstance(err.reason, TimeoutError) or "timed out" in str(err.reason).lower():
            raise DeepSeekServiceError(
                f"Tiempo de espera agotado ({API_TIMEOUT_SECONDS}s) al conectar con DeepSeek."
            ) from None
        raise DeepSeekServiceError(
            "Error de red o conexión al intentar comunicarse con DeepSeek."
        ) from None
    except TimeoutError:
        raise DeepSeekServiceError(
            f"Tiempo de espera agotado ({API_TIMEOUT_SECONDS}s) al conectar con DeepSeek."
        ) from None

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError:
        raise DeepSeekServiceError(
            "La respuesta del servidor DeepSeek no tiene un formato JSON decodificable."
        ) from None

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise DeepSeekServiceError("DeepSeek no devolvió opciones de respuesta.")

    choice = choices[0]
    message = choice.get("message") if isinstance(choice, dict) else None
    if not isinstance(message, dict):
        raise DeepSeekServiceError("Formato de mensaje inesperado en la respuesta de DeepSeek.")

    raw_text = message.get("content")
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise DeepSeekServiceError("La respuesta de DeepSeek contiene contenido vacío.")

    cleaned_text = _clean_json_markdown(raw_text)
    try:
        parsed = json.loads(cleaned_text)
    except json.JSONDecodeError:
        raise DeepSeekServiceError(
            "El contenido generado por DeepSeek no tiene un formato JSON válido."
        ) from None

    if isinstance(parsed, list):
        parsed_items = parsed
    elif isinstance(parsed, dict):
        found_list = None
        for key in ("elements", "items", "suggestions", "breakdown", "desglose", "stunts"):
            if isinstance(parsed.get(key), list):
                found_list = parsed[key]
                break
        if found_list is None:
            for val in parsed.values():
                if isinstance(val, list):
                    found_list = val
                    break
        if found_list is not None:
            parsed_items = found_list
        else:
            raise DeepSeekServiceError(
                "El JSON devuelto por DeepSeek no contiene una lista de elementos."
            )
    else:
        raise DeepSeekServiceError(
            "La respuesta de DeepSeek debe ser una lista o un objeto JSON con elementos."
        )

    validated_suggestions: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()

    for item in parsed_items:
        if not isinstance(item, dict):
            continue

        raw_category = item.get("category")
        raw_name = item.get("name")

        if not isinstance(raw_category, str) or not isinstance(raw_name, str):
            continue

        category = raw_category.strip().casefold()
        name = raw_name.strip()

        if not category or not name:
            continue

        if category not in VALID_CATEGORIES:
            continue

        norm_key = (category, name.casefold())
        if norm_key in seen_keys:
            continue

        seen_keys.add(norm_key)
        validated_suggestions.append({
            "category": category,
            "name": name,
        })

        if len(validated_suggestions) >= MAX_SUGGESTIONS:
            break

    return validated_suggestions
