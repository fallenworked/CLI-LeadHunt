"""Локальное хранилище Lead Hunter на SQLite.

Все данные лежат в data/lead_hunter.db. Никаких серверов, аккаунтов и D1.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from core.deduplicator import fingerprint as make_fingerprint
from core.models import CityInfo, Lead, SearchParams, SearchStats
from core.utils import (
    clean_text,
    now_iso,
    normalize_for_match,
    parse_iso,
    safe_json_dumps,
    safe_json_loads,
    today_iso,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    source_id TEXT DEFAULT '',
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    email TEXT DEFAULT '',
    address TEXT DEFAULT '',
    city TEXT DEFAULT '',
    region TEXT DEFAULT '',
    country TEXT DEFAULT '',
    country_code TEXT DEFAULT '',
    niche TEXT DEFAULT '',
    keywords TEXT DEFAULT '',
    lat REAL,
    lon REAL,
    opening_hours TEXT DEFAULT '',
    website TEXT DEFAULT '',
    lead_type TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',
    notes TEXT DEFAULT '',
    found_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    extra TEXT DEFAULT '{}',
    search_blob TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_leads_city ON leads(city);
CREATE INDEX IF NOT EXISTS idx_leads_niche ON leads(niche);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_found ON leads(found_at);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);

CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT DEFAULT '',
    city TEXT DEFAULT '',
    region TEXT DEFAULT '',
    country TEXT DEFAULT '',
    country_code TEXT DEFAULT '',
    niche TEXT DEFAULT '',
    category_key TEXT DEFAULT '',
    keywords TEXT DEFAULT '',
    radius INTEGER DEFAULT 5000,
    limit_value INTEGER DEFAULT 250,
    params TEXT DEFAULT '{}',
    total_found INTEGER DEFAULT 0,
    after_dedup INTEGER DEFAULT 0,
    filtered_out INTEGER DEFAULT 0,
    new_leads INTEGER DEFAULT 0,
    duplicates INTEGER DEFAULT 0,
    saved INTEGER DEFAULT 0,
    with_phone INTEGER DEFAULT 0,
    with_email INTEGER DEFAULT 0,
    errors TEXT DEFAULT '[]',
    query TEXT DEFAULT '',
    duration_ms INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_searches_created ON searches(created_at);

CREATE TABLE IF NOT EXISTS search_leads (
    search_id INTEGER NOT NULL,
    lead_id INTEGER NOT NULL,
    PRIMARY KEY (search_id, lead_id),
    FOREIGN KEY (search_id) REFERENCES searches(id) ON DELETE CASCADE,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS city_cache (
    query TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    country_code TEXT DEFAULT 'XX',
    country TEXT DEFAULT '',
    region TEXT DEFAULT '',
    updated_at TEXT NOT NULL
);
"""


