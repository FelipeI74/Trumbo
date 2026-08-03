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
