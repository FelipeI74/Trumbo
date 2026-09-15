"""Lexical-semantic service based on Stanza and the Spanish MCR lexicon."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any

import stanza
import wn


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


@dataclass(frozen=True)
class LexicalCandidate:
    text: str
    lemma: str
    family: str


class SemanticLexicon:
    """Find semantic families for nominal candidates in an ACTION line."""

    def __init__(
        self,
        pipeline: Any | None = None,
        wordnet: wn.Wordnet | None = None,
    ) -> None:
        self.pipeline = pipeline or stanza.Pipeline(
            lang="es",
            processors="tokenize,pos,lemma,depparse",
            verbose=False,
        )
        self.wordnet = wordnet or wn.Wordnet("omw-es:2.0")

    def analyze(self, text: str) -> list[LexicalCandidate]:
        """Return semantic candidates for the supplied ACTION line."""
        document = self.pipeline(text)
        candidates: list[LexicalCandidate] = []
        for sentence in document.sentences:
            words = sentence.words
            for token in sentence.tokens:
                word = token.words[0]
                if word.upos != "NOUN" or self._is_lexicalized_case_part(
                    word, words
                ):
                    continue
                candidates.append(
                    LexicalCandidate(
                        text=token.text,
                        lemma=word.lemma,
                        family=self.classify_lemma(word.lemma),
                    )
                )
        return candidates

    @staticmethod
    def _is_lexicalized_case_part(word: Any, words: list[Any]) -> bool:
        word_id = getattr(word, "id", None)
        if word_id is None:
            return False

        if word.deprel == "case":
            return any(
                dependent.head == word_id and dependent.deprel == "fixed"
                for dependent in words
            )

        return any(
            case_word.head == word_id
            and case_word.deprel == "case"
            and any(
                dependent.head == case_word.id and dependent.deprel == "fixed"
                for dependent in words
            )
            for case_word in words
        )

    def classify_lemma(self, lemma: str) -> str:
        synsets = self.wordnet.synsets(self.normalize(lemma), pos="n")
        family_counts: Counter[str] = Counter()
        sense_conflict = False

        for synset in synsets:
            sense_families: set[str] = set()
            for path in self.hypernym_paths(synset):
                for node in path:
                    sense_families.update(self.families_for(node))
            if len(sense_families) > 1:
                sense_conflict = True
            for family in sense_families:
                family_counts[family] += 1

        if not family_counts:
            return "UNKNOWN"

        highest = max(family_counts.values())
        leaders = [
            family for family, count in family_counts.items() if count == highest
        ]
        if sense_conflict or len(leaders) != 1:
            return "UNKNOWN"
        return leaders[0]

    @staticmethod
    def normalize(text: str) -> str:
        decomposed = unicodedata.normalize("NFD", text.casefold())
        without_marks = "".join(
            char for char in decomposed if unicodedata.category(char) != "Mn"
        )
        return " ".join(without_marks.split())

    @classmethod
    def families_for(cls, synset: wn.Synset) -> set[str]:
        families: set[str] = set()
        for lemma in synset.lemmas():
            concept = cls.normalize(lemma)
            for family_name, classification in FAMILIES.items():
                if concept == family_name or re.search(
                    rf"(?:^| ){re.escape(family_name)}(?:$| )", concept
                ):
                    families.add(classification)
        return families

    @staticmethod
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
