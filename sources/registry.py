"""Реестр источников. Новые источники подключаются здесь, без правок UI."""

from __future__ import annotations

from config import DEFAULT_ENDPOINTS
from sources.osm_overpass import OverpassSource, test_endpoints

SOURCE_CATALOG = [
    {
        "id": "osm",
        "name": "OpenStreetMap / Overpass",
        "type": "Публичный API",
        "requires_key": False,
        "description": (
            "POI-объекты OpenStreetMap через публичные зеркала Overpass. "
            "Ключ не нужен, регистрация не нужна."
        ),
    }
]


def build_sources(settings) -> list:
    sources = []
    if settings.get_bool("source_osm_enabled", True):
        endpoints = settings.get_list("endpoints") or list(DEFAULT_ENDPOINTS)
        sources.append(
            OverpassSource(
                endpoints=endpoints,
                timeout=settings.get_int("request_timeout", 30),
                min_interval=float(settings.get("min_request_interval", 1.2)),
            )
        )
    return sources


def get_catalog_item(source_id: str) -> dict | None:
    return next((item for item in SOURCE_CATALOG if item["id"] == source_id), None)