class Storage:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=20, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=15000")
        self.init_schema()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def init_schema(self) -> None:
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------------ settings
    def get_setting(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ city cache
    def get_city_cache(self, query: str) -> CityInfo | None:
        row = self.conn.execute("SELECT * FROM city_cache WHERE query = ?", (query,)).fetchone()
        if row is None:
            return None
        return CityInfo(
            name=str(row["name"]),
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            country_code=str(row["country_code"]),
            country=str(row["country"]),
            region=str(row["region"]),
            radius=5000,
            resolved_by="cache",
        )

    def save_city_cache(self, query: str, city: CityInfo) -> None:
        self.conn.execute(
            "INSERT INTO city_cache(query, name, lat, lon, country_code, country, region, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(query) DO UPDATE SET name=excluded.name, lat=excluded.lat, lon=excluded.lon, "
            "country_code=excluded.country_code, country=excluded.country, region=excluded.region, "
            "updated_at=excluded.updated_at",
            (
                query,
                city.name,
                city.lat,
                city.lon,
                city.country_code,
                city.country,
                city.region,
                now_iso(),
            ),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ searches
    def create_search(self, params: SearchParams) -> int:
        cursor = self.conn.execute(
            "INSERT INTO searches(source, city, niche, category_key, keywords, radius, limit_value, "
            "params, status, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ",".join(params.source_ids),
                params.city,
                params.niche,
                params.category_key,
                params.keywords,
                params.radius,
                params.limit,
                safe_json_dumps(params.to_dict()),
                "running",
                now_iso(),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def finish_search(
        self,
        search_id: int,
        stats: SearchStats,
        errors: Iterable[str],
        duration_ms: int,
        status: str,
        city: CityInfo | None = None,
        query: str = "",
    ) -> None:
        error_list = [str(item) for item in errors]
        if city is not None:
            self.conn.execute(
                "UPDATE searches SET city=?, region=?, country=?, country_code=?, "
                "total_found=?, after_dedup=?, filtered_out=?, new_leads=?, duplicates=?, "
                "saved=?, with_phone=?, with_email=?, errors=?, query=?, duration_ms=?, status=? "
                "WHERE id=?",
                (
                    city.name,
                    city.region,
                    city.country,
                    city.country_code,
                    stats.raw_found,
                    stats.after_dedup,
                    stats.filtered_out,
                    stats.new_leads,
                    stats.duplicates,
                    stats.saved,
                    stats.with_phone,
                    stats.with_email,
                    safe_json_dumps(error_list),
                    query,
                    int(duration_ms),
                    status,
                    search_id,
                ),
            )
        else:
            self.conn.execute(
                "UPDATE searches SET total_found=?, after_dedup=?, filtered_out=?, new_leads=?, "
                "duplicates=?, saved=?, with_phone=?, with_email=?, errors=?, query=?, "
                "duration_ms=?, status=? WHERE id=?",
                (
                    stats.raw_found,
                    stats.after_dedup,
                    stats.filtered_out,
                    stats.new_leads,
                    stats.duplicates,
                    stats.saved,
                    stats.with_phone,
                    stats.with_email,
                    safe_json_dumps(error_list),
                    query,
                    int(duration_ms),
                    status,
                    search_id,
                ),
            )
        self.conn.commit()

    # ------------------------------------------------------------------ leads
    @staticmethod
    def _blob_from_values(data: Any) -> str:
        return normalize_for_match(
            " ".join(
                str(part)
                for part in (
                    data.get("name"),
                    data.get("phone"),
                    data.get("email"),
                    data.get("address"),
                    data.get("city"),
                    data.get("region"),
                    data.get("niche"),
                    data.get("lead_type"),
                    data.get("keywords"),
                    data.get("notes"),
                )
                if part
            )
        )

    def _lead_blob(self, lead: Lead) -> str:
        return self._blob_from_values(
            {
                "name": lead.name,
                "phone": lead.phone,
                "email": lead.email,
                "address": lead.address,
                "city": lead.city,
                "region": lead.region,
                "niche": lead.niche,
                "lead_type": lead.lead_type,
                "keywords": lead.keywords,
                "notes": lead.notes,
            }
        )

    def save_leads(self, search_id: int, leads: list[Lead]) -> dict[str, int]:
        """Сохраняет лиды, обновляет дубликаты и связывает их с поиском."""
        now = now_iso()
        new_count = 0
        duplicate_count = 0
        with self.conn:
            for lead in leads:
                if not lead.fingerprint:
                    lead.fingerprint = make_fingerprint(lead)
                if not lead.found_at:
                    lead.found_at = now
                lead.last_seen_at = now
                blob = self._lead_blob(lead)
                existing = self.conn.execute(
                    "SELECT * FROM leads WHERE fingerprint = ?", (lead.fingerprint,)
                ).fetchone()
                if existing is None:
                    cursor = self.conn.execute(
                        "INSERT INTO leads(fingerprint, source, source_id, name, phone, email, address, "
                        "city, region, country, country_code, niche, keywords, lat, lon, opening_hours, "
                        "website, lead_type, status, notes, found_at, last_seen_at, extra, search_blob) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            lead.fingerprint,
                            lead.source,
                            lead.source_id,
                            lead.name,
                            lead.phone,
                            lead.email,
                            lead.address,
                            lead.city,
                            lead.region,
                            lead.country,
                            lead.country_code,
                            lead.niche,
                            lead.keywords,
                            lead.lat,
                            lead.lon,
                            lead.opening_hours,
                            lead.website,
                            lead.lead_type,
                            lead.status,
                            lead.notes,
                            lead.found_at,
                            lead.last_seen_at,
                            safe_json_dumps(lead.extra),
                            blob,
                        ),
                    )
                    lead.db_id = int(cursor.lastrowid)
                    new_count += 1
                else:
                    duplicate_count += 1
                    lead.db_id = int(existing["id"])
                    self._update_existing_lead(existing, lead, now)
                self.conn.execute(
                    "INSERT OR IGNORE INTO search_leads(search_id, lead_id) VALUES(?, ?)",
                    (search_id, lead.db_id),
                )
        return {
            "new": new_count,
            "duplicates": duplicate_count,
            "saved": len(leads),
        }

    def _update_existing_lead(self, existing: sqlite3.Row, lead: Lead, now: str) -> None:
        updates: dict[str, Any] = {"last_seen_at": now}
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
        ):
            if not clean_text(existing[field_name]) and getattr(lead, field_name):
                updates[field_name] = getattr(lead, field_name)
        existing_extra = safe_json_loads(existing["extra"], {}) or {}
        if not isinstance(existing_extra, dict):
            existing_extra = {}
        merged_extra = {**lead.extra, **existing_extra}
        existing_contacts = existing_extra.get("contacts") or {}
        new_contacts = lead.extra.get("contacts") or {}
        if existing_contacts or new_contacts:
            merged_extra["contacts"] = {**new_contacts, **existing_contacts}
        updates["extra"] = safe_json_dumps(merged_extra)
        updates["search_blob"] = self._blob_from_values({**dict(existing), **updates})
        # Обновляем только недостающие поля, статус и заметки пользователя не трогаем.
        assignments = ", ".join(f"{key} = ?" for key in updates)
        self.conn.execute(
            f"UPDATE leads SET {assignments} WHERE id = ?",
            (*updates.values(), existing["id"]),
        )

    def _row_to_lead(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        extra = safe_json_loads(data.get("extra"), {})
        data["extra"] = extra if isinstance(extra, dict) else {}
        return data

    @staticmethod
    def _build_where(filters: dict[str, Any] | None) -> tuple[str, list[Any]]:
        filters = filters or {}
        clauses: list[str] = []
        params: list[Any] = []

        def add(clause: str, *values: Any) -> None:
            clauses.append(clause)
            params.extend(values)

        query = clean_text(filters.get("query", ""))
        if query:
            add("search_blob LIKE ?", f"%{normalize_for_match(query)}%")
        for key in ("city", "niche", "status", "source", "country_code", "region"):
            value = filters.get(key)
            if value:
                add(f"{key} = ?", value)
        if filters.get("has_phone"):
            add("phone != ''")
        if filters.get("has_email"):
            add("email != ''")
        if filters.get("has_website"):
            add("website != ''")
        search_id = filters.get("search_id")
        if search_id:
            add(
                "id IN (SELECT lead_id FROM search_leads WHERE search_id = ?)",
                int(search_id),
            )
        if filters.get("ids"):
            ids = [int(item) for item in filters["ids"]]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                add(f"id IN ({placeholders})", *ids)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    def list_leads(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
        order: str = "found_at DESC, id DESC",
    ) -> list[dict[str, Any]]:
        where, params = self._build_where(filters)
        sql = f"SELECT * FROM leads{where} ORDER BY {order} LIMIT ? OFFSET ?"
        rows = self.conn.execute(sql, (*params, int(limit), int(offset))).fetchall()
        return [self._row_to_lead(row) for row in rows]

    def count_leads(self, filters: dict[str, Any] | None = None) -> int:
        where, params = self._build_where(filters)
        row = self.conn.execute(f"SELECT COUNT(*) AS cnt FROM leads{where}", params).fetchone()
        return int(row["cnt"] if row else 0)

    def get_lead(self, lead_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM leads WHERE id = ?", (int(lead_id),)).fetchone()
        return self._row_to_lead(row) if row else None

    def update_lead_status(self, lead_id: int, status: str) -> None:
        self.conn.execute("UPDATE leads SET status = ? WHERE id = ?", (status, int(lead_id)))
        self.conn.commit()

    def update_lead_notes(self, lead_id: int, notes: str) -> None:
        row = self.conn.execute("SELECT * FROM leads WHERE id = ?", (int(lead_id),)).fetchone()
        if row is None:
            return
        data = dict(row)
        data["notes"] = notes
        self.conn.execute(
            "UPDATE leads SET notes = ?, search_blob = ? WHERE id = ?",
            (notes, self._blob_from_values(data), int(lead_id)),
        )
        self.conn.commit()

    def delete_lead(self, lead_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM search_leads WHERE lead_id = ?", (int(lead_id),))
            self.conn.execute("DELETE FROM leads WHERE id = ?", (int(lead_id),))

    # ------------------------------------------------------------------ history
    def _row_to_search(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        params = safe_json_loads(data.get("params"), {})
        errors = safe_json_loads(data.get("errors"), [])
        data["params"] = params if isinstance(params, dict) else {}
        data["errors"] = errors if isinstance(errors, list) else []
        return data

    def list_searches(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM searches ORDER BY created_at DESC, id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return [self._row_to_search(row) for row in rows]

    def get_search(self, search_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM searches WHERE id = ?", (int(search_id),)).fetchone()
        return self._row_to_search(row) if row else None

    def delete_search(self, search_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM search_leads WHERE search_id = ?", (int(search_id),))
            self.conn.execute("DELETE FROM searches WHERE id = ?", (int(search_id),))

    def clear_history(self) -> int:
        with self.conn:
            count = int(self.conn.execute("SELECT COUNT(*) AS cnt FROM searches").fetchone()["cnt"])
            self.conn.execute("DELETE FROM search_leads")
            self.conn.execute("DELETE FROM searches")
        return count

    def clear_leads(self) -> int:
        with self.conn:
            count = int(self.conn.execute("SELECT COUNT(*) AS cnt FROM leads").fetchone()["cnt"])
            self.conn.execute("DELETE FROM search_leads")
            self.conn.execute("DELETE FROM leads")
        return count

    def clear_all(self) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM search_leads")
            self.conn.execute("DELETE FROM leads")
            self.conn.execute("DELETE FROM searches")
            self.conn.execute("DELETE FROM city_cache")

    # ------------------------------------------------------------------ statistics
    def stats(self) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN phone != '' THEN 1 ELSE 0 END) AS with_phone, "
            "SUM(CASE WHEN email != '' THEN 1 ELSE 0 END) AS with_email, "
            "SUM(CASE WHEN website != '' THEN 1 ELSE 0 END) AS with_website, "
            "COUNT(DISTINCT NULLIF(city, '')) AS cities, "
            "COUNT(DISTINCT NULLIF(niche, '')) AS niches "
            "FROM leads"
        ).fetchone()
        searches = self.conn.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN status IN ('ok','empty') THEN 1 ELSE 0 END) AS completed, "
            "SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS failed, "
            "SUM(total_found) AS found_total, "
            "SUM(new_leads) AS new_total, "
            "MAX(created_at) AS last_search "
            "FROM searches"
        ).fetchone()
        today = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM searches WHERE substr(created_at, 1, 10) = ?",
            (today_iso(),),
        ).fetchone()
        status_rows = self.conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM leads GROUP BY status"
        ).fetchall()
        return {
            "total": int(row["total"] or 0),
            "with_phone": int(row["with_phone"] or 0),
            "with_email": int(row["with_email"] or 0),
            "with_website": int(row["with_website"] or 0),
            "cities": int(row["cities"] or 0),
            "niches": int(row["niches"] or 0),
            "searches": int(searches["total"] or 0),
            "completed_searches": int(searches["completed"] or 0),
            "failed_searches": int(searches["failed"] or 0),
            "found_total": int(searches["found_total"] or 0),
            "new_total": int(searches["new_total"] or 0),
            "last_search": searches["last_search"] or "",
            "today_searches": int(today["cnt"] or 0),
            "status_counts": {str(item["status"]): int(item["cnt"]) for item in status_rows},
        }

    def top_cities(self, limit: int = 10) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT city, COUNT(*) AS cnt FROM leads WHERE city != '' "
            "GROUP BY city ORDER BY cnt DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [(str(row["city"]), int(row["cnt"])) for row in rows]

    def top_niches(self, limit: int = 10) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT niche, COUNT(*) AS cnt FROM leads WHERE niche != '' "
            "GROUP BY niche ORDER BY cnt DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [(str(row["niche"]), int(row["cnt"])) for row in rows]

    def weekly_searches(self, days: int = 7) -> list[tuple[str, int]]:
        start = datetime.now().astimezone().date() - timedelta(days=days - 1)
        rows = self.conn.execute(
            "SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS cnt FROM searches "
            "WHERE substr(created_at, 1, 10) >= ? GROUP BY day",
            (start.isoformat(),),
        ).fetchall()
        found = {str(row["day"]): int(row["cnt"]) for row in rows}
        return [
            ((start + timedelta(days=index)).isoformat(), found.get((start + timedelta(days=index)).isoformat(), 0))
            for index in range(days)
        ]

    def distinct_values(self, column: str) -> list[str]:
        if column not in {"city", "niche", "status", "source", "country_code", "region"}:
            raise ValueError(f"Недопустимая колонка: {column}")
        rows = self.conn.execute(
            f"SELECT DISTINCT {column} AS value FROM leads WHERE {column} != '' ORDER BY value"
        ).fetchall()
        return [str(row["value"]) for row in rows]

    def last_search(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM searches ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
        return self._row_to_search(row) if row else None

    # ------------------------------------------------------------------ maintenance
    def vacuum(self) -> None:
        self.conn.execute("VACUUM")
        self.conn.commit()

    def db_size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def export_counts(self) -> dict[str, Any]:
        return {
            "leads": self.count_leads(),
            "searches": len(self.list_searches(100000)),
            "size": self.db_size(),
        }
