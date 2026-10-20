from __future__ import annotations

import re
from uuid import uuid4

import stanza

from engine.core.block import Block
from engine.core.scene import Scene
from engine.core.types.block_type import BlockType
from engine.core.types.production_element_type import ProductionElementType
from engine.services.analyzers.character_extractor import CharacterExtractor
from engine.services.analyzers.event_extractor import EventExtractor
from engine.services.analyzers.production_element_analyzer import ProductionElementAnalyzer
from engine.services.parsers.scene_parser import SceneParser
from engine.services.semantic_lexicon import SemanticLexicon


def analyze_scene_with_engine(
    scene_id: int,
    heading: str,
    body: str,
    semantic_lines: list[dict[str, str]] | None = None,
    known_characters: list[str] | None = None,
) -> dict:
    """
    Analyze a screenplay scene using the Engine parser and return the
    frontend-compatible shape expected by the existing UI.
    """

    scene = Scene(
        id=str(scene_id),
        number="1",
        interior_exterior="INT",
        general_location="",
        specific_location=None,
        time_of_day="",
        content=f"{heading}\n{body}".strip(),
    )

    if semantic_lines:
        blocks = [
            Block(
                id=str(uuid4()),
                scene_id=str(scene_id),
                order=index,
                block_type=BlockType(line["type"]),
                content=line["text"],
            )
            for index, line in enumerate(semantic_lines, start=1)
            if line.get("type") in {
                "heading",
                "action",
                "character",
                "dialogue",
                "parenthetical",
                "transition",
            }
            and isinstance(line.get("text"), str)
        ]
    else:
        parser = SceneParser()
        parsed_scene = parser.parse(scene)
        blocks = parsed_scene.blocks

    event_extractor = EventExtractor()
    events = event_extractor.extract(blocks)
    event_characters = CharacterExtractor().extract(events)

    production_element_analyzer = ProductionElementAnalyzer()
    production_elements = production_element_analyzer.extract(
        blocks,
        known_characters=known_characters or [],
    )

    counts = {
        "heading": 0,
        "action": 0,
        "character": 0,
        "dialogue": 0,
        "parenthetical": 0,
        "transition": 0,
    }

    characters: list[str] = []
    character_keys: set[str] = set()
    elements: list[dict] = []

    for block in blocks:
        block_type = block.block_type
        block_type_value = block_type.value

        if block_type_value in counts:
            counts[block_type_value] += 1

        if block_type == BlockType.CHARACTER:
            name = block.content.strip()
            
            # --- NUEVO: Limpiar (VO), (OS), (CONT'D), etc. ---
            # Esto hace que "APARATO(VO)" se convierta en "APARATO" antes de guardarse.
            name = re.sub(r"\s*\(.*?\)", "", name).strip()
            # --------------------------------------------------
            
            if re.fullmatch(r"\d+[A-Z]?\.?", name):
                continue
            key = name.casefold()
            if key not in character_keys:
                characters.append(name)
                character_keys.add(key)

        elements.append(
            {
                "line_number": len(elements) + 1,
                "type": block_type_value,
                "text": block.content,
                "confidence": 1.0,
            }
        )

    if event_characters:
        pipeline = SemanticLexicon._get_shared_pipeline()
        event_documents = pipeline(
            [
                stanza.Document([], text=event.summary)
                for event in events
            ]
        )
        events_by_subject: dict[str, list[tuple[object, object]]] = {}
        for event, document in zip(events, event_documents):
            if event.subject:
                events_by_subject.setdefault(
                    event.subject.strip().casefold(),
                    [],
                ).append((event, document))

        # Pre-calculamos los nombres conocidos en minúsculas para comparación rápida
        known_keys = {c.casefold() for c in (known_characters or [])}

        for statistic in event_characters:
            name = statistic.character.name.strip()
            key = name.casefold()
            if key in character_keys:
                continue

            subject_tokens = name.split()
            is_proper_name = False
            for _, document in events_by_subject.get(key, []):
                words = [
                    word
                    for sentence in document.sentences
                    for word in sentence.words
                ]
                for start in range(len(words) - len(subject_tokens) + 1):
                    span = words[start : start + len(subject_tokens)]
                    if (
                        [word.text.casefold() for word in span]
                        == [token.casefold() for token in subject_tokens]
                        and all(word.upos == "PROPN" for word in span)
                    ):
                        is_proper_name = True
                        break
                if is_proper_name:
                    break

            if is_proper_name:
                # CANDADO ANTI-FANTASMAS: Si no está en la lista oficial del proyecto, se ignora
                if known_keys and key not in known_keys:
                    continue
                characters.append(name)
                character_keys.add(key)

    character_elements = [
        element
        for element in production_elements
        if element.element_type == ProductionElementType.CHARACTER
    ]
    production_elements = [
        element
        for element in production_elements
        if element.element_type != ProductionElementType.CHARACTER
    ]

    for element in character_elements:
        name = element.name.strip()
        key = name.casefold()
        if name and key not in character_keys:
            characters.append(name)
            character_keys.add(key)

    return {
        "counts": counts,
        "characters": characters,
        "elements": elements,
        "events": [
            {
                "id": event.id,
                "scene_id": event.scene_id,
                "order": event.order,
                "title": event.title,
                "summary": event.summary,
                "subject": event.subject,
                "verb": event.verb,
                "object": event.object,
            }
            for event in events
        ],
        "production_elements": [
            {
                "id": element.id,
                "name": element.name,
                "element_type": element.element_type.value,
            }
            for element in production_elements
        ],
    }
