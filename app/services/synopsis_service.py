from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request


class SynopsisServiceError(Exception):
    """Raised when the configured AI provider cannot suggest a synopsis."""


DEFAULT_MODELS = {
    "gemini": "gemini-3.8-flash",
    "openrouter": "openrouter/free",
    "deepseek": "deepseek-chat",
}

SYSTEM_PROMPT = (
    "BAJO NINGUNA CIRCUNSTANCIA muestres tu proceso de pensamiento, ni listas de análisis, ni texto introductorio. Devuelve SOLO la línea final del resumen.\n"
    "Eres un experto 1er Asistente de Dirección. Tu tarea es resumir la escena en un \"logline\" para una Hoja de Llamado.\n\n"
    "REGLAS ESTRICTAS:\n"
    "1. MÁXIMO 2 LÍNEAS (o 20 palabras).\n"
    "2. Ve directo a la acción o el conflicto principal.\n"
    "3. No uses frases introductorias como \"En esta escena...\".\n"
    "4. Escribe en tercera persona.\n"
    "5. Devuelve ÚNICAMENTE el texto del resumen, sin comillas, sin markdown, sin saltos de línea.\n\n"
    "Ejemplo de salida: Pasajero en peligro por conducción temeraria."
)


def suggest_scene_synopsis(heading: str, body: str) -> str:
    provider = os.environ.get("AI_PROVIDER", "gemini").strip().lower()
    if provider not in DEFAULT_MODELS:
        raise SynopsisServiceError("El proveedor de IA configurado no es válido.")

    if provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
        model = os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODELS[provider]
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }
        payload = {
            "systemInstruction": {
                "parts": [{
                    "text": SYSTEM_PROMPT,
                }]
            },
            "contents": [{
                "role": "user",
                "parts": [{
                    "text": f"ENCABEZADO:\n{heading.strip()}\n\nESCENA:\n{body.strip()}"
                }],
            }],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 256},
        }
    else:
        if provider == "openrouter":
            api_key = (
                os.environ.get("OPENROUTER_API_KEY", "").strip().strip('"').strip("'")
                or (
                    os.environ.get("DEEPSEEK_API_KEY", "").strip().strip('"').strip("'")
                    if os.environ.get("DEEPSEEK_API_KEY", "").strip().startswith("sk-or-")
                    else ""
                )
            )
            model = (
                os.environ.get("OPENROUTER_MODEL", "").strip()
                or DEFAULT_MODELS[provider]
            )
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "ADUMN Screenplay Assistant",
            }
        else:
            api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip().strip('"').strip("'")
            model = (
                os.environ.get("DEEPSEEK_MODEL", "").strip()
                or DEFAULT_MODELS[provider]
            )
            url = "https://api.deepseek.com/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": f"ENCABEZADO:\n{heading.strip()}\n\nESCENA:\n{body.strip()}",
                },
            ],
            "temperature": 0.3,
            "max_tokens": 256,
        }

    if not api_key:
        raise SynopsisServiceError(
            f"No hay una clave configurada para el proveedor {provider}."
        )

    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise SynopsisServiceError(
            f"El proveedor de IA respondió con error HTTP {error.code}."
        ) from None
    except (urllib.error.URLError, TimeoutError):
        raise SynopsisServiceError(
            "No fue posible conectar con el proveedor de IA."
        ) from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SynopsisServiceError(
            "El proveedor de IA devolvió una respuesta inválida."
        ) from None

    if not isinstance(data, dict):
        raise SynopsisServiceError(
            "El proveedor de IA devolvió una respuesta inválida."
        )

    if provider == "gemini":
        candidates = data.get("candidates")
        candidate = candidates[0] if isinstance(candidates, list) and candidates else {}
        parts = (
            candidate.get("content", {}).get("parts", [])
            if isinstance(candidate, dict)
            else []
        )
        text = parts[0].get("text", "") if parts and isinstance(parts[0], dict) else ""
    else:
        choices = data.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices else {}
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        text = message.get("content", "") if isinstance(message, dict) else ""

    synopsis = text.strip() if isinstance(text, str) else ""
    if synopsis:
        if synopsis.startswith("```"):
            synopsis = re.sub(r"^```[a-zA-Z]*\s*", "", synopsis)
            synopsis = re.sub(r"\s*```$", "", synopsis).strip()
        synopsis = synopsis.strip('"\'«»“”').strip()

    if "Analyze the Request" in synopsis or "1. **" in synopsis[:30]:
        lines = [line.strip() for line in synopsis.split("\n") if line.strip()]
        if lines:
            synopsis = lines[-1]

    words = synopsis.split()
    if len(words) > 25:
        synopsis = " ".join(words[:25]) + "..."

    if not synopsis:
        raise SynopsisServiceError("El proveedor de IA no devolvió una sinopsis.")
    return synopsis
