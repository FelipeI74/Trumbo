from app.services.engine_analysis_adapter import analyze_scene_with_engine


def test_adapter_builds_frontend_analysis_shape() -> None:
    result = analyze_scene_with_engine(
        scene_id=7,
        heading="INT. CASA - DIA",
        body="MARTA\nHola.\nJUAN\nQué tal?",
    )

    assert result["counts"]["heading"] == 1
    assert result["counts"]["character"] == 2
    assert result["counts"]["dialogue"] == 2
    assert result["characters"] == ["MARTA", "JUAN"]

    first_element = result["elements"][0]
    assert first_element["line_number"] == 1
    assert first_element["type"] == "heading"
    assert first_element["text"] == "INT. CASA - DIA"
    assert first_element["confidence"] == 1.0


def test_adapter_uses_confidence_one_for_detected_blocks() -> None:
    result = analyze_scene_with_engine(
        scene_id=3,
        heading="",
        body="MARTA\nHola.",
    )

    assert len(result["elements"]) >= 2
    assert all(item["confidence"] == 1.0 for item in result["elements"])


def test_adapter_ignores_scene_numbering_but_keeps_real_characters() -> None:
    result = analyze_scene_with_engine(
        scene_id=12,
        heading="INT. CASA - DIA",
        body="1\n1A\n1A.\nANDRÉS\nHola.\nSIMÓN\nAdelante.",
    )

    assert "1" not in result["characters"]
    assert "1A" not in result["characters"]
    assert "1A." not in result["characters"]
    assert "ANDRÉS" in result["characters"]
    assert "SIMÓN" in result["characters"]


def test_adapter_returns_events_and_production_elements() -> None:
    result = analyze_scene_with_engine(
        scene_id=9,
        heading="INT. SALA DE CONTROL - DÍA",
        body="Ravest toma el teléfono.\n\nEnrique mira el aparato.",
    )

    assert "counts" in result
    assert "characters" in result
    assert "elements" in result
    assert "events" in result
    assert "production_elements" in result

    assert result["events"]
    assert result["events"][0]["title"] == "Ravest toma el teléfono"
    assert result["events"][0]["subject"] == "Ravest"
    assert result["events"][0]["verb"] == "toma"
    assert result["events"][0]["object"] == "el teléfono"

    assert any(
        item["name"] == "Teléfono"
        for item in result["production_elements"]
    )


def test_adapter_returns_extended_production_categories() -> None:
    result = analyze_scene_with_engine(
        scene_id=10,
        heading="EXT. CAMPO - DÍA",
        body="Un extra acaricia un perro junto a una grúa. Lleva maquillaje.",
    )

    categories = {
        item["element_type"]
        for item in result["production_elements"]
    }

    assert "extra" in categories
    assert "animal" in categories
    assert "equipment" in categories
    assert "makeup" in categories


def test_adapter_serializes_stunt_production_elements() -> None:
    result = analyze_scene_with_engine(
        scene_id=11,
        heading="EXT. CALLE - DÍA",
        body="El personaje cae sobre el pavimento.",
    )

    assert any(
        item["name"] == "Caída"
        and item["element_type"] == "stunt"
        for item in result["production_elements"]
    )


def test_adapter_preserves_semantic_actions_after_dialogue() -> None:
    result = analyze_scene_with_engine(
        scene_id=194,
        heading="INT. OFICINA DE LIDIA - DÍA",
        body=(
            "LIDIA\n"
            "No te oigo.\n"
            "Cuando repentinamente un zorzal golpea contra su ventana.\n"
            "Se tropieza con la botella y cae sobre el escritorio."
        ),
        semantic_lines=[
            {"type": "heading", "text": "INT. OFICINA DE LIDIA - DÍA"},
            {"type": "character", "text": "LIDIA"},
            {"type": "dialogue", "text": "No te oigo."},
            {
                "type": "action",
                "text": "Cuando repentinamente un zorzal golpea contra su ventana.",
            },
            {
                "type": "action",
                "text": "Se tropieza con la botella y cae sobre el escritorio.",
            },
        ],
    )

    action_lines = {
        item["text"]
        for item in result["elements"]
        if item["type"] == "action"
    }
    production_elements = {
        (item["name"], item["element_type"])
        for item in result["production_elements"]
    }

    assert "Cuando repentinamente un zorzal golpea contra su ventana." in action_lines
    assert "Se tropieza con la botella y cae sobre el escritorio." in action_lines
    assert ("Caída", "stunt") in production_elements
    assert ("Impacto contra ventana", "special_effect") in production_elements