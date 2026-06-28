"""Consensus-Tests: gewichtetes Mittel mehrerer Sharp-Bücher."""

from __future__ import annotations

from decimal import Decimal

import pytest

from engine.consensus import fair_line_from_books


def test_single_book_equals_plain_devig() -> None:
    from engine.novig import shin

    books = [("pinnacle", {"h": Decimal("1.80"), "a": Decimal("2.10")})]
    fl = fair_line_from_books(books, method="shin")
    direct = shin({"h": Decimal("1.80"), "a": Decimal("2.10")})
    assert fl.p("h") == pytest.approx(direct.probabilities["h"], abs=1e-9)
    assert fl.n_books == 1


def test_consensus_sums_to_one_and_blends() -> None:
    books = [
        ("pinnacle", {"h": Decimal("1.80"), "a": Decimal("2.10")}),
        ("betfair", {"h": Decimal("1.83"), "a": Decimal("2.05")}),
    ]
    fl = fair_line_from_books(books, method="shin", weights={"pinnacle": 1.0, "betfair": 0.7})
    assert fl.p("h") + fl.p("a") == pytest.approx(1.0, abs=1e-9)
    assert fl.n_books == 2
    # Pinnacle (h niedriger bepreist) zieht stärker → Blend zwischen beiden Büchern
    assert 0.53 < fl.p("h") < 0.55


def test_higher_weight_pulls_toward_that_book() -> None:
    books = [
        ("pinnacle", {"h": Decimal("1.80"), "a": Decimal("2.10")}),
        ("betfair", {"h": Decimal("2.10"), "a": Decimal("1.80")}),
    ]
    heavy_pinnacle = fair_line_from_books(
        books, method="multiplicative", weights={"pinnacle": 1.0, "betfair": 0.1}
    )
    heavy_betfair = fair_line_from_books(
        books, method="multiplicative", weights={"pinnacle": 0.1, "betfair": 1.0}
    )
    assert heavy_pinnacle.p("h") > heavy_betfair.p("h")


def test_zero_weight_book_is_skipped() -> None:
    books = [
        ("pinnacle", {"h": Decimal("1.80"), "a": Decimal("2.10")}),
        ("junk", {"h": Decimal("5.00"), "a": Decimal("1.10")}),
    ]
    fl = fair_line_from_books(
        books, method="multiplicative", weights={"pinnacle": 1.0, "junk": 0.0}
    )
    assert fl.n_books == 1
    assert fl.books == ("pinnacle",)


def test_mismatched_markets_raise() -> None:
    books = [
        ("pinnacle", {"h": Decimal("1.80"), "a": Decimal("2.10")}),
        ("betfair", {"h": Decimal("1.80"), "d": Decimal("3.0"), "a": Decimal("4.0")}),
    ]
    with pytest.raises(ValueError, match="andere Ausgänge"):
        fair_line_from_books(books)


def test_empty_books_raise() -> None:
    with pytest.raises(ValueError, match="mindestens ein Buch"):
        fair_line_from_books([])
