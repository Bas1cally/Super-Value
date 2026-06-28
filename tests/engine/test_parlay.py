"""Parlay-Tests: Kombis nur aus unabhängigen +EV-Legs, höhere Schwelle."""

from __future__ import annotations

from decimal import Decimal

import pytest

from engine.parlay import ParlayLeg, build_parlays


def _leg(event: str, odds: str, p: float) -> ParlayLeg:
    return ParlayLeg(event_id=event, selection_key=f"{event}-pick", odds=Decimal(odds), p_true=p)


def test_two_independent_value_legs_form_a_combo() -> None:
    # Leg A: 1.95 @ p 0.60 (EV +17 %), Leg B: 1.80 @ p 0.65 (EV +17 %)
    legs = [_leg("m1", "1.95", 0.60), _leg("m2", "1.80", 0.65)]
    combos = build_parlays(legs, min_legs=2, max_legs=2, min_ev_combo=Decimal("0.08"))
    assert len(combos) == 1
    c = combos[0]
    # odds_combo = 1.95*1.80 = 3.51; p_combo = 0.60*0.65 = 0.39
    assert c.odds_combo == pytest.approx(Decimal("3.51"), abs=Decimal("1e-4"))
    assert c.p_combo == pytest.approx(0.39, abs=1e-9)
    # EV = 0.39*3.51 - 1 = 0.3689
    assert c.ev_combo == pytest.approx(Decimal("0.3689"), abs=Decimal("1e-4"))


def test_legs_from_same_event_are_not_combined() -> None:
    """Zwei Legs aus demselben Event sind korreliert → keine Kombi."""
    legs = [_leg("same", "1.95", 0.60), _leg("same", "1.80", 0.65)]
    # selber event_id für beide
    legs[1] = ParlayLeg("same", "other", Decimal("1.80"), 0.65)
    combos = build_parlays(legs, min_legs=2, max_legs=2)
    assert combos == []


def test_combo_below_higher_threshold_is_dropped() -> None:
    """Zwei knappe Einzel-Values ergeben keine Kombi über der 8 %-Schwelle."""
    # je EV ~ +2 %: 1.02/0.51... wähle p so, dass EV_combo < 0.08
    legs = [_leg("m1", "1.50", 0.69), _leg("m2", "1.50", 0.69)]
    # EV einzeln = 0.69*1.5-1 = 0.035; combo: 0.69^2 * 2.25 - 1 = 0.0712 < 0.08
    combos = build_parlays(legs, min_legs=2, max_legs=2, min_ev_combo=Decimal("0.08"))
    assert combos == []


def test_results_sorted_by_ev_descending() -> None:
    legs = [
        _leg("m1", "2.00", 0.60),
        _leg("m2", "2.00", 0.58),
        _leg("m3", "2.00", 0.62),
    ]
    combos = build_parlays(legs, min_legs=2, max_legs=3, min_ev_combo=Decimal("0.0"))
    evs = [c.ev_combo for c in combos]
    assert evs == sorted(evs, reverse=True)


def test_respects_max_legs() -> None:
    legs = [_leg(f"m{i}", "2.00", 0.60) for i in range(4)]
    combos = build_parlays(legs, min_legs=2, max_legs=2, min_ev_combo=Decimal("0.0"))
    assert all(len(c.legs) == 2 for c in combos)


def test_min_legs_must_be_at_least_two() -> None:
    with pytest.raises(ValueError, match="mindestens 2 Legs"):
        build_parlays([_leg("m1", "2.0", 0.6)], min_legs=1, max_legs=2)


def test_max_legs_not_below_min() -> None:
    with pytest.raises(ValueError, match="max_legs"):
        build_parlays([], min_legs=3, max_legs=2)
