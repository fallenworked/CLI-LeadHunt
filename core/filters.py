"""Фильтрация результатов поиска. Не скрывает ошибки источника."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from core.models import Lead
from core.utils import normalize_for_match


@dataclass
class FilterSpec:
    only_with_phone: bool = False
    require_address: bool = False
    include_website: bool = False
    keywords: str = ""
    lead_types: list[str] = field(default_factory=list)
    country_code: str = ""
    region: str = ""


def keyword_tokens(keywords: str) -> list[str]:
    return [
        token.strip()
        for token in re.split(r"[,;]+", keywords or "")
        if token.strip()
    ]


def _haystack(lead: Lead) -> str:
    extra = lead.extra or {}
    contacts = extra.get("contacts") or {}
    parts = [
        lead.name,
        lead.address,
        lead.city,
        lead.lead_type,
        lead.niche,
        lead.opening_hours,
        lead.email,
        extra.get("operator", ""),
        extra.get("brand", ""),
        extra.get("cuisine", ""),
        extra.get("description", ""),
        " ".join(str(value) for value in contacts.values()),
    ]
    return normalize_for_match(" ".join(str(part) for part in parts if part))


def apply_filters(leads: Iterable[Lead], spec: FilterSpec) -> tuple[list[Lead], dict[str, int]]:
    tokens = [normalize_for_match(token) for token in keyword_tokens(spec.keywords)]
    tokens = [token for token in tokens if token]
    reasons: dict[str, int] = {
        "Есть сайт": 0,
        "Нет телефона": 0,
        "Нет адреса": 0,
        "Не совпало по ключевым словам": 0,
        "Другой тип": 0,
        "Другой регион": 0,
    }
    result: list[Lead] = []

    for lead in leads:
        if not spec.include_website and lead.website:
            reasons["Есть сайт"] += 1
            continue
        if spec.only_with_phone and not lead.phone:
            reasons["Нет телефона"] += 1
            continue
        if spec.require_address and not lead.address:
            reasons["Нет адреса"] += 1
            continue
        if tokens:
            haystack = _haystack(lead)
            if not all(token in haystack for token in tokens):
                reasons["Не совпало по ключевым словам"] += 1
                continue
        if spec.lead_types and lead.lead_type not in spec.lead_types:
            reasons["Другой тип"] += 1
            continue
        if spec.country_code and lead.country_code.upper() != spec.country_code.upper():
            reasons["Другой регион"] += 1
            continue
        if spec.region and normalize_for_match(spec.region) not in normalize_for_match(
            f"{lead.city} {lead.region}"
        ):
            reasons["Другой регион"] += 1
            continue
        result.append(lead)

    return result, {key: value for key, value in reasons.items() if value}
