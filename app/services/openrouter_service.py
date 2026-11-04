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


class OpenRouterServiceError(Exception):
    """Excepción para errores controlados al interactuar con OpenRouter API."""
    pass


DEFAULT_OPENROUTER_MODEL = "openrouter/free"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
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
        "]\n\n"
        "Devuelve ÚNICAMENTE el array JSON, sin bloques de código markdown ni texto adicional. Si no hay sugerencias, devuelve []."
    )


SYSTEM_PROMPT = build_system_prompt()


def _clean_json_markdown(text: str) -> str:
    """Remueve bloques delimitadores markdown (```json ... ```) si están presentes, o extrae el JSON."""
    stripped = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # En caso de que el modelo incluya texto introductorio o de cierre alrededor del JSON
    array_match = re.search(r"(\[[\s\S]*\])", stripped)
    if array_match:
        return array_match.group(1).strip()
    object_match = re.search(r"(\{[\s\S]*\})", stripped)
    if object_match:
        return object_match.group(1).strip()
    return stripped


def analyze_scene_with_openrouter(
    heading: str,
    body: str,
    known_elements: list[str] | None = None,
) -> list[dict[str, str]]:
    """Analiza una escena usando la API de OpenRouter para sugerir elementos de desglose.

    Parámetros:
        heading: Encabezado de la escena (ej. 'INT. COCINA - DIA').
        body: Contenido o acciones y diálogos de la escena.
        known_elements: Lista de elementos previamente detectados para evitar duplicación.

    Retorna:
        Lista de hasta 30 sugerencias sin duplicados, cada una con 'category' y 'name'.

    Lanza:
        OpenRouterServiceError si la API key falta, expira el timeout, ocurre un error HTTP,
        la respuesta se trunca o no cumple con el formato esperado.
    """
    api_key = (
        os.environ.get("OPENROUTER_API_KEY", "").strip().strip('"').strip("'")
        or (os.environ.get("DEEPSEEK_API_KEY", "").strip().strip('"').strip("'") if os.environ.get("DEEPSEEK_API_KEY", "").startswith("sk-or-") else "")
    )
    if not api_key:
        raise OpenRouterServiceError(
            "La variable de entorno OPENROUTER_API_KEY no está configurada o está vacía."
        )

    model = os.environ.get("OPENROUTER_MODEL", "").strip() or DEFAULT_OPENROUTER_MODEL
    url = OPENROUTER_API_URL

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
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "ADUMN Screenplay Breakdown",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            raw_response = response.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        status = err.code
        if status in (401, 403):
            detail = "Credenciales de OpenRouter inválidas o no autorizadas."
        elif status == 402:
            detail = "Fondos insuficientes en la cuenta de OpenRouter."
        elif status == 404:
            detail = "El modelo o endpoint de OpenRouter no fue encontrado."
        elif status == 429:
            detail = "Límite de solicitudes de OpenRouter alcanzado o modelo saturado temporalmente."
        elif status in (500, 502, 503, 504):
            detail = "El servicio de OpenRouter no se encuentra disponible temporalmente."
        else:
            detail = f"Error HTTP {status} al comunicarse con OpenRouter."
        raise OpenRouterServiceError(detail) from None
    except urllib.error.URLError as err:
        if isinstance(err.reason, TimeoutError) or "timed out" in str(err.reason).lower():
            raise OpenRouterServiceError(
                f"Tiempo de espera agotado ({API_TIMEOUT_SECONDS}s) al conectar con OpenRouter."
            ) from None
        raise OpenRouterServiceError(
            "Error de red o conexión al intentar comunicarse con OpenRouter."
        ) from None
    except TimeoutError:
        raise OpenRouterServiceError(
            f"Tiempo de espera agotado ({API_TIMEOUT_SECONDS}s) al conectar con OpenRouter."
        ) from None

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError:
        raise OpenRouterServiceError(
            "La respuesta del servidor OpenRouter no tiene un formato JSON decodificable."
        ) from None

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenRouterServiceError("OpenRouter no devolvió opciones de respuesta.")

    choice = choices[0]
    message = choice.get("message") if isinstance(choice, dict) else None
    if not isinstance(message, dict):
        raise OpenRouterServiceError("Formato de mensaje inesperado en la respuesta de OpenRouter.")

    raw_text = message.get("content")
    if not isinstance(raw_text, str) or not raw_text.strip():
        # Si el contenido está vacío, devolver lista vacía [] sin lanzar error
        return []

    cleaned_text = _clean_json_markdown(raw_text.strip())
    if not cleaned_text:
        return []

    try:
        parsed = json.loads(cleaned_text)
    except json.JSONDecodeError:
        raise OpenRouterServiceError(
            "El contenido generado por OpenRouter no tiene un formato JSON válido."
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
            raise OpenRouterServiceError(
                "El JSON devuelto por OpenRouter no contiene una lista de elementos."
            )
    else:
        raise OpenRouterServiceError(
            "La respuesta de OpenRouter debe ser una lista o un objeto JSON con elementos."
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

