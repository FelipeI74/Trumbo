"""Experimento aislado de clasificacion conceptual con wn y omw-es:2.0."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

import wn


WORDS = (
    "martillo",
    "camioneta",
    "perro",
    "chaqueta",
    "segundo",
    "árbol",
    "silla",
    "mesa",
    "pistola",
    "teléfono",
    "bicicleta",
    "caballo",
    "vestido",
    "sombrero",
    "cuchillo",
    "botella",
    "reloj",
    "computador",
    "cámara",
    "cortina",
)

PHRASES = (
    "Andrés toma el martillo",
    "El perro corre por el patio",
    "Es un perro miserable",
    "Espera unos segundos",
    "Se sienta en la silla",
    "Deja la chaqueta sobre la mesa",
    "Sube a la camioneta",
    "La cámara está sobre la mesa",
    "Entra en la cámara frigorífica",
)

FAMILIES = {
    "vehiculo": "VEHICLE",
    "animal": "ANIMAL",
    "prenda de vestir": "WARDROBE",
    "prenda": "WARDROBE",
    "ropa": "WARDROBE",
    "vestuario": "WARDROBE",
    "herramienta": "PROP",
    "mueble": "FURNITURE",
    "mobiliario": "FURNITURE",
    "unidad de tiempo": "IGNORE",
    "instante": "IGNORE",
    "momento": "IGNORE",
}

FAMILY_ALIASES = {
    "vehiculo": "VEHICLE",
    "vehiculos": "VEHICLE",
    "animal": "ANIMAL",
    "animales": "ANIMAL",
    "prenda de vestir": "WARDROBE",
    "prendas de vestir": "WARDROBE",
    "prenda": "WARDROBE",
    "prendas": "WARDROBE",
    "ropa": "WARDROBE",
    "vestuario": "WARDROBE",
    "herramienta": "PROP",
    "herramientas": "PROP",
    "mueble": "FURNITURE",
    "muebles": "FURNITURE",
    "mobiliario": "FURNITURE",
    "unidad de tiempo": "IGNORE",
    "unidades de tiempo": "IGNORE",
    "instante": "IGNORE",
    "instantes": "IGNORE",
    "momento": "IGNORE",
    "momentos": "IGNORE",
}


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return " ".join(without_marks.split())


def concepts(synset: wn.Synset) -> tuple[str, ...]:
    return tuple(sorted({normalize(lemma) for lemma in synset.lemmas()}))


def family_for(concept_names: tuple[str, ...]) -> str | None:
    for concept_name in concept_names:
        if concept_name in FAMILY_ALIASES:
            return FAMILY_ALIASES[concept_name]
        for family_name, classification in FAMILIES.items():
            if re.search(rf"(?:^| )({re.escape(family_name)})(?:$| )", concept_name):
                return classification
    return None


def hypernym_paths(synset: wn.Synset, max_levels: int = 8):
    """Yield each conceptual chain, including the queried synset."""
    path = [synset]

    def visit(current: wn.Synset, levels: int):
        yield tuple(path)
        if levels == max_levels:
            return
        for parent in current.hypernyms():
            if parent in path:
                continue
            path.append(parent)
            yield from visit(parent, levels + 1)
            path.pop()

    yield from visit(synset, 0)


def inspect_word(
    wordnet: wn.Wordnet, word: str
) -> tuple[str, str | None, Counter[str], tuple[str, ...]]:
    synsets = wordnet.synsets(word, pos="n")
    family_counts: Counter[str] = Counter()
    evidence: list[str] = []
    sense_conflict = False

    for synset in synsets:
        sense_families: set[str] = set()
        for path in hypernym_paths(synset):
            chain = tuple(", ".join(concepts(node)) for node in path)
            path_families = {
                classification
                for node in path
                if (classification := family_for(concepts(node))) is not None
            }
            sense_families.update(path_families)
            if path_families:
                evidence.append(" > ".join(chain))

        if len(sense_families) > 1:
            sense_conflict = True
        for classification in sense_families:
            family_counts[classification] += 1

    if not family_counts:
        return "UNKNOWN", None, family_counts, ("sin familia conocida",)

    highest_count = max(family_counts.values())
    leaders = [
        classification
        for classification, count in family_counts.items()
        if count == highest_count
    ]
    if sense_conflict or len(leaders) != 1:
        return "AMBIGUOUS", None, family_counts, tuple(dict.fromkeys(evidence))

    return "PROBABLE", leaders[0], family_counts, tuple(dict.fromkeys(evidence))


def noun_synsets(
    wordnet: wn.Wordnet, token: str
) -> tuple[str, list[wn.Synset]] | None:
    normalized = normalize(token)
    forms = [normalized]
    if normalized.endswith("s") and len(normalized) > 4:
        forms.append(normalized[:-1])
    for form in dict.fromkeys(forms):
        synsets = wordnet.synsets(form, pos="n")
        if synsets:
            return form, synsets
    return None


def phrase_nouns(
    wordnet: wn.Wordnet, phrase: str
) -> tuple[tuple[str, str], ...]:
    tokens = re.findall(r"[^\W\d_]+", phrase, flags=re.UNICODE)
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for token in tokens:
        normalized = normalize(token)
        if normalized in seen:
            continue
        result = noun_synsets(wordnet, token)
        if result is not None:
            candidates.append((token, result[0]))
            seen.add(normalized)
    return tuple(candidates)


def inspect_phrase(wordnet: wn.Wordnet, phrase: str) -> None:
    print(f"\nFRASE: {phrase}")
    candidates = phrase_nouns(wordnet, phrase)
    if not candidates:
        print("  sustantivos candidatos: ninguno")
        return

    print("  sustantivos candidatos: " + ", ".join(surface for surface, _ in candidates))
    for candidate, lookup_form in candidates:
        synsets = wordnet.synsets(lookup_form, pos="n")
        families: set[str] = set()
        sense_lines: list[str] = []

        for synset in synsets:
            sense_families: set[str] = set()
            for path in hypernym_paths(synset):
                sense_families.update(
                    classification
                    for node in path
                    if (classification := family_for(concepts(node))) is not None
                )
            families.update(sense_families)
            labels = ", ".join(synset.lemmas())
            sense_lines.append(f"{synset.id} [{labels}]")

        family_text = ", ".join(sorted(families)) or "ninguna"
        print(f"  {candidate}: familias semánticas: {family_text}")
        print("    sentidos posibles de MCR: " + " || ".join(sense_lines))


def main() -> None:
    wordnet = wn.Wordnet("omw-es:2.0")
    for word in WORDS:
        status, family, family_counts, chains = inspect_word(wordnet, word)
        counts = ", ".join(
            f"{classification}={count}"
            for classification, count in sorted(family_counts.items())
        ) or "ninguna"
        decision = f"{status} {family}" if family is not None else status
        print(f"{word}: {decision} | familias: {counts}")
        print("  cadenas: " + " || ".join(chains))

    print("\n=== PRUEBA EXPERIMENTAL CON FRASES ===")
    for phrase in PHRASES:
        inspect_phrase(wordnet, phrase)


if __name__ == "__main__":
    main()
