"""Геокодирование городов: словарь + Photon + Nominatim + локальный кеш.

Старый проект использовал Photon (photon.komoot.io) для городов вне словаря.
Здесь сохранён этот путь, добавлен резервный Nominatim и SQLite-кеш, чтобы
повторные поиски не зависели от сети.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import requests

from config import USER_AGENT
from core.dictionaries import CITIES, COUNTRIES, KnownCity, normalize_city
from core.models import CityInfo


class Geocoder:
    def __init__(self, storage=None, user_agent: str = USER_AGENT) -> None:
        self.storage = storage
        self.user_agent = user_agent
        self._lock = threading.Lock()
        self._last_nominatim = 0.0

    def resolve(self, query: str, radius: int = 5000, timeout: int = 25) -> CityInfo | None:
        raw = (query or "").strip()
        if not raw:
            return None
        normalized = normalize_city(raw)

        known = CITIES.get(normalized)
        if known is not None:
            return self._from_known(known, radius)

        if self.storage is not None:
            cached = self.storage.get_city_cache(normalized)
            if cached:
                cached.radius = radius
                return cached

        errors: list[str] = []
        city = self._resolve_photon(raw, radius, timeout, errors)
        if city is None:
            city = self._resolve_nominatim(raw, radius, timeout, errors)
        if city is not None and self.storage is not None:
            self.storage.save_city_cache(normalized, city)
        if city is not None:
            city.resolved_by = city.resolved_by or "photon"
        return city

    def _from_known(self, known: KnownCity, radius: int) -> CityInfo:
        return CityInfo(
            name=known.name,
            lat=known.lat,
            lon=known.lon,
            country_code=known.country_code,
            country=COUNTRIES.get(known.country_code, known.country_code),
            region="",
            radius=radius or known.radius,
            resolved_by="dictionary",
        )

    def _resolve_photon(
        self, query: str, radius: int, timeout: int, errors: list[str]
    ) -> CityInfo | None:
        try:
            response = requests.get(
                "https://photon.komoot.io/api/",
                params={"q": query, "limit": 1, "lang": "ru"},
                headers={"User-Agent": self.user_agent},
                timeout=timeout,
            )
            if response.status_code != 200:
                errors.append(f"Photon: HTTP {response.status_code}")
                return None
            data = response.json()
            features = data.get("features") or []
            if not features:
                errors.append("Photon: город не найден")
                return None
            feature = features[0]
            coordinates = (feature.get("geometry") or {}).get("coordinates") or []
            if len(coordinates) < 2:
                errors.append("Photon: нет координат")
                return None
            lon, lat = float(coordinates[0]), float(coordinates[1])
            props = feature.get("properties") or {}
            name = props.get("name") or query
            country_code = str(props.get("countrycode") or "XX").upper()
            country = str(props.get("country") or COUNTRIES.get(country_code, country_code))
            region = str(props.get("state") or props.get("county") or "")
            return CityInfo(
                name=str(name),
                lat=lat,
                lon=lon,
                country_code=country_code,
                country=country,
                region=region,
                radius=radius,
                resolved_by="photon",
            )
        except Exception as exc:  # noqa: BLE001 - источник может быть недоступен
            errors.append(f"Photon: {type(exc).__name__}")
            return None

    def _resolve_nominatim(
        self, query: str, radius: int, timeout: int, errors: list[str]
    ) -> CityInfo | None:
        # Публичный Nominatim требует не более одного запроса в секунду.
        with self._lock:
            wait = 1.1 - (time.monotonic() - self._last_nominatim)
            if wait > 0:
                time.sleep(wait)
            self._last_nominatim = time.monotonic()

        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": 1,
                    "addressdetails": 1,
                    "accept-language": "ru",
                },
                headers={"User-Agent": self.user_agent},
                timeout=timeout,
            )
            if response.status_code != 200:
                errors.append(f"Nominatim: HTTP {response.status_code}")
                return None
            data = response.json()
            if not data:
                errors.append("Nominatim: город не найден")
                return None
            item = data[0]
            address = item.get("address") or {}
            country_code = str(address.get("country_code") or "XX").upper()
            country = str(address.get("country") or COUNTRIES.get(country_code, country_code))
            region = str(address.get("state") or address.get("county") or "")
            name = (
                address.get("city")
                or address.get("town")
                or address.get("village")
                or address.get("municipality")
                or str(item.get("name") or query)
            )
            return CityInfo(
                name=str(name),
                lat=float(item["lat"]),
                lon=float(item["lon"]),
                country_code=country_code,
                country=country,
                region=region,
                radius=radius,
                resolved_by="nominatim",
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Nominatim: {type(exc).__name__}")
            return None


def city_info_from_dict(data: dict[str, Any]) -> CityInfo:
    return CityInfo.from_dict(data)
