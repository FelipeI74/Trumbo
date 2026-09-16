from dataclasses import dataclass
from types import SimpleNamespace

import pytest
import wn

from engine.services.semantic_lexicon import SemanticLexicon


def test_semantic_lexicon_enables_wn_multithreading() -> None:
    assert wn.config.allow_multithreading is True


@dataclass
class FakeSynset:
    lemmas_value: tuple[str, ...]
    parents: tuple["FakeSynset", ...] = ()

    def lemmas(self) -> list[str]:
        return list(self.lemmas_value)

    def hypernyms(self) -> list["FakeSynset"]:
        return list(self.parents)


@dataclass
class FakeWord:
    text: str
    lemma: str
    upos: str
    id: int
    head: int
    deprel: str


class FakePipeline:
    def __init__(self, words: list[FakeWord]) -> None:
        self.words = words

    def __call__(self, documents):
        return [
            SimpleNamespace(
                sentences=[
                    SimpleNamespace(
                        words=self.words,
                        tokens=[
                            SimpleNamespace(text=word.text, words=[word])
                            for word in self.words
                        ],
                    )
                ]
            )
            for _document in documents
        ]


class FakeWordnet:
    def __init__(self, synsets_by_lemma: dict[str, list[FakeSynset]]) -> None:
        self.synsets_by_lemma = synsets_by_lemma
        self.queries: list[tuple[str, str]] = []

    def synsets(self, lemma: str, pos: str) -> list[FakeSynset]:
        self.queries.append((lemma, pos))
        return self.synsets_by_lemma.get(lemma, [])


def test_semantic_lexicon_caches_wordnet_classification_per_instance() -> None:
    wordnet = FakeWordnet(
        {"perro": [FakeSynset(("perro",), (FakeSynset(("animal",)),))]}
    )
    lexicon = SemanticLexicon(wordnet=wordnet)

    assert lexicon.classify_lemma("perro") == "ANIMAL"
    assert lexicon.classify_lemma("perro") == "ANIMAL"
    assert wordnet.queries == [("perro", "n")]


def test_semantic_lexicon_human_and_animal_conflict_is_unknown() -> None:
    human_root = FakeSynset((), ())
    human_root.id = "omw-es-00007846-n"
    animal_root = FakeSynset(("animal",))
    animal_sense = FakeSynset(("concepto",), (animal_root,))
    human_sense = FakeSynset(("concepto",), (human_root,))
    wordnet = FakeWordnet({"concepto": [animal_sense, human_sense]})

    result = SemanticLexicon(wordnet=wordnet).classify_lemma("concepto")

    assert result == "UNKNOWN"


def test_semantic_lexicon_preserves_human_control_signal() -> None:
    human_root = FakeSynset((), ())
    human_root.id = "omw-es-00007846-n"
    wordnet = FakeWordnet(
        {"concepto": [FakeSynset(("concepto",), (human_root,))]}
    )
    pipeline = FakePipeline(
        [FakeWord("concepto", "concepto", "NOUN", 1, 0, "root")]
    )

    result = SemanticLexicon(pipeline=pipeline, wordnet=wordnet).analyze(
        "concepto"
    )

    assert result[0].family == "UNKNOWN"
    assert result[0].control_families == frozenset({"HUMAN"})


def test_semantic_lexicon_uses_wordnet_sense_order_not_rank_attribute() -> None:
    animal_root = FakeSynset(("animal",), ())
    water_root = FakeSynset(("liquido",), ())
    animal_sense = FakeSynset(("agua",), (animal_root,))
    water_sense = FakeSynset(("agua",), (water_root,))
    wordnet = FakeWordnet({"agua": [water_sense, animal_sense]})

    assert SemanticLexicon(wordnet=wordnet).classify_lemma("agua") == "UNKNOWN"


@pytest.mark.parametrize(
    ("text", "lemma", "concept", "conflict", "expected_family"),
    [
        ("camionetas", "camioneta", "vehículo", False, "VEHICLE"),
        ("perros", "perro", "animal", False, "ANIMAL"),
        ("chaquetas", "chaqueta", "prenda", False, "WARDROBE"),
        ("martillos", "martillo", "herramienta", False, "PROP"),
        ("sillas", "silla", "mueble", False, "FURNITURE"),
        ("segundos", "segundo", "unidad de tiempo", False, "IGNORE"),
        ("patio", "patio", None, False, "UNKNOWN"),
        ("objeto", "objeto", "vehículo", True, "UNKNOWN"),
    ],
)
def test_semantic_lexicon_filters_nouns_and_classifies_lemmas(
    text: str,
    lemma: str,
    concept: str | None,
    conflict: bool,
    expected_family: str,
) -> None:
    parent = (
        FakeSynset((concept,), ())
        if concept is not None
        else None
    )
    if conflict:
        parent = FakeSynset(
            ("vehículo",),
            (FakeSynset(("animal",), ()),),
        )
    synsets = {lemma: [FakeSynset((lemma,), (parent,))]} if parent else {}
    wordnet = FakeWordnet(synsets)
    pipeline = FakePipeline(
        [
            FakeWord("toma", "tomar", "VERB", 1, 0, "root"),
            FakeWord(text, lemma, "NOUN", 2, 0, "root"),
            FakeWord("bonito", "bonito", "ADJ", 3, 0, "root"),
        ]
    )

    result = SemanticLexicon(pipeline=pipeline, wordnet=wordnet).analyze(
        "línea ACTION"
    )

    assert [(candidate.text, candidate.lemma, candidate.family) for candidate in result] == [
        (text, lemma, expected_family)
    ]
    assert wordnet.queries == [(lemma, "n")]
