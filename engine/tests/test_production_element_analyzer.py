from types import SimpleNamespace

from engine.core.block import Block
from engine.core.types.block_type import BlockType
from engine.core.types.production_element_type import ProductionElementType
from engine.services.analyzers.production_element_analyzer import (
    ProductionElementAnalyzer,
)


def test_production_element_analyzer_batches_semantic_action_blocks() -> None:
    class BatchSemanticLexicon:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def analyze_many(self, texts: list[str]):
            self.calls.append(texts)
            return [
                [SimpleNamespace(text="vehiculo-nuevo", family="VEHICLE")],
                [SimpleNamespace(text="animal-nuevo", family="ANIMAL")],
            ]

    semantic_lexicon = BatchSemanticLexicon()
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="Primera acción.",
        ),
        Block(
            id="2",
            scene_id="1",
            order=2,
            block_type=BlockType.DIALOGUE,
            content="No se analiza.",
        ),
        Block(
            id="3",
            scene_id="1",
            order=3,
            block_type=BlockType.ACTION,
            content="Segunda acción.",
        ),
    ]

    elements = ProductionElementAnalyzer(semantic_lexicon).extract(blocks)

    assert semantic_lexicon.calls == [["Primera acción.", "Segunda acción."]]
    assert {
        element.name: element.element_type
        for element in elements
    } == {
        "Animal-nuevo": ProductionElementType.ANIMAL,
        "Vehiculo-nuevo": ProductionElementType.VEHICLE,
    }


def test_production_element_analyzer_vetoes_human_indefinite_prop() -> None:
    class HumanSemanticLexicon:
        def analyze_many(self, texts: list[str]):
            return [
                [
                    SimpleNamespace(
                        text="personas",
                        family="UNKNOWN",
                        control_families=frozenset({"HUMAN"}),
                    )
                ]
            ]

    elements = ProductionElementAnalyzer(HumanSemanticLexicon()).extract(
        [
            Block(
                id="1",
                scene_id="1",
                order=1,
                block_type=BlockType.ACTION,
                content="Unas personas caminan.",
            )
        ]
    )

    assert elements == []


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


def test_production_element_analyzer_ignores_verbal_van_but_keeps_vehicle_van() -> None:
    verbal_blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="Los coágulos de leche se van desarmando.",
        )
    ]
    verbal_elements = ProductionElementAnalyzer().extract(verbal_blocks)
    assert all(element.name != "Van" for element in verbal_elements)

    vehicle_blocks = [
        Block(
            id="2",
            scene_id="1",
            order=2,
            block_type=BlockType.ACTION,
            content="La van gris espera junto a la puerta.",
        )
    ]
    vehicle_elements = ProductionElementAnalyzer().extract(vehicle_blocks)
    vehicle_detected = {
        element.name: element.element_type
        for element in vehicle_elements
    }

    assert vehicle_detected["Van"] == ProductionElementType.VEHICLE


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


def test_production_element_analyzer_detects_bird_window_impact() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="Un zorzal golpea contra su ventana.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    assert any(
        element.name == "Impacto contra ventana"
        and element.element_type == ProductionElementType.SPECIAL_EFFECT
        for element in elements
    )


def test_production_element_analyzer_ignores_bottle_fall_as_stunt() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="La botella cae.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    assert not any(
        element.name == "Caída"
        and element.element_type == ProductionElementType.STUNT
        for element in elements
    )


def test_production_element_analyzer_detects_coordinated_fall_as_stunt() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="Se tropieza con la botella y cae sobre el escritorio.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    assert any(
        element.name == "Caída"
        and element.element_type == ProductionElementType.STUNT
        for element in elements
    )


def test_production_element_analyzer_detects_perro_as_animal() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="El perro corre por el patio.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    assert any(
        element.name == "Perro"
        and element.element_type == ProductionElementType.ANIMAL
        for element in elements
    )


