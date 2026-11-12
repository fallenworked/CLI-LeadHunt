"""Небольшие утилиты без внешних зависимостей."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today_iso() -> str:
    return datetime.now().astimezone().date().isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed
    except (TypeError, ValueError):
        return None


def fmt_datetime(value: str | None, fmt: str = "%d.%m.%Y %H:%M") -> str:
    parsed = parse_iso(value)
    if not parsed:
        return "—"
    return parsed.strftime(fmt)


def fmt_relative(value: str | None) -> str:
    parsed = parse_iso(value)
    if not parsed:
        return "—"
    delta = datetime.now().astimezone() - parsed
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "только что"
    if seconds < 3600:
        return f"{seconds // 60} мин назад"
    if seconds < 86400:
        return f"{seconds // 3600} ч назад"
    if seconds < 86400 * 7:
        return f"{seconds // 86400} дн назад"
    return parsed.strftime("%d.%m.%Y")


def human_duration(milliseconds: int | float) -> str:
    total = max(0.0, float(milliseconds) / 1000)
    if total < 1:
        return f"{int(total * 1000)} мс"
    if total < 60:
        return f"{total:.1f} с"
    minutes = int(total // 60)
    seconds = int(total % 60)
    return f"{minutes} мин {seconds} с"


def human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or unit == "ГБ":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} Б"


def sanitize_filename(value: str, fallback: str = "leads") -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    value = re.sub(r"\s+", "_", value)
    return (value or fallback)[:80]


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\u00a0", " ").split())


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return digits


def normalize_for_match(value: str) -> str:
    text = (value or "").lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def map_links(lead: dict) -> dict[str, str]:
    name = clean_text(lead.get("name", ""))
    city = clean_text(lead.get("city", ""))
    address = clean_text(lead.get("address", ""))
    query_text = " ".join(part for part in (name, address, city) if part)
    encoded = quote(query_text)
    links = {
        "yandex": f"https://yandex.ru/maps/?text={encoded}",
        "2gis": f"https://2gis.ru/search/{encoded}",
        "osm": f"https://www.openstreetmap.org/search?query={encoded}",
    }
    lat, lon = lead.get("lat"), lead.get("lon")
    if lat is not None and lon is not None:
        links["yandex_point"] = f"https://yandex.ru/maps/?pt={lon},{lat}&z=17"
        links["osm_point"] = (
            f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"
        )
    return links


def safe_json_loads(value: str | None, default: object = None) -> object:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def safe_json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def truncate(value: str, width: int) -> str:
    value = clean_text(value)
    if len(value) <= width:
        return value
    return value[: max(0, width - 1)].rstrip() + "…"


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
