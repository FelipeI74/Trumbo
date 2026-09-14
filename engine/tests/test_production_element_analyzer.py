from engine.core.block import Block
from engine.core.types.block_type import BlockType
from engine.core.types.production_element_type import ProductionElementType
from engine.services.analyzers.production_element_analyzer import (
    ProductionElementAnalyzer,
)


def test_production_element_analyzer_detects_known_elements() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="Ravest toma el teléfono.",
        ),
        Block(
            id="2",
            scene_id="1",
            order=2,
            block_type=BlockType.DIALOGUE,
            content="¿Quién llamó?",
        ),
        Block(
            id="3",
            scene_id="1",
            order=3,
            block_type=BlockType.ACTION,
            content="Enrique deja los papeles sobre la mesa.",
        ),
    ]

    analyzer = ProductionElementAnalyzer()
    elements = analyzer.extract(blocks)

    assert len(elements) == 3

    assert elements[0].name == "Mesa"
    assert elements[0].element_type == ProductionElementType.FURNITURE

    assert elements[1].name == "Papeles"
    assert elements[1].element_type == ProductionElementType.PROP

    assert elements[2].name == "Teléfono"
    assert elements[2].element_type == ProductionElementType.PROP


def test_production_element_analyzer_detects_extended_categories() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content=(
                "Un extra acaricia un perro junto a una grúa. "
                "Lleva maquillaje."
            ),
        ),
    ]

    analyzer = ProductionElementAnalyzer()
    elements = analyzer.extract(blocks)

    categories = {
        element.element_type
        for element in elements
    }

    assert ProductionElementType.EXTRA in categories
    assert ProductionElementType.ANIMAL in categories
    assert ProductionElementType.EQUIPMENT in categories
    assert ProductionElementType.MAKEUP in categories


def test_production_element_analyzer_detects_wardrobe() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="El personaje se pone un abrigo.",
        ),
        Block(
            id="2",
            scene_id="1",
            order=2,
            block_type=BlockType.ACTION,
            content="El personaje usa una chaqueta.",
        ),
        Block(
            id="3",
            scene_id="1",
            order=3,
            block_type=BlockType.ACTION,
            content="El personaje calza botas.",
        ),
    ]

    analyzer = ProductionElementAnalyzer()
    elements = analyzer.extract(blocks)

    wardrobe = {
        element.name
        for element in elements
        if element.element_type == ProductionElementType.WARDROBE
    }

    assert wardrobe == {"Abrigo", "Chaqueta", "Botas"}


def test_production_element_analyzer_detects_general_breakdown_categories() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content=(
                "Un extra llega en un auto con un perro. Lleva maquillaje, "
                "opera un dron y hay humo mientras usa un abrigo."
            ),
        ),
    ]

    analyzer = ProductionElementAnalyzer()
    elements = analyzer.extract(blocks)

    detected_types = {
        element.name: element.element_type
        for element in elements
    }

    assert detected_types == {
        "Abrigo": ProductionElementType.WARDROBE,
        "Auto": ProductionElementType.VEHICLE,
        "Dron": ProductionElementType.EQUIPMENT,
        "Extra": ProductionElementType.EXTRA,
        "Humo": ProductionElementType.SPECIAL_EFFECT,
        "Maquillaje": ProductionElementType.MAKEUP,
        "Perro": ProductionElementType.ANIMAL,
    }


def test_production_element_analyzer_detects_extended_wardrobe() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="Usa una camisa y una bufanda.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    assert {
        element.name: element.element_type
        for element in elements
    } == {
        "Camisa": ProductionElementType.WARDROBE,
        "Bufanda": ProductionElementType.WARDROBE,
    }


def test_production_element_analyzer_detects_extended_extras() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="Un figurante cruza la calle con otros figurantes.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    assert {
        element.name: element.element_type
        for element in elements
    } == {
        "Figurante": ProductionElementType.EXTRA,
        "Figurantes": ProductionElementType.EXTRA,
    }


def test_production_element_analyzer_detects_extended_vehicles() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="La camioneta espera junto a la lancha y la avioneta.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    assert {
        element.name: element.element_type
        for element in elements
    } == {
        "Avioneta": ProductionElementType.VEHICLE,
        "Camioneta": ProductionElementType.VEHICLE,
        "Lancha": ProductionElementType.VEHICLE,
    }


