"""Разбор ответов OpenStreetMap и построение Overpass-запросов.

Логика извлечения лидов перенесена из Lead Hunter (src/index.js):
  * берём только объекты с названием;
  * по умолчанию это бизнесы БЕЗ сайта;
  * телефон, email, адрес, часы работы и координаты читаются из OSM-тегов;
  * тип определяется по amenity / shop / office / healthcare / leisure / tourism.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from core.dictionaries import find_niche
from core.models import CityInfo, Lead
from core.utils import clean_text


def _tag(tags: dict[str, Any], *names: str) -> str:
    for name in names:
        value = tags.get(name)
        if value is not None and str(value).strip():
            return clean_text(value)
    return ""


def _extract_address(tags: dict[str, Any]) -> str:
    street = _tag(tags, "addr:street")
    number = _tag(tags, "addr:housenumber")
    place = _tag(tags, "addr:place")
    full = _tag(tags, "addr:full")
    if street:
        return " ".join(part for part in (street, number) if part)
    if place:
        return " ".join(part for part in (place, number) if part)
    return full


def _extract_type(tags: dict[str, Any]) -> str:
    for key in ("amenity", "shop", "office", "healthcare", "leisure", "tourism", "craft"):
        value = tags.get(key)
        if value:
            return clean_text(value)
    return ""


def _extract_contacts(tags: dict[str, Any]) -> dict[str, str]:
    mapping = {
        "vk": ("contact:vk", "vk"),
        "telegram": ("contact:telegram", "telegram"),
        "instagram": ("contact:instagram", "instagram"),
        "facebook": ("contact:facebook", "facebook"),
        "whatsapp": ("contact:whatsapp", "whatsapp"),
        "youtube": ("contact:youtube", "youtube"),
        "ok": ("contact:ok", "ok"),
    }
    contacts: dict[str, str] = {}
    for key, tag_names in mapping.items():
        value = _tag(tags, *tag_names)
        if value:
            contacts[key] = value
    return contacts


def element_to_lead(
    element: dict[str, Any],
    source: str,
    city: CityInfo,
    niche: str,
    keywords: str = "",
) -> Lead | None:
    tags = element.get("tags") or {}
    if not isinstance(tags, dict):
        return None
    name = _tag(tags, "name", "name:ru")
    if not name:
        return None

    element_type = str(element.get("type") or "node")
    element_id = str(element.get("id") or "")
    lat = element.get("lat")
    lon = element.get("lon")
    center = element.get("center") or {}
    if lat is None:
        lat = center.get("lat")
    if lon is None:
        lon = center.get("lon")

    website = _tag(tags, "website", "contact:website", "url")
    phone = _tag(tags, "phone", "contact:phone", "contact:mobile", "mobile")
    email = _tag(tags, "email", "contact:email")

    extra: dict[str, Any] = {}
    contacts = _extract_contacts(tags)
    if contacts:
        extra["contacts"] = contacts
    for key, tag_names in {
        "operator": ("operator",),
        "brand": ("brand",),
        "cuisine": ("cuisine",),
        "description": ("description",),
        "postcode": ("addr:postcode",),
        "district": ("addr:district",),
        "city_tag": ("addr:city",),
        "wikipedia": ("wikipedia",),
        "wikidata": ("wikidata",),
    }.items():
        value = _tag(tags, *tag_names)
        if value:
            extra[key] = value

    return Lead(
        source=source,
        source_id=f"{element_type}/{element_id}" if element_id else "",
        name=name,
        phone=phone,
        email=email,
        address=_extract_address(tags),
        city=city.name,
        region=city.region,
        country=city.country,
        country_code=city.country_code,
        niche=niche,
        keywords=keywords,
        lat=float(lat) if lat is not None else None,
        lon=float(lon) if lon is not None else None,
        opening_hours=_tag(tags, "opening_hours"),
        website=website,
        lead_type=_extract_type(tags),
        extra=extra,
    )


def parse_overpass_elements(
    elements: Iterable[dict[str, Any]],
    source: str,
    city: CityInfo,
    niche: str,
    keywords: str = "",
) -> list[Lead]:
    leads: list[Lead] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        lead = element_to_lead(element, source, city, niche, keywords)
        if lead is not None:
            leads.append(lead)
    return leads


def _escape_overpass_regex(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("/", "\\/")


def _bbox(city: CityInfo, radius: int) -> str:
    import math

    lat_delta = radius / 111_000
    lon_delta = radius / (111_000 * max(0.15, math.cos(city.lat * math.pi / 180)))
    south = city.lat - lat_delta
    north = city.lat + lat_delta
    west = city.lon - lon_delta
    east = city.lon + lon_delta
    return f"{south:.5f},{west:.5f},{north:.5f},{east:.5f}"


def build_overpass_query(
    city: CityInfo,
    niche: str,
    keywords: str = "",
    radius: int = 5000,
    limit: int = 250,
    timeout: int = 30,
) -> str:
    """Строит запрос так же, как рабочая версия, но с настраиваемым радиусом."""
    niche_obj = find_niche(niche)
    box = _bbox(city, radius)
    clauses: list[str] = []

    if niche_obj is not None:
        for key, value in niche_obj.tags:
            clauses.append(f'node["{key}"="{value}"]({box});')
            clauses.append(f'way["{key}"="{value}"]({box});')
    else:
        keyword = clean_text(niche or keywords)
        if not keyword:
            raise ValueError("нужна ниша или ключевое слово для поиска")
        pattern = _escape_overpass_regex(keyword)
        clauses.append(f'node["name"~"{pattern}",i]({box});')
        clauses.append(f'way["name"~"{pattern}",i]({box});')

    out_limit = max(100, min(1200, int(limit) * 3))
    joined = "".join(clauses)
    return (
        f"[out:json][timeout:{max(10, int(timeout))}];"
        f"({joined});"
        f"out center {out_limit};"
    )


def parse_query_metadata(query: str) -> dict[str, Any]:
    """Небольшая диагностическая информация для истории поиска."""
    limit_match = re.search(r"out center (\d+);", query)
    return {
        "query_length": len(query),
        "result_limit": int(limit_match.group(1)) if limit_match else None,
    }
