from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]


def setting(name: str, default: str) -> str:
    return os.getenv(name, default)


def db_path() -> Path:
    path = Path(setting("DB_PATH", "warehouse/football.duckdb"))
    return path if path.is_absolute() else ROOT / path


def season() -> str:
    return setting("SEASON", "2026")


def league() -> str:
    return setting("LEAGUE", "BRA").upper()


def simulations() -> int:
    return max(100, int(setting("SIMULATIONS", "20000")))


def relegation_spots() -> int:
    return max(1, int(setting("RELEGATION_SPOTS", "4")))
