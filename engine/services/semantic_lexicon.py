"""Lexical-semantic service based on Stanza and the Spanish MCR lexicon."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from threading import Lock, RLock, local
from typing import Any

import stanza
import wn


wn.config.allow_multithreading = True

_PIPELINE: Any | None = None
_PIPELINE_INIT_LOCK = Lock()
_PIPELINE_CALL_LOCK = RLock()
_WORDNET_LOCAL = local()
HUMAN_ROOT_SYNSET_IDS = {
    "omw-es-00007846-n",
    "omw-es-02472293-n",
}


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
    control_families: frozenset[str] = field(default_factory=frozenset)


class SemanticLexicon:
    """Find semantic families for nominal candidates in an ACTION line."""

    def __init__(
        self,
        pipeline: Any | None = None,
        wordnet: wn.Wordnet | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.wordnet = wordnet
        self._injected_classification_cache: dict[
            str, tuple[str, frozenset[str]]
        ] | None = (
            {} if wordnet is not None else None
        )

    def analyze(self, text: str) -> list[LexicalCandidate]:
        """Return semantic candidates for the supplied ACTION line."""
        return self.analyze_many([text])[0]

    def analyze_many(
        self,
        texts: list[str],
    ) -> list[list[LexicalCandidate]]:
        """Return semantic candidates while processing texts in one batch."""
        pipeline = (
            self.pipeline
            if self.pipeline is not None
            else self._get_shared_pipeline()
        )
        documents = [stanza.Document([], text=text) for text in texts]
        with _PIPELINE_CALL_LOCK:
            processed_documents = pipeline(documents)

        results: list[list[LexicalCandidate]] = []
        for document in processed_documents:
            candidates: list[LexicalCandidate] = []
            for sentence in document.sentences:
                words = sentence.words
                for token in sentence.tokens:
                    word = token.words[0]
                    if word.upos != "NOUN" or self._is_lexicalized_case_part(
                        word, words
                    ):
                        continue
                    family, control_families = self._classify_lemma_with_controls(
                        word.lemma
                    )
                    candidates.append(
                        LexicalCandidate(
                            text=token.text,
                            lemma=word.lemma,
                            family=family,
                            control_families=control_families,
                        )
                    )
            results.append(candidates)
        return results

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
        family, _ = self._classify_lemma_with_controls(lemma)
        return family

    def is_animate_lemma(self, lemma: str) -> bool:
        family, control_families = self._classify_lemma_with_controls(lemma)
        return family in {"ANIMAL", "HUMAN"} or "HUMAN" in control_families

    def _classify_lemma_with_controls(
        self,
        lemma: str,
    ) -> tuple[str, frozenset[str]]:
        normalized_lemma = self.normalize(lemma)
        cache = self._get_classification_cache()
        if normalized_lemma in cache:
            return cache[normalized_lemma]

        with _PIPELINE_CALL_LOCK:
            wordnet = (
                self.wordnet
                if self.wordnet is not None
                else self._get_thread_wordnet()
            )
            synsets = wordnet.synsets(normalized_lemma, pos="n")

            if not synsets:
                cache[normalized_lemma] = ("UNKNOWN", frozenset())
                return cache[normalized_lemma]

            sense_candidates: list[tuple[int, set[str]]] = []
            for index, synset in enumerate(synsets):
                families = self._families_for_synset(synset)
                sense_candidates.append((index, families))

        if not sense_candidates:
            cache[normalized_lemma] = ("UNKNOWN", frozenset())
            return cache[normalized_lemma]

        top_families = {
            family
            for _, families in sense_candidates
            for family in families
        }
        if not sense_candidates[0][1]:
            cache[normalized_lemma] = ("UNKNOWN", frozenset())
            return cache[normalized_lemma]
        control_families = frozenset(
            family for family in top_families if family == "HUMAN"
        )

        if "HUMAN" in top_families:
            cache[normalized_lemma] = ("UNKNOWN", control_families)
            return cache[normalized_lemma]

        if len(top_families) != 1:
            cache[normalized_lemma] = ("UNKNOWN", control_families)
            return cache[normalized_lemma]

        family = next(iter(top_families))
        cache[normalized_lemma] = (family, control_families)
        return cache[normalized_lemma]

    def _families_for_synset(self, synset: wn.Synset) -> set[str]:
        sense_families: set[str] = set()
        for path in self.hypernym_paths(synset):
            if any(
                getattr(node, "id", None) in HUMAN_ROOT_SYNSET_IDS
                for node in path
            ):
                sense_families.add("HUMAN")
            for node in path:
                sense_families.update(self.families_for(node))
        return sense_families

    @staticmethod
    def _synset_sort_key(synset: wn.Synset) -> int:
        raw_rank = getattr(synset, "rank", None)
        if raw_rank is None:
            return 10**9
        try:
            return int(raw_rank)
        except (TypeError, ValueError):
            return 10**9

    @staticmethod
    def _get_shared_pipeline() -> Any:
        global _PIPELINE
        if _PIPELINE is None:
            with _PIPELINE_INIT_LOCK:
                if _PIPELINE is None:
                    _PIPELINE = stanza.Pipeline(
                        lang="es",
                        processors="tokenize,pos,lemma,depparse",
                        verbose=False,
                    )
        return _PIPELINE

    @staticmethod
    def _get_thread_wordnet() -> wn.Wordnet:
        wordnet = getattr(_WORDNET_LOCAL, "wordnet", None)
        if wordnet is None:
            wordnet = wn.Wordnet("omw-es:2.0")
            _WORDNET_LOCAL.wordnet = wordnet
        return wordnet

    def _get_classification_cache(
        self,
    ) -> dict[str, tuple[str, frozenset[str]]]:
        if self._injected_classification_cache is not None:
            return self._injected_classification_cache

        cache = getattr(_WORDNET_LOCAL, "classification_cache", None)
        if cache is None:
            cache = {}
            _WORDNET_LOCAL.classification_cache = cache
        return cache

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
