"""No-Vig-Tests mit festen Zahlenbeispielen.

Anker: Pinnacle 1.80 / 2.10 → multiplikativ p_fair(home) = 0.538 (CLAUDE.md §Mathe).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from engine import novig

TWO_WAY = {"home": Decimal("1.80"), "away": Decimal("2.10")}
THREE_WAY = {"h": Decimal("2.50"), "d": Decimal("3.40"), "a": Decimal("3.00")}
BALANCED = {"a": Decimal("2.00"), "b": Decimal("2.00")}


# --------------------------------------------------------------------------- #
# Invarianten über alle Methoden
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("method", novig.available_methods())
@pytest.mark.parametrize("market", [TWO_WAY, THREE_WAY, BALANCED])
def test_probabilities_sum_to_one(method: str, market: dict[str, Decimal]) -> None:
    result = novig.devig(market, method)
    assert sum(result.probabilities.values()) == pytest.approx(1.0, abs=1e-9)
    assert all(0.0 < p < 1.0 for p in result.probabilities.values())


@pytest.mark.parametrize("method", novig.available_methods())
def test_balanced_market_is_fifty_fifty(method: str) -> None:
    """Ohne Marge (2.00/2.00) liefert jede Methode exakt 0.5/0.5."""
    result = novig.devig(BALANCED, method)
    assert result.probabilities["a"] == pytest.approx(0.5, abs=1e-9)
    assert result.probabilities["b"] == pytest.approx(0.5, abs=1e-9)
    assert result.overround == pytest.approx(1.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# Feste Anker je Methode (2-Wege 1.80/2.10)
# --------------------------------------------------------------------------- #
def test_multiplicative_matches_claude_example() -> None:
    result = novig.multiplicative(TWO_WAY)
    assert result.probabilities["home"] == pytest.approx(0.538462, abs=1e-5)
    assert result.probabilities["away"] == pytest.approx(0.461538, abs=1e-5)
    assert result.overround == pytest.approx(1.031746, abs=1e-5)
    # faire Quote home ≈ 1.857 (Plan §4.1)
    assert result.fair_odds()["home"] == pytest.approx(1.857, abs=1e-3)


def test_additive_anchor() -> None:
    result = novig.additive(TWO_WAY)
    assert result.probabilities["home"] == pytest.approx(0.539683, abs=1e-5)
    assert result.probabilities["away"] == pytest.approx(0.460317, abs=1e-5)


def test_power_anchor() -> None:
    result = novig.power(TWO_WAY)
    assert result.param == pytest.approx(1.04744, abs=1e-4)
    assert result.probabilities["home"] == pytest.approx(0.540278, abs=1e-5)


def test_shin_anchor() -> None:
    result = novig.shin(TWO_WAY)
    assert result.param == pytest.approx(0.031752, abs=1e-5)  # Insider-Anteil z
    assert result.probabilities["home"] == pytest.approx(0.539683, abs=1e-5)


def test_odds_ratio_anchor() -> None:
    result = novig.odds_ratio(TWO_WAY)
    assert result.param == pytest.approx(1.066004, abs=1e-5)
    assert result.probabilities["home"] == pytest.approx(0.539723, abs=1e-5)


# --------------------------------------------------------------------------- #
# Der eigentliche Edge-Gewinn: FLB-Korrektur
# --------------------------------------------------------------------------- #
def test_shin_and_power_correct_favorite_longshot_bias() -> None:
    """Shin/Power geben dem Favoriten MEHR, dem Außenseiter WENIGER als die
    naive multiplikative Methode — sonst entsteht Phantom-Value auf Außenseitern.
    """
    mult = novig.multiplicative(TWO_WAY).probabilities
    shin = novig.shin(TWO_WAY).probabilities
    power = novig.power(TWO_WAY).probabilities

    # Favorit (home) bekommt mehr Wahrscheinlichkeit:
    assert shin["home"] > mult["home"]
    assert power["home"] > mult["home"]
    # Außenseiter (away) bekommt entsprechend weniger:
    assert shin["away"] < mult["away"]
    assert power["away"] < mult["away"]


# --------------------------------------------------------------------------- #
# Fehlerfälle & Dispatcher
# --------------------------------------------------------------------------- #
def test_devig_rejects_unknown_method() -> None:
    with pytest.raises(ValueError, match="Unbekannte De-Vig-Methode"):
        novig.devig(TWO_WAY, "does_not_exist")


def test_devig_rejects_single_outcome() -> None:
    with pytest.raises(ValueError, match="≥ 2 Ausgängen"):
        novig.devig({"only": Decimal("1.50")}, "shin")


def test_devig_rejects_invalid_odds() -> None:
    with pytest.raises(ValueError, match="≤ 1.0"):
        novig.devig({"a": Decimal("1.00"), "b": Decimal("2.00")}, "shin")


def test_dispatcher_matches_direct_call() -> None:
    for method in novig.available_methods():
        via_dispatch = novig.devig(THREE_WAY, method).probabilities
        via_direct = getattr(novig, method)(THREE_WAY).probabilities
        assert via_dispatch == via_direct
