"""Parlay-Builder: Kombis ausschließlich aus bereits validierten +EV-Legs.

``odds_combo = Π odds_i``, ``p_combo = Π p_true_i`` (Unabhängigkeit),
``EV_combo = p_combo · odds_combo − 1``.

Eiserne Regeln (CLAUDE.md):
- nur Legs, die EINZELN den Value-Filter bestehen (niemals Value-Leg + Auffüller),
- möglichst unabhängig: keine zwei Legs aus demselben Event,
- höhere EV-Schwelle als bei Einzelwetten (Unsicherheiten multiplizieren sich),
- 2..N Legs (Default 2–4).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from itertools import combinations

_Q = Decimal("0.000001")


@dataclass(frozen=True)
class ParlayLeg:
    """Ein einzelnes, bereits als +EV validiertes Leg.

    Attributes:
        event_id: Event des Legs (für die Unabhängigkeitsprüfung).
        selection_key: gewählter Ausgang (für die Anzeige).
        odds: yeet.com-Dezimalquote des Legs.
        p_true: wahre Wahrscheinlichkeit des Legs.
    """

    event_id: str
    selection_key: str
    odds: Decimal
    p_true: float


@dataclass(frozen=True)
class ParlaySignal:
    """Eine bewertete Kombiwette.

    Attributes:
        legs: enthaltene Legs.
        odds_combo: Produkt der Quoten.
        p_combo: Produkt der wahren Wahrscheinlichkeiten (Unabhängigkeit).
        ev_combo: erwarteter Wert der Kombi.
    """

    legs: tuple[ParlayLeg, ...]
    odds_combo: Decimal
    p_combo: float
    ev_combo: Decimal


def _evaluate_combo(legs: tuple[ParlayLeg, ...]) -> ParlaySignal:
    odds_combo = Decimal(1)
    p_combo = 1.0
    for leg in legs:
        odds_combo *= leg.odds
        p_combo *= leg.p_true
    ev = (Decimal(str(p_combo)) * odds_combo - Decimal(1)).quantize(_Q, rounding=ROUND_HALF_UP)
    odds_combo = odds_combo.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return ParlaySignal(legs, odds_combo, p_combo, ev)


def build_parlays(
    legs: list[ParlayLeg],
    *,
    min_legs: int = 2,
    max_legs: int = 4,
    min_ev_combo: Decimal = Decimal("0.08"),
) -> list[ParlaySignal]:
    """Baue alle zulässigen Kombis aus bereits validierten +EV-Legs.

    Args:
        legs: Kandidaten — jedes Leg MUSS einzeln den Value-Filter bestanden haben.
        min_legs: minimale Leg-Anzahl pro Kombi.
        max_legs: maximale Leg-Anzahl pro Kombi.
        min_ev_combo: höhere EV-Schwelle für Kombis.

    Returns:
        Kombi-Signale mit ``ev_combo ≥ min_ev_combo``, absteigend nach EV sortiert.
        Es werden nur Kombis mit paarweise verschiedenen ``event_id`` gebildet
        (Unabhängigkeit; keine korrelierten Legs aus demselben Spiel).
    """
    if min_legs < 2:
        raise ValueError("Eine Kombi braucht mindestens 2 Legs.")
    if max_legs < min_legs:
        raise ValueError("max_legs darf nicht kleiner als min_legs sein.")

    signals: list[ParlaySignal] = []
    for size in range(min_legs, max_legs + 1):
        for combo in combinations(legs, size):
            event_ids = {leg.event_id for leg in combo}
            if len(event_ids) != size:
                continue  # zwei Legs aus demselben Event → korreliert → überspringen
            signal = _evaluate_combo(combo)
            if signal.ev_combo >= min_ev_combo:
                signals.append(signal)

    signals.sort(key=lambda s: s.ev_combo, reverse=True)
    return signals
