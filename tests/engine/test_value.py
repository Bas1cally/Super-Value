"""Value-Tests: EV, Edge, Filter, Robust-Modus — mit festen Zahlen."""

from __future__ import annotations

from decimal import Decimal

import pytest

from engine.value import compute_ev_edge, evaluate_value, evaluate_value_robust


# --------------------------------------------------------------------------- #
# Kennzahlen
# --------------------------------------------------------------------------- #
def test_compute_ev_edge_concrete() -> None:
    # p_true 0.55, yeet 1.95: EV = 0.55*1.95-1 = 0.0725; Edge = 0.55-1/1.95
    ev, edge = compute_ev_edge(0.55, Decimal("1.95"))
    assert ev == pytest.approx(Decimal("0.0725"), abs=Decimal("1e-6"))
    assert edge == pytest.approx(Decimal("0.037179"), abs=Decimal("1e-6"))


def test_fair_odds_is_inverse_of_p_true() -> None:
    result = evaluate_value(0.5, Decimal("2.10"))
    assert result.fair_odds == pytest.approx(Decimal("2.0"), abs=Decimal("1e-4"))


# --------------------------------------------------------------------------- #
# Filter
# --------------------------------------------------------------------------- #
def test_clear_value_passes_all_filters() -> None:
    result = evaluate_value(0.55, Decimal("1.95"))
    assert result.is_value is True
    assert result.reasons == ()
    assert result.ev >= Decimal("0.03")
    assert result.edge >= Decimal("0.02")


def test_no_value_when_ev_and_edge_too_low() -> None:
    # p_true 0.50, odds 1.90: EV = -0.05, Edge < 0
    result = evaluate_value(0.50, Decimal("1.90"))
    assert result.is_value is False
    assert "EV<0.03" in result.reasons
    assert "Edge<0.02" in result.reasons


def test_high_ev_but_odds_below_minimum_is_blocked() -> None:
    """Quote-Filter und Value-Filter sind getrennt: hoher EV bei Quote < 1.5
    ist KEIN Signal (eiserne Regel)."""
    result = evaluate_value(0.80, Decimal("1.40"))  # EV = 0.12, aber odds < 1.5
    assert result.is_value is False
    assert result.reasons == ("odds<1.5",)


def test_thresholds_are_configurable() -> None:
    # Mit lockeren Schwellen wird ein knapper Fall zum Value:
    result = evaluate_value(0.52, Decimal("1.95"), min_ev=Decimal("0.0"), min_edge=Decimal("0.0"))
    assert result.is_value is True


# --------------------------------------------------------------------------- #
# Robust-Modus — der eigentliche Edge-Schutz
# --------------------------------------------------------------------------- #
def test_robust_mode_rejects_method_dependent_phantom_value() -> None:
    """Außenseiter @ 3.20: multiplikativ passiert BEIDE Filter (Phantom-Value),
    Shin/Power scheitern am Edge. Der Robust-Modus muss das Signal verwerfen."""
    sharp = {"fav": Decimal("1.45"), "dog": Decimal("2.90")}

    # Naiv-multiplikativ allein würde Value sehen (EV +6.7 %, Edge +2.1 %):
    naive = evaluate_value_robust(sharp, "dog", Decimal("3.20"), methods=("multiplicative",))
    assert naive.is_value is True

    # Robust über Shin+Power+multiplikativ → konservativste Methode blockt:
    robust = evaluate_value_robust(
        sharp, "dog", Decimal("3.20"), methods=("shin", "power", "multiplicative")
    )
    assert robust.is_robust is False
    assert robust.is_value is False


def test_robust_mode_confirms_genuine_value() -> None:
    """Klarer Favoriten-Value besteht unter allen Methoden → robust."""
    sharp = {"fav": Decimal("1.45"), "dog": Decimal("2.90")}
    # yeet bietet den Favoriten zu 1.62 (fair ~1.45) → deutlicher Value
    robust = evaluate_value_robust(
        sharp, "fav", Decimal("1.62"), methods=("shin", "power", "multiplicative")
    )
    assert robust.is_value is True
    assert robust.is_robust is True


def test_robust_reports_most_conservative_method() -> None:
    """Berichteter EV ist der kleinste über alle Methoden (nie überzeichnet)."""
    sharp = {"fav": Decimal("1.45"), "dog": Decimal("2.90")}
    robust = evaluate_value_robust(
        sharp, "dog", Decimal("3.10"), methods=("shin", "power", "multiplicative")
    )
    # power ist hier am konservativsten (kleinster p_true für den Außenseiter)
    assert robust.ev < Decimal("0.03")


def test_robust_applies_ki_delta() -> None:
    sharp = {"fav": Decimal("1.45"), "dog": Decimal("2.90")}
    base = evaluate_value_robust(sharp, "fav", Decimal("1.55"), methods=("shin",))
    boosted = evaluate_value_robust(sharp, "fav", Decimal("1.55"), methods=("shin",), ki_delta=0.05)
    assert boosted.ev > base.ev


def test_robust_requires_at_least_one_method() -> None:
    with pytest.raises(ValueError, match="mindestens eine"):
        evaluate_value_robust(
            {"a": Decimal("1.8"), "b": Decimal("2.1")}, "a", Decimal("2.0"), methods=()
        )
