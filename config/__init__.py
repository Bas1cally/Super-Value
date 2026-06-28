"""Konfiguration (Pydantic-Settings, aus .env). Keine Magic Numbers im Code."""

from config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
