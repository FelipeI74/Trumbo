"""Experimento aislado de tokenizacion, POS y lematizacion con Stanza."""

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


def main() -> None:
    pipeline = stanza.Pipeline(
        lang="es",
        processors="tokenize,pos,lemma",
        verbose=False,
    )

    for phrase in PHRASES:
        print(f"\n{phrase}")
        document = pipeline(phrase)
        for sentence in document.sentences:
            for token in sentence.tokens:
                word = token.words[0]
                print(f"{token.text} | {word.lemma} | {word.upos}")


if __name__ == "__main__":
    main()