def test_production_element_analyzer_detects_requested_vehicle_types() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content=(
                "La camioneta, el camión, el jeep, el SUV, el furgón, "
                "la furgoneta, la van, el minibús, el bus, el taxi, "
                "la motocicleta, la moto, la bicicleta, la ambulancia, "
                "la patrulla y el tractor esperan."
            ),
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    detected_types = {
        element.name: element.element_type
        for element in elements
    }

    assert detected_types == {
        "Ambulancia": ProductionElementType.VEHICLE,
        "Bicicleta": ProductionElementType.VEHICLE,
        "Bus": ProductionElementType.VEHICLE,
        "Camioneta": ProductionElementType.VEHICLE,
        "Camión": ProductionElementType.VEHICLE,
        "Furgoneta": ProductionElementType.VEHICLE,
        "Furgón": ProductionElementType.VEHICLE,
        "Jeep": ProductionElementType.VEHICLE,
        "Minibús": ProductionElementType.VEHICLE,
        "Moto": ProductionElementType.VEHICLE,
        "Motocicleta": ProductionElementType.VEHICLE,
        "Patrulla": ProductionElementType.VEHICLE,
        "Suv": ProductionElementType.VEHICLE,
        "Taxi": ProductionElementType.VEHICLE,
        "Tractor": ProductionElementType.VEHICLE,
        "Van": ProductionElementType.VEHICLE,
    }


def test_production_element_analyzer_detects_extended_animals() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="Una vaca permanece junto a varias gallinas.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    assert {
        element.name: element.element_type
        for element in elements
    } == {
        "Vaca": ProductionElementType.ANIMAL,
        "Gallinas": ProductionElementType.ANIMAL,
    }


def test_production_element_analyzer_detects_extended_makeup() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="Lleva una herida y una cicatriz en el rostro.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    assert {
        element.name: element.element_type
        for element in elements
    } == {
        "Herida": ProductionElementType.MAKEUP,
        "Cicatriz": ProductionElementType.MAKEUP,
    }


def test_production_element_analyzer_detects_extended_equipment() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="La cámara apunta al actor con un micrófono.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    assert {
        element.name: element.element_type
        for element in elements
    } == {
        "Cámara": ProductionElementType.EQUIPMENT,
        "Micrófono": ProductionElementType.EQUIPMENT,
    }


def test_production_element_analyzer_detects_extended_special_effects() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="La niebla cubre el muelle y ocurre una detonación.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    assert {
        element.name: element.element_type
        for element in elements
    } == {
        "Detonación": ProductionElementType.SPECIAL_EFFECT,
        "Niebla": ProductionElementType.SPECIAL_EFFECT,
    }


def test_production_element_analyzer_detects_enumerated_unknown_props() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content=(
                "Busca en una vieja caja de herramientas, "
                "un par de guantes, un martillo "
                "y una barreta de fierro."
            ),
        ),
    ]

    analyzer = ProductionElementAnalyzer()
    elements = analyzer.extract(blocks)

    names = {
        element.name
        for element in elements
    }

    assert "Guantes" in names
    assert "Martillo" in names
    assert "Barreta de fierro" in names


def test_production_element_analyzer_detects_unknown_indefinite_props() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content=(
                "El guardia usa unos grilletes parecidos. "
                "Permanece allÃ­ durante unos segundos."
            ),
        ),
    ]

    analyzer = ProductionElementAnalyzer()
    elements = analyzer.extract(blocks)

    assert any(
        element.name == "Grilletes"
        and element.element_type == ProductionElementType.PROP
        for element in elements
    )
    assert "Grilletes parecidos" not in {
        element.name
        for element in elements
    }
    assert "Segundos" not in {
        element.name
        for element in elements
    }


def test_production_element_analyzer_detects_general_effect_candidates() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="Recibe una descarga eléctrica.",
        ),
        Block(
            id="2",
            scene_id="1",
            order=2,
            block_type=BlockType.ACTION,
            content="La ampolleta revienta.",
        ),
        Block(
            id="3",
            scene_id="1",
            order=3,
            block_type=BlockType.ACTION,
            content="Recibe una carta.",
        ),
    ]

    analyzer = ProductionElementAnalyzer()
    elements = analyzer.extract(blocks)

    effect_names = {
        element.name
        for element in elements
        if element.element_type == ProductionElementType.SPECIAL_EFFECT
    }

    assert "Efecto de descarga" in effect_names
    assert "Efecto de estallido" in effect_names
    assert "Efecto de ruptura" not in effect_names