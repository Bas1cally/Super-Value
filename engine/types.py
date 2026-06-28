"""Kopplungs-Typen zwischen Quellen, Storage und Engine.

Die Engine kennt keine Quellen-Details — die einzige Kopplung läuft über
``OddsRecord`` (bzw. die DB). Jede Quelle implementiert das ``OddsSource``-
Protokoll; weitere Buchmacher = nur eine neue Klasse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class OddsRecord:
    """Eine Dezimalquote für einen Ausgang, bei einem Buch, zu einem Zeitpunkt.

    Quoten als ``Decimal``. Jeder Record trägt einen ``ts`` — die Zeitreihe ist
    Pflicht für CLV.

    Attributes:
        event_id: kanonische Event-ID (nach Normalisierung).
        market_key: kanonischer Markt-Key (z. B. ``"1X2"``, ``"OVER_2.5"``).
        selection_key: kanonischer Ausgang (z. B. ``"home"``, ``"over"``).
        bookmaker: Quelle (``"pinnacle"``, ``"yeet"`` …).
        decimal_odds: Dezimalquote.
        ts: Erhebungszeitpunkt (UTC).
        is_sharp: True für Sharp-Referenzbücher (Pinnacle etc.), False für yeet.
    """

    event_id: str
    market_key: str
    selection_key: str
    bookmaker: str
    decimal_odds: Decimal
    ts: datetime
    is_sharp: bool = False


@runtime_checkable
class OddsSource(Protocol):
    """Gemeinsames Interface aller Quoten-Quellen.

    Die Engine bleibt quellen-agnostisch: sie sieht nur ``list[OddsRecord]``.
    """

    name: str

    async def fetch(self) -> list[OddsRecord]:
        """Hole aktuelle Quoten und gib sie normalisiert als Records zurück."""
        ...
