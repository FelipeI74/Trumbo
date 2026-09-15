from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from engine.services.semantic_lexicon import SemanticLexicon


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

    def __call__(self, text: str):
        return SimpleNamespace(
            sentences=[
                SimpleNamespace(
                    words=self.words,
                    tokens=[
                        SimpleNamespace(text=word.text, words=[word])
                        for word in self.words
                    ]
                )
            ]
        )


class FakeWordnet:
    def __init__(self, synsets_by_lemma: dict[str, list[FakeSynset]]) -> None:
        self.synsets_by_lemma = synsets_by_lemma
        self.queries: list[tuple[str, str]] = []

    def synsets(self, lemma: str, pos: str) -> list[FakeSynset]:
        self.queries.append((lemma, pos))
        return self.synsets_by_lemma.get(lemma, [])


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
