"""Общие функции экспорта."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from core.utils import clean_text, fmt_datetime, map_links, sanitize_filename


def lead_display_contacts(lead: dict[str, Any]) -> str:
    extra = lead.get("extra") or {}
    contacts = extra.get("contacts") or {}
    parts = []
    for key, value in contacts.items():
        if value:
            parts.append(f"{key}: {value}")
    return "; ".join(parts)


def lead_status_label(lead: dict[str, Any]) -> str:
    from config import STATUSES

    return STATUSES.get(str(lead.get("status") or "new"), str(lead.get("status") or ""))


def lead_map_url(lead: dict[str, Any]) -> str:
    return map_links(lead).get("yandex_point") or map_links(lead)["yandex"]


def default_export_path(directory: Path, prefix: str, extension: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{sanitize_filename(prefix, 'leadhunter')}_{stamp}.{extension}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / name


def lead_search_text(lead: dict[str, Any]) -> str:
    parts = [
        lead.get("name"),
        lead.get("phone"),
        lead.get("email"),
        lead.get("address"),
        lead.get("city"),
        lead.get("niche"),
        lead.get("lead_type"),
        lead.get("opening_hours"),
        lead.get("website"),
        lead.get("source"),
        lead.get("notes"),
        lead_display_contacts(lead),
    ]
    return " ".join(clean_text(str(part)) for part in parts if part).lower()


def clean_phone_href(phone: str) -> str:
    value = re.sub(r"[^\d+]", "", phone or "")
    return value
