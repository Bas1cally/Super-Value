"""KI-Adjustierungs-Tests: Kappung, Confidence-Gate, Line-Movement-Dämpfung."""

from __future__ import annotations

from decimal import Decimal

import pytest

from engine.ki_adjust import KiDelta, apply_ki_adjustment


def test_confident_delta_is_applied() -> None:
    r = apply_ki_adjustment(0.50, KiDelta(0.04, 0.8, "Lineup bestätigt"))
    assert r.p_true == pytest.approx(0.54, abs=1e-9)
    assert r.applied_delta == pytest.approx(0.04, abs=1e-9)
    assert r.gated is False
    assert r.reason == "Lineup bestätigt"


def test_delta_is_capped() -> None:
    r = apply_ki_adjustment(0.50, KiDelta(0.20, 0.9), cap=Decimal("0.06"))
    assert r.p_true == pytest.approx(0.56, abs=1e-9)
    assert r.applied_delta == pytest.approx(0.06, abs=1e-9)


def test_negative_delta_is_capped() -> None:
    r = apply_ki_adjustment(0.50, KiDelta(-0.20, 0.9), cap=Decimal("0.06"))
    assert r.p_true == pytest.approx(0.44, abs=1e-9)


def test_low_confidence_is_gated() -> None:
    r = apply_ki_adjustment(0.50, KiDelta(0.04, 0.3), min_confidence=0.6)
    assert r.gated is True
    assert r.applied_delta == 0.0
    assert r.p_true == pytest.approx(0.50, abs=1e-9)


def test_line_movement_damps_same_direction_delta() -> None:
    """Markt hat sich bereits +0.03 in Delta-Richtung bewegt → Info teilweise
    eingepreist → angewandtes Delta = 0.04 − 0.03 = 0.01."""
    r = apply_ki_adjustment(
        0.50,
        KiDelta(0.04, 0.9),
        line_move=0.03,
        line_move_damping=Decimal("1.0"),
    )
    assert r.applied_delta == pytest.approx(0.01, abs=1e-9)
    assert r.p_true == pytest.approx(0.51, abs=1e-9)


def test_line_movement_fully_prices_in_delta() -> None:
    """Bewegung ≥ Delta → Info vollständig eingepreist → kein Delta mehr."""
    r = apply_ki_adjustment(
        0.50, KiDelta(0.03, 0.9), line_move=0.05, line_move_damping=Decimal("1.0")
    )
    assert r.applied_delta == pytest.approx(0.0, abs=1e-9)


def test_opposite_line_movement_is_not_damped() -> None:
    """Bewegung gegen das Delta → kein Doppelzählen, Delta bleibt voll."""
    r = apply_ki_adjustment(
        0.50, KiDelta(0.04, 0.9), line_move=-0.03, line_move_damping=Decimal("1.0")
    )
    assert r.applied_delta == pytest.approx(0.04, abs=1e-9)


def test_p_true_is_clipped_to_bounds() -> None:
    r = apply_ki_adjustment(0.98, KiDelta(0.06, 0.9), cap=Decimal("0.06"))
    assert r.p_true == pytest.approx(0.99, abs=1e-9)  # geklippt auf 0.99
