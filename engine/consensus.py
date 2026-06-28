"""Sharp-Consensus: mehrere Sharp-Bücher zu *einer* fairen Linie verrechnen.

Eine einzelne Pinnacle-Quote ist scharf, aber verrauscht (Latenz, Einzel-
Fehlbepreisung). Werden mehrere Sharp-Bücher je Ausgang de-vigged und
gewichtet gemittelt, sinkt die Varianz der fairen Wahrscheinlichkeit — das
reduziert Fehlsignale und macht den gemessenen Edge verlässlicher.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from engine.novig import devig

# Ein Sharp-Buch für einen Markt: Buchname + vollständige Quoten je Ausgang.
BookQuotes = tuple[str, Mapping[str, Decimal]]


@dataclass(frozen=True)
class FairLine:
    """Konsolidierte faire Linie eines Marktes über mehrere Sharp-Bücher.

    Attributes:
        probabilities: gewichtet gemittelte faire Wahrscheinlichkeit je Ausgang
            (Summe = 1).
        method: verwendete De-Vig-Methode.
        n_books: Anzahl eingeflossener Sharp-Bücher.
        books: Namen der eingeflossenen Bücher.
    """

    probabilities: dict[str, float]
    method: str
    n_books: int
    books: tuple[str, ...]

    def p(self, selection_key: str) -> float:
        """Faire Wahrscheinlichkeit eines Ausgangs."""
        return self.probabilities[selection_key]

    def fair_odds(self, selection_key: str) -> float:
        """Faire Dezimalquote eines Ausgangs."""
        return 1.0 / self.probabilities[selection_key]


def fair_line_from_books(
    books: Sequence[BookQuotes],
    *,
    method: str = "shin",
    weights: Mapping[str, float] | None = None,
    default_weight: float = 0.4,
) -> FairLine:
    """De-vig jedes Sharp-Buch und mittele die fairen Wahrscheinlichkeiten gewichtet.

    Args:
        books: Liste ``(bookmaker, {selection_key: Quote})``. Alle Bücher müssen
            denselben Markt (gleiche selection_keys) abdecken.
        method: De-Vig-Methode (Default ``shin``).
        weights: Gewicht je Buch (case-insensitiv). Fehlt ein Buch, gilt
            ``default_weight``.
        default_weight: Fallback-Gewicht für unbekannte Bücher.

    Raises:
        ValueError: keine Bücher, oder Bücher decken unterschiedliche Ausgänge ab.
    """
    if not books:
        raise ValueError("Sharp-Consensus braucht mindestens ein Buch.")

    weights = {k.lower(): v for k, v in (weights or {}).items()}
    selection_keys = set(books[0][1].keys())

    accum: dict[str, float] = dict.fromkeys(selection_keys, 0.0)
    total_weight = 0.0
    used_books: list[str] = []

    for bookmaker, odds in books:
        if set(odds.keys()) != selection_keys:
            raise ValueError(
                f"Buch '{bookmaker}' deckt andere Ausgänge ab als das erste Buch — "
                "Märkte müssen vor dem Consensus normalisiert sein."
            )
        w = weights.get(bookmaker.lower(), default_weight)
        if w <= 0.0:
            continue
        result = devig(odds, method=method)
        for key, p in result.probabilities.items():
            accum[key] += w * p
        total_weight += w
        used_books.append(bookmaker)

    if total_weight <= 0.0:
        raise ValueError("Alle Sharp-Bücher hatten Gewicht 0 — keine faire Linie möglich.")

    # Renormieren: gewichtete Mittel summieren nur näherungsweise auf 1.
    avg = {k: v / total_weight for k, v in accum.items()}
    norm = sum(avg.values())
    probs = {k: v / norm for k, v in avg.items()}
    return FairLine(probs, method, len(used_books), tuple(used_books))
