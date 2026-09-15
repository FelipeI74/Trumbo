"""Experimento aislado de Stanza y MCR para clasificacion semantica."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

import stanza
import wn


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


def family_for(synset: wn.Synset) -> set[str]:
    families: set[str] = set()
    for lemma in synset.lemmas():
        concept = normalize(lemma)
        for family_name, classification in FAMILIES.items():
            if concept == family_name or re.search(
                rf"(?:^| ){re.escape(family_name)}(?:$| )", concept
            ):
                families.add(classification)
    return families


def hypernym_paths(synset: wn.Synset, max_levels: int = 8):
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


def classify_lemma(wordnet: wn.Wordnet, lemma: str) -> str:
    synsets = wordnet.synsets(normalize(lemma), pos="n")
    family_counts: Counter[str] = Counter()
    sense_conflict = False

    for synset in synsets:
        sense_families: set[str] = set()
        for path in hypernym_paths(synset):
            for node in path:
                sense_families.update(family_for(node))
        if len(sense_families) > 1:
            sense_conflict = True
        for family in sense_families:
            family_counts[family] += 1

    if not family_counts:
        return "UNKNOWN"

    highest = max(family_counts.values())
    leaders = [family for family, count in family_counts.items() if count == highest]
    if sense_conflict or len(leaders) != 1:
        return "AMBIGUOUS"
    return f"PROBABLE {leaders[0]}"


def main() -> None:
    pipeline = stanza.Pipeline(
        lang="es",
        processors="tokenize,pos,lemma",
        verbose=False,
    )
    wordnet = wn.Wordnet("omw-es:2.0")

    for phrase in PHRASES:
        print(phrase)
        document = pipeline(phrase)
        for sentence in document.sentences:
            for token in sentence.tokens:
                word = token.words[0]
                if word.upos == "NOUN":
                    print(f"{token.text} | {classify_lemma(wordnet, word.lemma)}")


if __name__ == "__main__":
    main()
