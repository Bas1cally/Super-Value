"""Fair-Value Engine: No-Vig, KI-Adjustierung, EV/Edge, Parlay.

Die Engine kennt keine Quellen-Details. Kopplung nur über die Typen in
``engine.types`` (bzw. die DB). Reine Mathematik, deterministisch, testbar.
"""

from engine.consensus import FairLine, fair_line_from_books
from engine.ki_adjust import KiDelta, apply_ki_adjustment
from engine.novig import DevigResult, available_methods, devig
from engine.parlay import ParlayLeg, ParlaySignal, build_parlays
from engine.types import OddsRecord, OddsSource
from engine.value import (
    ValueResult,
    compute_ev_edge,
    evaluate_value,
    evaluate_value_robust,
)

__all__ = [
    "DevigResult",
    "devig",
    "available_methods",
    "FairLine",
    "fair_line_from_books",
    "KiDelta",
    "apply_ki_adjustment",
    "ValueResult",
    "compute_ev_edge",
    "evaluate_value",
    "evaluate_value_robust",
    "ParlayLeg",
    "ParlaySignal",
    "build_parlays",
    "OddsRecord",
    "OddsSource",
]
