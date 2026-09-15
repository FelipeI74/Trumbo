"""Experimento aislado de contexto sintactico con Stanza."""

from __future__ import annotations

import stanza


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


def describe_head(words: list[stanza.models.common.doc.Word], head_id: int) -> str:
    if head_id == 0:
        return "ROOT | ROOT | ROOT"
    head = words[head_id - 1]
    return f"{head.text} | {head.lemma} | {head.upos}"


def describe_modifiers(
    words: list[stanza.models.common.doc.Word], noun_id: int
) -> str:
    modifiers = [
        f"{word.text} | {word.lemma} | {word.upos}"
        for word in words
        if word.head == noun_id
    ]
    return ", ".join(modifiers) if modifiers else "ninguno"


def main() -> None:
    pipeline = stanza.Pipeline(
        lang="es",
        processors="tokenize,pos,lemma,depparse",
        verbose=False,
    )

    for phrase in PHRASES:
        print(f"\n{phrase}")
        document = pipeline(phrase)
        for sentence in document.sentences:
            words = sentence.words
            for word in words:
                if word.upos != "NOUN":
                    continue
                head = describe_head(words, word.head)
                modifiers = describe_modifiers(words, word.id)
                print(
                    f"{word.text} | {word.lemma} | {word.deprel} | "
                    f"head: {head} | modificadores: {modifiers}"
                )


if __name__ == "__main__":
    main()
