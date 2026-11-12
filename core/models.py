"""Модели данных, общие для поиска, хранения и экспорта."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CityInfo:
    name: str
    lat: float
    lon: float
    country_code: str = "XX"
    country: str = "Мир"
    region: str = ""
    radius: int = 5000
    resolved_by: str = "dictionary"  # dictionary | cache | photon | nominatim

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "country_code": self.country_code,
            "country": self.country,
            "region": self.region,
            "radius": self.radius,
            "resolved_by": self.resolved_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CityInfo":
        return cls(
            name=str(data.get("name", "")),
            lat=float(data.get("lat", 0)),
            lon=float(data.get("lon", 0)),
            country_code=str(data.get("country_code", "XX")),
            country=str(data.get("country", "Мир")),
            region=str(data.get("region", "")),
            radius=int(data.get("radius", 5000)),
            resolved_by=str(data.get("resolved_by", "cache")),
        )


@dataclass
class SearchParams:
    city: str
    niche: str
    category_key: str = ""
    keywords: str = ""
    radius: int = 5000
    limit: int = 250
    only_with_phone: bool = False
    require_address: bool = False
    include_website: bool = False
    source_ids: list[str] = field(default_factory=lambda: ["osm"])
    region: str = ""
    country_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "city": self.city,
            "niche": self.niche,
            "category_key": self.category_key,
            "keywords": self.keywords,
            "radius": self.radius,
            "limit": self.limit,
            "only_with_phone": self.only_with_phone,
            "require_address": self.require_address,
            "include_website": self.include_website,
            "source_ids": list(self.source_ids),
            "region": self.region,
            "country_code": self.country_code,
        }


@dataclass
class Lead:
    source: str
    source_id: str
    name: str
    phone: str = ""
    email: str = ""
    address: str = ""
    city: str = ""
    region: str = ""
    country: str = ""
    country_code: str = ""
    niche: str = ""
    keywords: str = ""
    lat: float | None = None
    lon: float | None = None
    opening_hours: str = ""
    website: str = ""
    lead_type: str = ""
    status: str = "new"
    notes: str = ""
    found_at: str = ""
    last_seen_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""
    db_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_id": self.source_id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "city": self.city,
            "region": self.region,
            "country": self.country,
            "country_code": self.country_code,
            "niche": self.niche,
            "keywords": self.keywords,
            "lat": self.lat,
            "lon": self.lon,
            "opening_hours": self.opening_hours,
            "website": self.website,
            "lead_type": self.lead_type,
            "status": self.status,
            "notes": self.notes,
            "found_at": self.found_at,
            "last_seen_at": self.last_seen_at,
            "extra": self.extra,
            "fingerprint": self.fingerprint,
        }


@dataclass
class SearchStats:
    raw_found: int = 0
    after_dedup: int = 0
    filtered_out: int = 0
    saved: int = 0
    new_leads: int = 0
    duplicates: int = 0
    with_phone: int = 0
    with_email: int = 0
    with_address: int = 0
    filter_reasons: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_found": self.raw_found,
            "after_dedup": self.after_dedup,
            "filtered_out": self.filtered_out,
            "saved": self.saved,
            "new_leads": self.new_leads,
            "duplicates": self.duplicates,
            "with_phone": self.with_phone,
            "with_email": self.with_email,
            "with_address": self.with_address,
            "filter_reasons": self.filter_reasons,
        }


@dataclass
class SearchOutcome:
    search_id: int
    params: SearchParams
    city_info: CityInfo | None
    leads: list[Lead] = field(default_factory=list)
    stats: SearchStats = field(default_factory=SearchStats)
    errors: list[str] = field(default_factory=list)
    source_notes: list[str] = field(default_factory=list)
    duration_ms: int = 0
    status: str = "ok"
    query: str = ""

    @property
    def ok(self) -> bool:
        return self.status in {"ok", "empty"} and not self.errors

    @property
    def total(self) -> int:
        return len(self.leads)