def test_production_element_analyzer_detects_literal_stunts() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content=(
                "La caída ocurre tras el golpe durante la pelea. "
                "El atropello causa un arrastre y un lanzamiento."
            ),
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    assert {
        element.name
        for element in elements
        if element.element_type == ProductionElementType.STUNT
    } == {
        "Arrastre",
        "Atropello",
        "Caída",
        "Golpe",
        "Lanzamiento",
        "Pelea",
    }


def test_production_element_analyzer_detects_semantic_stunts() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="El personaje cae sobre el pavimento.",
        ),
        Block(
            id="2",
            scene_id="1",
            order=2,
            block_type=BlockType.ACTION,
            content="Sale despedido contra la pared.",
        ),
        Block(
            id="3",
            scene_id="1",
            order=3,
            block_type=BlockType.ACTION,
            content="Es arrojado al suelo.",
        ),
        Block(
            id="4",
            scene_id="1",
            order=4,
            block_type=BlockType.ACTION,
            content="Lo arrastran por el pasillo.",
        ),
        Block(
            id="5",
            scene_id="1",
            order=5,
            block_type=BlockType.ACTION,
            content="Es atropellado frente al edificio.",
        ),
        Block(
            id="6",
            scene_id="1",
            order=6,
            block_type=BlockType.ACTION,
            content="Se golpea contra el muro.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    assert {
        element.name
        for element in elements
        if element.element_type == ProductionElementType.STUNT
    } == {
        "Arrastre",
        "Atropello",
        "Caída",
        "Golpe",
        "Persona arrojada",
        "Persona despedida",
    }


def test_production_element_analyzer_detects_semantic_action_cases() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="La herida del rostro comienza a sangrar.",
        ),
        Block(
            id="2",
            scene_id="1",
            order=2,
            block_type=BlockType.ACTION,
            content="El cristal se rompe con un estruendo.",
        ),
        Block(
            id="3",
            scene_id="1",
            order=3,
            block_type=BlockType.ACTION,
            content="Una explosión sacude el almacén.",
        ),
        Block(
            id="4",
            scene_id="1",
            order=4,
            block_type=BlockType.ACTION,
            content="Una descarga eléctrica atraviesa el aire.",
        ),
        Block(
            id="5",
            scene_id="1",
            order=5,
            block_type=BlockType.ACTION,
            content="El humo cubre la sala.",
        ),
        Block(
            id="6",
            scene_id="1",
            order=6,
            block_type=BlockType.ACTION,
            content="El fuego crece en la habitación.",
        ),
        Block(
            id="7",
            scene_id="1",
            order=7,
            block_type=BlockType.ACTION,
            content="El arnés sostiene al técnico.",
        ),
        Block(
            id="8",
            scene_id="1",
            order=8,
            block_type=BlockType.ACTION,
            content="Un dron sobrevuela el patio.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    detected_types = {
        element.name: element.element_type
        for element in elements
    }

    assert detected_types == {
        "Arnés": ProductionElementType.EQUIPMENT,
        "Dron": ProductionElementType.EQUIPMENT,
        "Efecto de descarga": ProductionElementType.SPECIAL_EFFECT,
        "Efecto de ruptura": ProductionElementType.SPECIAL_EFFECT,
        "Explosión": ProductionElementType.SPECIAL_EFFECT,
        "Fuego": ProductionElementType.SPECIAL_EFFECT,
        "Herida": ProductionElementType.MAKEUP,
        "Humo": ProductionElementType.SPECIAL_EFFECT,
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


def test_production_element_analyzer_detects_dead_tree_as_set_dressing() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="Andrés se detiene frente a un árbol muerto.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

    assert {
        (element.name, element.element_type)
        for element in elements
    } == {
        ("Árbol muerto", ProductionElementType.SET_DRESSING),
    }


def test_production_element_analyzer_ignores_temporal_seconds_as_prop() -> None:
    blocks = [
        Block(
            id="1",
            scene_id="1",
            order=1,
            block_type=BlockType.ACTION,
            content="Andrés se queda mirando el árbol unos segundos.",
        ),
    ]

    elements = ProductionElementAnalyzer().extract(blocks)

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