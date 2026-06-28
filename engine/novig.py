"""No-Vig: Marge aus der Sharp-Quote rausrechnen → faire Wahrscheinlichkeit.

Mehrere Methoden, weil die Methodenwahl direkt über die *Qualität* des Edges
entscheidet. Die simple proportionale Methode (``multiplicative``) verteilt die
Marge gleichmäßig und überschätzt dadurch systematisch Favoriten — das erzeugt
Phantom-Value auf Außenseitern. ``shin`` und ``power`` korrigieren diesen
Favorite-Longshot-Bias und liefern realistischere faire Wahrscheinlichkeiten.

Eingang je Methode: Mapping ``selection_key -> Decimal(dezimalquote)`` eines
*einzelnen* Sharp-Buchs für einen vollständigen Markt (alle Ausgänge).
Ausgang: faire Wahrscheinlichkeiten, die exakt zu 1 summieren.

Wahrscheinlichkeiten werden intern als ``float`` gerechnet (Wurzelfindung);
die Quoten kommen als ``Decimal`` rein. Edge/EV (geldnah) entstehen erst in
``engine.value`` und sind dort wieder ``Decimal``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

# Numerik
_EPS = 1e-12
_MARGIN_EPS = 1e-9  # darunter gilt der Markt als margenfrei
_MAX_ITER = 200


@dataclass(frozen=True)
class DevigResult:
    """Ergebnis einer De-Vig-Berechnung für einen Markt.

    Attributes:
        method: Name der verwendeten Methode.
        probabilities: faire Wahrscheinlichkeit je ``selection_key`` (Summe = 1).
        overround: Buchmacher-Overround ``M = Σ 1/odds_i`` (z. B. 1.03 = 3 % Marge).
        param: methodenspezifischer Parameter (Shin ``z``, Power ``k``,
            Odds-Ratio ``c``) oder ``None`` für parameterfreie Methoden.
    """

    method: str
    probabilities: dict[str, float]
    overround: float
    param: float | None

    def fair_odds(self) -> dict[str, float]:
        """Faire Dezimalquote je Ausgang (Kehrwert der fairen Wahrscheinlichkeit)."""
        return {k: (1.0 / p if p > _EPS else math.inf) for k, p in self.probabilities.items()}


def _raw_probs(odds: Mapping[str, Decimal]) -> dict[str, float]:
    """Roh-Wahrscheinlichkeiten ``p_i = 1/odds_i`` (summieren zu ``M``)."""
    if len(odds) < 2:
        raise ValueError("De-Vig braucht einen vollständigen Markt mit ≥ 2 Ausgängen.")
    raw: dict[str, float] = {}
    for key, dec in odds.items():
        o = float(dec)
        if o <= 1.0:
            raise ValueError(f"Quote {dec} für '{key}' ist ≤ 1.0 — ungültig.")
        raw[key] = 1.0 / o
    return raw


# --------------------------------------------------------------------------- #
# Methode 1: multiplikativ / proportional (Baseline — was der Plan ursprünglich nutzt)
# --------------------------------------------------------------------------- #
def multiplicative(odds: Mapping[str, Decimal]) -> DevigResult:
    """Proportionale Normierung: ``p_i = (1/odds_i) / M``.

    Schnell und simpel, aber margen-naiv: überschätzt Favoriten.
    """
    raw = _raw_probs(odds)
    m = sum(raw.values())
    probs = {k: v / m for k, v in raw.items()}
    return DevigResult("multiplicative", probs, m, None)


# --------------------------------------------------------------------------- #
# Methode 2: additiv (gleiche absolute Marge je Ausgang)
# --------------------------------------------------------------------------- #
def additive(odds: Mapping[str, Decimal]) -> DevigResult:
    """Gleichverteilte Marge: ``p_i = 1/odds_i − (M−1)/n``.

    Zieht jedem Ausgang denselben Margen-Absolutbetrag ab. Kann bei extremen
    Favoriten negativ werden → wird geklippt und renormiert.
    """
    raw = _raw_probs(odds)
    m = sum(raw.values())
    n = len(raw)
    share = (m - 1.0) / n
    probs = {k: max(v - share, _EPS) for k, v in raw.items()}
    total = sum(probs.values())
    probs = {k: v / total for k, v in probs.items()}
    return DevigResult("additive", probs, m, None)


# --------------------------------------------------------------------------- #
# Methode 3: Power (korrigiert Favorite-Longshot-Bias)
# --------------------------------------------------------------------------- #
def power(odds: Mapping[str, Decimal]) -> DevigResult:
    """Power-Methode: finde ``k`` mit ``Σ (1/odds_i)^k = 1``.

    Da alle Roh-Wahrscheinlichkeiten < 1 sind, schrumpft Potenzieren mit ``k>1``
    Außenseiter stärker als Favoriten — das entzerrt die Marge realistischer.
    """
    raw = _raw_probs(odds)
    m = sum(raw.values())
    if m - 1.0 <= _MARGIN_EPS:
        probs = {k: v / m for k, v in raw.items()}
        return DevigResult("power", probs, m, 1.0)

    values = list(raw.values())

    def sum_pow(k: float) -> float:
        return sum(v**k for v in values)

    # f(k) = Σ raw^k − 1 ist fallend in k; f(1) = M−1 > 0. Obergrenze suchen.
    lo, hi = 1.0, 2.0
    for _ in range(_MAX_ITER):
        if sum_pow(hi) < 1.0:
            break
        hi *= 2.0
    for _ in range(_MAX_ITER):
        mid = 0.5 * (lo + hi)
        if sum_pow(mid) > 1.0:
            lo = mid
        else:
            hi = mid
    k = 0.5 * (lo + hi)
    probs = {key: v**k for key, v in raw.items()}
    total = sum(probs.values())
    probs = {key: v / total for key, v in probs.items()}
    return DevigResult("power", probs, m, k)


# --------------------------------------------------------------------------- #
# Methode 4: Shin (informierte Wetter / Insider-Anteil z)
# --------------------------------------------------------------------------- #
def shin(odds: Mapping[str, Decimal]) -> DevigResult:
    """Shin-Methode: modelliert die Marge als Schutz gegen einen Anteil ``z``
    informierter Wetter.

    ``p_i(z) = (√(z² + 4(1−z)·raw_i²/M) − z) / (2(1−z))``; ``z`` wird so gesucht,
    dass ``Σ p_i = 1``. Entfernt relativ mehr Marge vom Favoriten und gilt
    empirisch als eine der genauesten De-Vig-Methoden.
    """
    raw = _raw_probs(odds)
    m = sum(raw.values())
    if m - 1.0 <= _MARGIN_EPS:
        probs = {k: v / m for k, v in raw.items()}
        return DevigResult("shin", probs, m, 0.0)

    values = list(raw.values())

    def shin_p(v: float, z: float) -> float:
        return (math.sqrt(z * z + 4.0 * (1.0 - z) * v * v / m) - z) / (2.0 * (1.0 - z))

    def sum_p(z: float) -> float:
        return sum(shin_p(v, z) for v in values)

    # f(z) = Σ p_i(z) − 1 ist fallend; f(0) = √M − 1 > 0, f(1⁻) < 0.
    lo, hi = 0.0, 1.0 - 1e-9
    for _ in range(_MAX_ITER):
        mid = 0.5 * (lo + hi)
        if sum_p(mid) > 1.0:
            lo = mid
        else:
            hi = mid
    z = 0.5 * (lo + hi)
    probs = {key: shin_p(v, z) for key, v in raw.items()}
    total = sum(probs.values())
    probs = {key: v / total for key, v in probs.items()}
    return DevigResult("shin", probs, m, z)


# --------------------------------------------------------------------------- #
# Methode 5: Odds-Ratio (Cheung)
# --------------------------------------------------------------------------- #
def odds_ratio(odds: Mapping[str, Decimal]) -> DevigResult:
    """Odds-Ratio-Methode: konstantes Quotenverhältnis ``c`` zwischen Buch- und
    fairer Wahrscheinlichkeit.

    Mit ``a_i = raw_i/(1−raw_i)`` gilt ``p_i = a_i/(c + a_i)``; ``c`` wird so
    gesucht, dass ``Σ p_i = 1``.
    """
    raw = _raw_probs(odds)
    m = sum(raw.values())
    if m - 1.0 <= _MARGIN_EPS:
        probs = {k: v / m for k, v in raw.items()}
        return DevigResult("odds_ratio", probs, m, 1.0)

    a = [v / (1.0 - v) for v in raw.values()]
    keys = list(raw.keys())

    def sum_p(c: float) -> float:
        return sum(ai / (c + ai) for ai in a)

    # f(c) = Σ p_i(c) − 1 fallend; f(1) = M−1 > 0. Obergrenze suchen.
    lo, hi = 1.0, 2.0
    for _ in range(_MAX_ITER):
        if sum_p(hi) < 1.0:
            break
        hi *= 2.0
    for _ in range(_MAX_ITER):
        mid = 0.5 * (lo + hi)
        if sum_p(mid) > 1.0:
            lo = mid
        else:
            hi = mid
    c = 0.5 * (lo + hi)
    probs_list = [ai / (c + ai) for ai in a]
    total = sum(probs_list)
    probs = {keys[i]: probs_list[i] / total for i in range(len(keys))}
    return DevigResult("odds_ratio", probs, m, c)


_METHODS = {
    "multiplicative": multiplicative,
    "additive": additive,
    "power": power,
    "shin": shin,
    "odds_ratio": odds_ratio,
}


def available_methods() -> tuple[str, ...]:
    """Namen aller registrierten De-Vig-Methoden."""
    return tuple(_METHODS.keys())


def devig(odds: Mapping[str, Decimal], method: str = "shin") -> DevigResult:
    """Dispatcher: wendet die benannte De-Vig-Methode an.

    Args:
        odds: vollständiger Markt eines Sharp-Buchs, ``selection_key -> Quote``.
        method: einer der Namen aus :func:`available_methods`.

    Raises:
        ValueError: bei unbekannter Methode oder ungültigem Markt.
    """
    try:
        fn = _METHODS[method]
    except KeyError:
        raise ValueError(
            f"Unbekannte De-Vig-Methode '{method}'. Verfügbar: {available_methods()}"
        ) from None
    return fn(odds)
