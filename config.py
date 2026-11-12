"""Глобальная конфигурация Lead Hunter Local Edition."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "LEAD HUNTER"
APP_EDITION = "LOCAL EDITION"
VERSION = "2.0.0"
TAGLINE = "Каждый найденный лид — новая возможность"

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LH_DATA_DIR", ROOT_DIR / "data")).resolve()
RESULTS_DIR = Path(os.environ.get("LH_RESULTS_DIR", ROOT_DIR / "results")).resolve()
DB_PATH = Path(os.environ.get("LH_DB_PATH", DATA_DIR / "lead_hunter.db")).resolve()

USER_AGENT = f"LeadHunterLocal/{VERSION} (+local CLI; OSM Overpass client)"

DEFAULT_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

DEFAULT_SETTINGS: dict[str, object] = {
    "default_city": "Москва",
    "default_niche": "стоматология",
    "default_radius": 5000,
    "default_limit": 250,
    "default_only_phone": False,
    "default_require_address": False,
    "default_include_website": False,
    "request_timeout": 30,
    "min_request_interval": 1.2,
    "endpoints": DEFAULT_ENDPOINTS,
    "source_osm_enabled": True,
    "animations": True,
    "page_size": 15,
    "last_run": "",
}

STATUSES: dict[str, str] = {
    "new": "Новый",
    "contacted": "На связи",
    "interested": "Интерес",
    "proposal": "Предложение",
    "won": "Клиент",
    "rejected": "Отказ",
}

STATUS_STYLES: dict[str, str] = {
    "new": "lh.status.new",
    "contacted": "lh.status.contacted",
    "interested": "lh.status.interested",
    "proposal": "lh.status.proposal",
    "won": "lh.status.won",
    "rejected": "lh.status.rejected",
}


def configure_windows_console() -> None:
    """Включает UTF-8 и ANSI/VT в консоли Windows 10."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
        # Включаем virtual terminal processing, чтобы Rich мог рисовать цвета и рамки.
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        # Консоль может не поддерживать ANSI; Rich сам деградирует безопасно.
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
