"""Value-Berechnung: EV, Edge, Filter. Geldnahe Werte als ``Decimal``.

``EV   = p_true · odds_yeet − 1``
``Edge = p_true − 1/odds_yeet``

Ein Signal entsteht nur, wenn ALLE Filter zutreffen (CLAUDE.md, eiserne Regel):
``odds ≥ min_odds`` UND ``EV ≥ min_ev`` UND ``Edge ≥ min_edge``.

Zusätzlich der **Robust-Modus**: der Edge muss über mehrere De-Vig-Methoden
hinweg bestehen. Schwankt das Signal je nach Methode, ist es kein robuster
Value, sondern ein Artefakt der Methodenwahl → kein Signal.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from engine.novig import devig

_Q = Decimal("0.000001")  # 6 Nachkommastellen für EV/Edge


def _d(x: float | Decimal) -> Decimal:
    """Robuste Konvertierung nach Decimal (float über str, um Bit-Rauschen zu meiden)."""
    return x if isinstance(x, Decimal) else Decimal(str(x))


@dataclass(frozen=True)
class ValueResult:
    """Ergebnis einer Value-Bewertung einer yeet.com-Quote.

    Attributes:
        ev: erwarteter Wert pro Einheit Einsatz (``p_true·odds − 1``).
        edge: Wahrscheinlichkeits-Vorsprung (``p_true − 1/odds``).
        fair_odds: faire Quote (``1/p_true``).
        odds: bewertete yeet.com-Quote.
        p_true: zugrunde gelegte wahre Wahrscheinlichkeit.
        is_value: True, wenn ALLE Filter bestanden wurden.
        is_robust: True, wenn der Edge zusätzlich methoden-robust ist
            (None, wenn nicht geprüft).
        reasons: Filter, die NICHT bestanden wurden (leer ⇒ Value).
    """

    ev: Decimal
    edge: Decimal
    fair_odds: Decimal
    odds: Decimal
    p_true: float
    is_value: bool
    is_robust: bool | None
    reasons: tuple[str, ...]


def compute_ev_edge(p_true: float, odds: Decimal) -> tuple[Decimal, Decimal]:
    """Reine Kennzahlen ohne Filter: ``(EV, Edge)`` als ``Decimal``."""
    p = _d(p_true)
    ev = (p * odds - Decimal(1)).quantize(_Q, rounding=ROUND_HALF_UP)
    edge = (p - Decimal(1) / odds).quantize(_Q, rounding=ROUND_HALF_UP)
    return ev, edge


def evaluate_value(
    p_true: float,
    odds: Decimal,
    *,
    min_odds: Decimal = Decimal("1.5"),
    min_ev: Decimal = Decimal("0.03"),
    min_edge: Decimal = Decimal("0.02"),
) -> ValueResult:
    """Bewerte eine einzelne yeet.com-Quote gegen ``p_true``.

    Args:
        p_true: wahre Wahrscheinlichkeit (Sharp-Consensus, optional KI-adjustiert).
        odds: yeet.com-Dezimalquote.
        min_odds, min_ev, min_edge: Filter-Schwellen.

    Returns:
        :class:`ValueResult`. ``is_value`` ist nur True, wenn alle drei Filter
        bestehen. ``is_robust`` bleibt ``None`` (hier nicht geprüft).
    """
    ev, edge = compute_ev_edge(p_true, odds)
    fair_odds = (Decimal(1) / _d(p_true)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    reasons: list[str] = []
    if odds < min_odds:
        reasons.append(f"odds<{min_odds}")
    if ev < min_ev:
        reasons.append(f"EV<{min_ev}")
    if edge < min_edge:
        reasons.append(f"Edge<{min_edge}")

    return ValueResult(
        ev=ev,
        edge=edge,
        fair_odds=fair_odds,
        odds=odds,
        p_true=p_true,
        is_value=not reasons,
        is_robust=None,
        reasons=tuple(reasons),
    )


def evaluate_value_robust(
    sharp_odds: Mapping[str, Decimal],
    selection_key: str,
    odds_yeet: Decimal,
    *,
    methods: Sequence[str] = ("shin", "power", "multiplicative"),
    ki_delta: float = 0.0,
    min_odds: Decimal = Decimal("1.5"),
    min_ev: Decimal = Decimal("0.03"),
    min_edge: Decimal = Decimal("0.02"),
) -> ValueResult:
    """Methoden-robuste Value-Bewertung gegen einen Sharp-Markt.

    De-vigged denselben Sharp-Markt mit mehreren Methoden und bewertet jede
    daraus folgende ``p_true``. Das Signal gilt nur als robuster Value, wenn der
    Filter unter ALLEN Methoden besteht. Berichtet wird die *konservativste*
    Methode (kleinster EV) — so wird der Edge nie überzeichnet.

    Args:
        sharp_odds: vollständiger Sharp-Markt ``selection_key -> Quote``.
        selection_key: zu bewertender Ausgang.
        odds_yeet: yeet.com-Quote für diesen Ausgang.
        methods: De-Vig-Methoden, über die der Edge robust sein muss.
        ki_delta: bereits gekapptes KI-Delta (wird auf jede ``p_fair`` addiert).
        min_odds, min_ev, min_edge: Filter-Schwellen.

    Returns:
        :class:`ValueResult` der konservativsten Methode. ``is_robust`` ist True,
        wenn alle Methoden den Filter bestehen.
    """
    if not methods:
        raise ValueError("Robust-Modus braucht mindestens eine De-Vig-Methode.")

    per_method: list[ValueResult] = []
    for method in methods:
        result = devig(sharp_odds, method=method)
        if selection_key not in result.probabilities:
            raise ValueError(f"Ausgang '{selection_key}' fehlt im Sharp-Markt.")
        p_true = max(0.01, min(0.99, result.probabilities[selection_key] + ki_delta))
        per_method.append(
            evaluate_value(
                p_true,
                odds_yeet,
                min_odds=min_odds,
                min_ev=min_ev,
                min_edge=min_edge,
            )
        )

    # Konservativste Methode = kleinster EV; robust = alle bestehen.
    worst = min(per_method, key=lambda r: r.ev)
    is_robust = all(r.is_value for r in per_method)
    return ValueResult(
        ev=worst.ev,
        edge=worst.edge,
        fair_odds=worst.fair_odds,
        odds=worst.odds,
        p_true=worst.p_true,
        is_value=worst.is_value,
        is_robust=is_robust,
        reasons=worst.reasons,
    )
