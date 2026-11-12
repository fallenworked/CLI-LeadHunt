"""Дедупликация лидов внутри поиска и между разными поисками."""

from __future__ import annotations

import hashlib
from typing import Iterable

from core.models import Lead
from core.utils import normalize_for_match, normalize_phone


def lead_key(lead: Lead) -> str:
    """Стабильный ключ бизнеса: название + координаты / телефон / адрес."""
    name = normalize_for_match(lead.name) or "без-названия"
    phone = normalize_phone(lead.phone)
    address = normalize_for_match(lead.address)
    city = normalize_for_match(lead.city)

    if lead.lat is not None and lead.lon is not None:
        # 3 знака после запятой — примерно 100 метров. Так же делала старая версия.
        return f"{name}|geo:{lead.lat:.3f},{lead.lon:.3f}"
    if phone:
        return f"{name}|phone:{phone}"
    if address:
        return f"{name}|addr:{address}|{city}"
    return f"{name}|city:{city}"


def fingerprint(lead: Lead) -> str:
    return hashlib.sha1(lead_key(lead).encode("utf-8")).hexdigest()


def _merge_missing(target: Lead, source: Lead) -> None:
    for field_name in (
        "phone",
        "email",
        "address",
        "opening_hours",
        "website",
        "lead_type",
        "country",
        "country_code",
        "region",
        "city",
        "niche",
        "keywords",
    ):
        if not getattr(target, field_name) and getattr(source, field_name):
            setattr(target, field_name, getattr(source, field_name))
    if target.lat is None and source.lat is not None:
        target.lat = source.lat
    if target.lon is None and source.lon is not None:
        target.lon = source.lon
    if source.extra:
        target.extra = {**source.extra, **target.extra}
        contacts = {**(source.extra.get("contacts") or {}), **(target.extra.get("contacts") or {})}
        if contacts:
            target.extra["contacts"] = contacts


def deduplicate(leads: Iterable[Lead]) -> tuple[list[Lead], int]:
    """Возвращает уникальные лиды и число отброшенных дубликатов."""
    unique: dict[str, Lead] = {}
    duplicates = 0
    for lead in leads:
        key = lead_key(lead)
        existing = unique.get(key)
        if existing is None:
            lead.fingerprint = hashlib.sha1(key.encode("utf-8")).hexdigest()
            unique[key] = lead
        else:
            duplicates += 1
            _merge_missing(existing, lead)
    return list(unique.values()), duplicates
