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
