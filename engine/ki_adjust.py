"""KI-Adjustierung der fairen Wahrscheinlichkeit — begrenzt und doppelzähl-sicher.

Die Sharp-Linie ist die Basis. Ein LLM (News/Lineups/Verletzungen) liefert ein
*kalibriertes* Delta auf ``p_fair``. Dieses Modul enthält bewusst NICHT den
LLM-Call, sondern nur die Schutz-Mathematik, die den Edge vor LLM-Fehlern
bewahrt:

1. **Kappung** — ``delta`` wird hart auf ``±cap`` begrenzt.
2. **Line-Movement-Dämpfung** — hat sich die Sharp-Linie schon in Richtung des
   Deltas bewegt, ist die Info bereits eingepreist → Delta wird um die
   Bewegung reduziert (kein Doppelzählen).
3. **Confidence-Gate** — unter ``min_confidence`` zählt das Delta nicht; das
   Signal bleibt 'info' statt 'value'.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class KiDelta:
    """Ausgabe des LLM-Info-Layers für einen Ausgang.

    Attributes:
        delta: roh geschätzte Wahrscheinlichkeitsänderung auf ``p_fair``
            (z. B. −0.04 = "−4 % wegen überraschendem Ausfall").
        confidence: Vertrauen des LLM in ``[0, 1]``.
        reason: kurze Begründung für die Signal-Ausgabe.
    """

    delta: float
    confidence: float
    reason: str = ""


@dataclass(frozen=True)
class AdjustResult:
    """Ergebnis der Adjustierung.

    Attributes:
        p_true: adjustierte, geklippte Wahrscheinlichkeit in ``[0.01, 0.99]``.
        applied_delta: tatsächlich angewandtes Delta nach Dämpfung & Kappung.
        gated: True, wenn die Confidence das Gate nicht passierte (Delta = 0).
        reason: durchgereichte Begründung.
    """

    p_true: float
    applied_delta: float
    gated: bool
    reason: str


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def apply_ki_adjustment(
    p_fair: float,
    ki: KiDelta,
    *,
    cap: Decimal = Decimal("0.06"),
    min_confidence: float = 0.6,
    line_move: float = 0.0,
    line_move_damping: Decimal = Decimal("1.0"),
) -> AdjustResult:
    """Wende ein KI-Delta sicher auf eine faire Wahrscheinlichkeit an.

    Args:
        p_fair: faire Wahrscheinlichkeit aus dem Sharp-Consensus.
        ki: KI-Delta inkl. Confidence.
        cap: maximaler Betrag des Deltas (±).
        min_confidence: Confidence-Gate; darunter wird das Delta verworfen.
        line_move: bereits beobachtete Bewegung von ``p_fair`` im jüngsten
            Fenster (positiv = der Markt hat den Ausgang wahrscheinlicher
            bepreist). Bewegt sich die Linie in dieselbe Richtung wie das Delta,
            ist die Info teilweise eingepreist und das Delta wird reduziert.
        line_move_damping: wie stark die Linienbewegung angerechnet wird (0..1+).

    Returns:
        :class:`AdjustResult` mit geklippter ``p_true`` und Diagnose.
    """
    # 1) Confidence-Gate
    if ki.confidence < min_confidence:
        return AdjustResult(_clip(p_fair, 0.01, 0.99), 0.0, gated=True, reason=ki.reason)

    delta = ki.delta

    # 2) Line-Movement-Dämpfung — nur wenn Bewegung & Delta gleichgerichtet sind.
    if delta != 0.0 and line_move != 0.0 and (delta > 0) == (line_move > 0):
        damp = float(line_move_damping) * abs(line_move)
        sign = 1.0 if delta > 0 else -1.0
        # Restdelta nach Abzug der bereits eingepreisten Bewegung (min. 0).
        delta = sign * max(abs(delta) - damp, 0.0)

    # 3) Kappung
    cap_f = float(cap)
    delta = _clip(delta, -cap_f, cap_f)

    p_true = _clip(p_fair + delta, 0.01, 0.99)
    return AdjustResult(p_true, p_true - p_fair, gated=False, reason=ki.reason)
