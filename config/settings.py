"""Zentrale Konfiguration.

Alle Schwellen, Methoden und Gewichte sind hier konfigurierbar — niemals als
Magic Number im Engine-Code. Geld-/quotenähnliche Werte als ``Decimal``.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Laufzeit-Konfiguration des Value-Bots.

    Werte stammen aus ``.env`` (Prefix ``VALUEBOT_``) oder den Defaults hier.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="VALUEBOT_",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ #
    # Value-/Edge-Filter (Einzelwette)
    # ------------------------------------------------------------------ #
    min_odds: Decimal = Field(
        default=Decimal("1.5"),
        description="Mindestquote bei yeet.com, ab der ein Signal überhaupt zählt.",
    )
    min_ev: Decimal = Field(
        default=Decimal("0.03"),
        description="Mindest-EV (3 %) für ein Einzel-Value-Signal.",
    )
    min_edge: Decimal = Field(
        default=Decimal("0.02"),
        description="Mindest-Edge (p_true − 1/odds) für ein Einzel-Value-Signal.",
    )

    # ------------------------------------------------------------------ #
    # Fair-Value Engine — De-Vig
    # ------------------------------------------------------------------ #
    devig_method: str = Field(
        default="shin",
        description=(
            "Primäre De-Vig-Methode: 'multiplicative' | 'additive' | 'power' "
            "| 'shin' | 'odds_ratio'. 'shin' korrigiert den Favorite-Longshot-"
            "Bias und liefert i. d. R. die genauesten fairen Wahrscheinlichkeiten."
        ),
    )
    robust_methods: tuple[str, ...] = Field(
        default=("shin", "power", "multiplicative"),
        description=(
            "Methoden-Set für den Robust-Modus. Ein Signal überlebt nur, wenn der "
            "Edge über ALLE diese Methoden hinweg die Schwelle hält — killt "
            "Phantom-Value, der nur durch die Methodenwahl entsteht."
        ),
    )
    robust_mode: bool = Field(
        default=True,
        description="Wenn True, muss der Value über 'robust_methods' robust sein.",
    )

    # ------------------------------------------------------------------ #
    # Multi-Book-Sharp-Consensus
    # ------------------------------------------------------------------ #
    sharp_book_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "pinnacle": 1.0,
            "betfair_ex_eu": 0.7,
            "betfair": 0.7,
            "circa": 0.6,
        },
        description=(
            "Gewichtung der Sharp-Bücher beim Consensus. Pinnacle am schärfsten; "
            "unbekannte Bücher erhalten 'default_book_weight'."
        ),
    )
    default_book_weight: float = Field(
        default=0.4,
        description="Gewicht für ein Sharp-Buch, das nicht in sharp_book_weights steht.",
    )

    # ------------------------------------------------------------------ #
    # KI-Adjustierung
    # ------------------------------------------------------------------ #
    ki_delta_cap: Decimal = Field(
        default=Decimal("0.06"),
        description="Maximaler Betrag des KI-p-Deltas (±). Schützt vor LLM-Fehlschätzung.",
    )
    ki_line_move_damping: Decimal = Field(
        default=Decimal("1.0"),
        description=(
            "Dämpfungsfaktor gegen Doppelzählen: hat sich die Sharp-Linie bereits "
            "in Richtung des KI-Deltas bewegt, wird das Delta um diesen Faktor × "
            "der Linienbewegung reduziert (1.0 = volle Anrechnung)."
        ),
    )
    min_ki_confidence: float = Field(
        default=0.6,
        description="Mindest-Confidence der KI, sonst zählt das Delta nicht (Signal = 'info').",
    )

    # ------------------------------------------------------------------ #
    # Parlay / Kombi
    # ------------------------------------------------------------------ #
    parlay_min_ev: Decimal = Field(
        default=Decimal("0.08"),
        description="Höhere EV-Schwelle für Kombis (Unsicherheiten multiplizieren sich).",
    )
    parlay_max_legs: int = Field(default=4, description="Maximale Anzahl Legs pro Kombi.")
    parlay_min_legs: int = Field(default=2, description="Minimale Anzahl Legs pro Kombi.")

    def book_weight(self, bookmaker: str) -> float:
        """Gewicht eines Sharp-Buchs (case-insensitiv), mit Default-Fallback."""
        return self.sharp_book_weights.get(bookmaker.lower(), self.default_book_weight)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Gecachte Settings-Instanz (einmal pro Prozess laden)."""
    return Settings()
