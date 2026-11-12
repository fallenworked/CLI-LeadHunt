"""Экспорт лидов в CSV (UTF-8 BOM, разделитель ; для Excel)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

from config import STATUSES
from exporters.common import lead_display_contacts, lead_map_url
from core.utils import clean_text, fmt_datetime


CSV_COLUMNS = [
    "Название",
    "Телефон",
    "Email",
    "Адрес",
    "Город",
    "Регион",
    "Страна",
    "Ниша",
    "Тип",
    "Часы работы",
    "Сайт",
    "Доп. контакты",
    "Широта",
    "Долгота",
    "Ссылка на карту",
    "Источник",
    "Статус",
    "Ключевые слова",
    "Дата обнаружения",
    "Заметки",
    "ID лида",
]


def export_csv(leads: Iterable[dict[str, Any]], path: str | Path, delimiter: str = ";") -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = list(leads)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(CSV_COLUMNS)
        for lead in rows:
            writer.writerow(
                [
                    clean_text(lead.get("name")),
                    clean_text(lead.get("phone")),
                    clean_text(lead.get("email")),
                    clean_text(lead.get("address")),
                    clean_text(lead.get("city")),
                    clean_text(lead.get("region")),
                    clean_text(lead.get("country")),
                    clean_text(lead.get("niche")),
                    clean_text(lead.get("lead_type")),
                    clean_text(lead.get("opening_hours")),
                    clean_text(lead.get("website")),
                    lead_display_contacts(lead),
                    lead.get("lat") if lead.get("lat") is not None else "",
                    lead.get("lon") if lead.get("lon") is not None else "",
                    lead_map_url(lead),
                    clean_text(lead.get("source")),
                    STATUSES.get(str(lead.get("status") or "new"), str(lead.get("status") or "")),
                    clean_text(lead.get("keywords")),
                    fmt_datetime(lead.get("found_at")),
                    clean_text(lead.get("notes")),
                    lead.get("id") or "",
                ]
            )
    return output
