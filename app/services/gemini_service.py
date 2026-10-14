from __future__ import annotations

import json
import os
import re
from typing import Any
import urllib.error
import urllib.request


class GeminiServiceError(Exception):
    """Excepción para errores controlados al interactuar con Gemini API."""
    pass


DEFAULT_MODEL = "gemini-3.8-flash"
API_TIMEOUT_SECONDS = 30
MAX_SUGGESTIONS = 30

# Categorías oficiales de desglose en ADÜMN (incluye furniture y set_dressing)
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


def _clean_json_markdown(text: str) -> str:
    """Remueve bloques delimitadores markdown (```json ... ```) si están presentes."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def analyze_scene_with_gemini(heading: str, body: str) -> list[dict[str, str]]:
    """
    Analiza una escena audiovisual usando la API de Gemini para sugerir
    elementos de desglose de producción en formato estructurado.

    Parámetros:
        heading: Encabezado de la escena (ej. "INT. COCINA - NOCHE").
        body: Contenido o acciones y diálogos de la escena.

    Retorna:
        Lista de hasta 30 sugerencias sin duplicados, cada una con 'category' y 'name'.

    Lanza:
        GeminiServiceError si la API key falta, expira el timeout, ocurre un error HTTP,
        la respuesta se trunca o no cumple con el formato esperado.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise GeminiServiceError(
            "La variable de entorno GEMINI_API_KEY no está configurada o está vacía."
        )

    model = os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    # Se envía exclusivamente el encabezado y el cuerpo de la escena
    prompt = (
        f"Analiza la siguiente escena de guion audiovisual y sugiere los elementos "
        f"necesarios para el desglose de producción.\n\n"
        f"ENCABEZADO:\n{heading.strip()}\n\n"
        f"CUERPO:\n{body.strip()}"
    )

    system_instruction = (
        "Eres un asistente experto en desglose de producción cinematográfica y televisiva. "
        "Devuelve únicamente una lista JSON de objetos con las propiedades 'category' y 'name' en español. "
        "No agregues explicaciones, introducciones ni texto fuera del JSON."
    )

    sorted_categories = sorted(VALID_CATEGORIES)

    payload: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_instruction}],
        },
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "category": {
                            "type": "STRING",
                            "enum": sorted_categories,
                        },
                        "name": {"type": "STRING"},
                    },
                    "required": ["category", "name"],
                },
            },
            "temperature": 0.2,
            "maxOutputTokens": 2048,
        },
    }

    req_data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=req_data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,  # Clave exclusivamente en encabezado, nunca en URL
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            raw_response = response.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        status = err.code
        # Mensajes estrictamente controlados por código de estado, sin reflejar payloads externos
        if status in (401, 403):
            detail = "Credenciales de Gemini inválidas o no autorizadas."
        elif status == 404:
            detail = "El modelo de Gemini especificado no existe o no se encuentra disponible."
        elif status == 429:
            detail = "Cuota de Gemini excedida o límite de solicitudes alcanzado."
        elif status == 400:
            detail = "Solicitud rechazada por la API de Gemini (parámetros o formato inválidos)."
        elif status == 503:
            detail = "Gemini está experimentando una demanda elevada. Inténtalo nuevamente más tarde."
        elif status >= 500:
            detail = "El servicio de Gemini no se encuentra disponible temporalmente."
        else:
            detail = f"Error HTTP {status} al comunicarse con el servicio de Gemini."

        raise GeminiServiceError(detail) from None

    except urllib.error.URLError as err:
        if isinstance(err.reason, TimeoutError) or "timed out" in str(err.reason).lower():
            raise GeminiServiceError(
                f"Tiempo de espera agotado ({API_TIMEOUT_SECONDS}s) al conectar con Gemini."
            ) from None
        raise GeminiServiceError(
            "Error de red o conexión al intentar comunicarse con Gemini."
        ) from None
    except TimeoutError:
        raise GeminiServiceError(
            f"Tiempo de espera agotado ({API_TIMEOUT_SECONDS}s) al conectar con Gemini."
        ) from None

    # Procesamiento y validación del JSON devuelto
    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError:
        raise GeminiServiceError(
            "La respuesta del servidor no tiene un formato JSON decodificable."
        ) from None

    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise GeminiServiceError("Gemini no devolvió candidatos de respuesta.")

    candidate = candidates[0]
    if not isinstance(candidate, dict):
        raise GeminiServiceError("Formato de candidato inesperado en la respuesta de Gemini.")

    # Verificación de finalización limpia; rechaza truncamientos por MAX_TOKENS u otras anomalías
    finish_reason = candidate.get("finishReason")
    if finish_reason != "STOP":
        raise GeminiServiceError(
            f"La generación de Gemini fue incompleta o anómala (finishReason: {finish_reason or 'desconocido'})."
        )

    content = candidate.get("content")
    if not isinstance(content, dict):
        raise GeminiServiceError("La respuesta de Gemini no contiene bloque de contenido.")

    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        raise GeminiServiceError("La respuesta de Gemini no contiene partes de texto.")

    first_part = parts[0]
    if not isinstance(first_part, dict):
        raise GeminiServiceError("Formato de parte inesperado en la respuesta de Gemini.")

    raw_text = first_part.get("text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise GeminiServiceError("La respuesta de Gemini contiene texto vacío.")

    cleaned_text = _clean_json_markdown(raw_text)
    try:
        parsed_items = json.loads(cleaned_text)
    except json.JSONDecodeError:
        raise GeminiServiceError(
            "El contenido generado por Gemini no tiene un formato JSON válido."
        ) from None

    if not isinstance(parsed_items, list):
        raise GeminiServiceError("La respuesta de Gemini debe ser una lista de elementos.")

    # Validación estricta de tipos, descarte de categorías desconocidas, normalización y deduplicación
    validated_suggestions: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()

    for item in parsed_items:
        if not isinstance(item, dict):
            continue

        raw_category = item.get("category")
        raw_name = item.get("name")

        # Validación estricta: deben ser instancias de str y no cadenas vacías (no convierte None, listas ni objetos)
        if not isinstance(raw_category, str) or not isinstance(raw_name, str):
            continue

        category = raw_category.strip().casefold()
        name = raw_name.strip()

        if not category or not name:
            continue

        # Solo se aceptan categorías conocidas del desglose de ADÜMN
        if category not in VALID_CATEGORIES:
            continue

        # Deduplicación mediante strip() y casefold()
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

