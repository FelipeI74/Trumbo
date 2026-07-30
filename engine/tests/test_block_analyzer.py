"""
Basic test for BlockAnalyzer
"""

from core.scene import Scene
from services.analyzers.block_analyzer import BlockAnalyzer


def test_block_analyzer():

    scene = Scene(
        id="1",
        number="1",
        interior_exterior="INT",
        general_location="CASA",
        specific_location="COCINA",
        time_of_day="NOCHE",
        content="""
Juan entra lentamente.

JUAN

Hola.

MARÍA

¿Qué haces aquí?
"""
    )

    analyzer = BlockAnalyzer()

    blocks = analyzer.analyze(scene)

    print()

    for block in blocks:
        print(block.block_type, "->", block.content)
