"""Оркестратор поиска: геокодирование → источники → фильтры → дедуп → SQLite."""

from __future__ import annotations

import logging
import time
from typing import Callable

from core.deduplicator import deduplicate
from core.filters import FilterSpec, apply_filters
from core.geocoder import Geocoder
from core.models import CityInfo, SearchOutcome, SearchParams, SearchStats
from core.parser import build_overpass_query
from core.settings import Settings
from database.storage import Storage
from sources.base import SourceCancelled
from sources.registry import build_sources

ProgressCallback = Callable[[dict], None]
logger = logging.getLogger("lead_hunter.engine")


class LeadEngine:
    def __init__(self, storage: Storage, settings: Settings, sources=None) -> None:
        self.storage = storage
        self.settings = settings
        self.geocoder = Geocoder(storage=storage)
        self._sources = sources

    def _get_sources(self):
        if self._sources is not None:
            return self._sources
        return build_sources(self.settings)

    def search(
        self,
        params: SearchParams,
        progress: ProgressCallback | None = None,
        cancel=None,
    ) -> SearchOutcome:
        emit = progress or (lambda event: None)
        started = time.monotonic()
        search_id = self.storage.create_search(params)
        logger.info(
            "Поиск #%s: город=%s, ниша=%s, радиус=%s, лимит=%s",
            search_id,
            params.city,
            params.niche,
            params.radius,
            params.limit,
        )
        stats = SearchStats()
        errors: list[str] = []
        notes: list[str] = []
        city: CityInfo | None = None
        query = ""
        status = "ok"
        leads: list = []

        try:
            emit(
                {
                    "type": "phase",
                    "phase": "resolve",
                    "message": f"Определяю координаты: {params.city}",
                }
            )
            city = self.geocoder.resolve(
                params.city,
                radius=params.radius,
                timeout=self.settings.get_int("request_timeout", 30),
            )
            if city is None:
                errors.append(
                    f"Город «{params.city}» не найден. Проверь название или попробуй ближайший крупный город."
                )
                status = "error"
                return self._finalize(
                    search_id, params, city, stats, errors, notes, query, status, started, leads
                )

            emit(
                {
                    "type": "resolved",
                    "city": city.to_dict(),
                    "message": (
                        f"{city.name}, {city.country}"
                        + (f" · {city.region}" if city.region else "")
                        + f" · {city.resolved_by}"
                    ),
                }
            )

            try:
                query = build_overpass_query(
                    city,
                    niche=params.niche,
                    keywords=params.keywords,
                    radius=params.radius,
                    limit=params.limit,
                    timeout=self.settings.get_int("request_timeout", 30),
                )
            except ValueError as exc:
                errors.append(str(exc))
                status = "error"
                return self._finalize(
                    search_id, params, city, stats, errors, notes, query, status, started, leads
                )

            sources = self._get_sources()
            if not sources:
                errors.append(
                    "Нет активных источников. Включи OpenStreetMap в разделе «Управление источниками»."
                )
                status = "error"
                return self._finalize(
                    search_id, params, city, stats, errors, notes, query, status, started, leads
                )

            raw_leads: list = []
            for source in sources:
                if cancel is not None and cancel.is_set():
                    raise SourceCancelled("поиск отменён пользователем")
                emit(
                    {
                        "type": "source_start",
                        "source_id": source.id,
                        "source": source.name,
                        "message": f"Источник: {source.name}",
                    }
                )
                source_started = time.monotonic()
                try:
                    result = source.search(city, params, progress=emit, cancel=cancel)
                    raw_leads.extend(result.leads)
                    stats.raw_found += len(result.leads)
                    notes.extend(result.warnings)
                    if result.query:
                        query = result.query
                    emit(
                        {
                            "type": "source_done",
                            "source_id": source.id,
                            "source": source.name,
                            "found": len(result.leads),
                            "raw_elements": result.raw_elements,
                            "elapsed_ms": result.elapsed_ms,
                            "message": (
                                f"{source.name}: {len(result.leads)} лидов "
                                f"за {result.elapsed_ms / 1000:.1f} с"
                            ),
                        }
                    )
                except SourceCancelled:
                    raise
                except Exception as exc:  # один источник не должен ронять всё приложение
                    message = str(exc) or type(exc).__name__
                    errors.append(f"{source.name}: {message}")
                    emit(
                        {
                            "type": "source_error",
                            "source_id": source.id,
                            "source": source.name,
                            "error": message,
                            "elapsed_ms": int((time.monotonic() - source_started) * 1000),
                            "message": f"Ошибка источника {source.name}: {message}",
                        }
                    )

            emit(
                {
                    "type": "phase",
                    "phase": "dedup",
                    "message": f"Удаляю дубликаты из {len(raw_leads)} записей",
                }
            )
            unique, within_duplicates = deduplicate(raw_leads)
            stats.after_dedup = len(unique)
            stats.duplicates = within_duplicates

            emit(
                {
                    "type": "phase",
                    "phase": "filter",
                    "message": "Применяю фильтры: сайт, телефон, адрес, ключевые слова",
                }
            )
            filtered, reasons = apply_filters(
                unique,
                FilterSpec(
                    only_with_phone=params.only_with_phone,
                    require_address=params.require_address,
                    include_website=params.include_website,
                    keywords=params.keywords,
                    country_code=params.country_code,
                    region=params.region,
                ),
            )
            stats.filter_reasons = reasons
            stats.filtered_out = max(0, len(unique) - len(filtered))
            if len(filtered) > params.limit:
                filtered = filtered[: params.limit]
            stats.with_phone = sum(1 for lead in filtered if lead.phone)
            stats.with_email = sum(1 for lead in filtered if lead.email)
            stats.with_address = sum(1 for lead in filtered if lead.address)

            if cancel is not None and cancel.is_set():
                raise SourceCancelled("поиск отменён пользователем")

            emit(
                {
                    "type": "phase",
                    "phase": "save",
                    "message": f"Сохраняю {len(filtered)} лидов в локальную базу",
                }
            )
            saved = self.storage.save_leads(search_id, filtered)
            stats.saved = saved["saved"]
            stats.new_leads = saved["new"]
            stats.duplicates += saved["duplicates"]
            leads = filtered
            status = "ok" if filtered else "empty"
            if errors and not filtered:
                status = "error"
            if not filtered and not errors:
                notes.append("Источник ответил, но подходящих лидов не найдено.")

            emit(
                {
                    "type": "done",
                    "found": stats.raw_found,
                    "saved": stats.saved,
                    "new": stats.new_leads,
                    "duplicates": stats.duplicates,
                    "message": "Поиск завершён",
                }
            )
        except SourceCancelled:
            status = "cancelled"
            errors.append("Поиск отменён пользователем.")
            emit({"type": "cancelled", "message": "Поиск отменён"})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected search failure")
            status = "error"
            errors.append(f"Внутренняя ошибка поиска: {type(exc).__name__}: {exc}")
            emit(
                {
                    "type": "fatal",
                    "error": f"{type(exc).__name__}: {exc}",
                    "message": "Внутренняя ошибка поиска",
                }
            )

        return self._finalize(
            search_id, params, city, stats, errors, notes, query, status, started, leads
        )

    def _finalize(
        self,
        search_id: int,
        params: SearchParams,
        city: CityInfo | None,
        stats: SearchStats,
        errors: list[str],
        notes: list[str],
        query: str,
        status: str,
        started: float,
        leads: list,
    ) -> SearchOutcome:
        duration_ms = int((time.monotonic() - started) * 1000)
        try:
            self.storage.finish_search(
                search_id,
                stats,
                errors,
                duration_ms,
                status,
                city=city,
                query=query,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось сохранить историю поиска")
        if errors:
            logger.warning("Поиск #%s завершён со статусом %s: %s", search_id, status, "; ".join(errors))
        else:
            logger.info(
                "Поиск #%s завершён: статус=%s, найдено=%s, новых=%s, дубликатов=%s, %.1f с",
                search_id,
                status,
                stats.raw_found,
                stats.new_leads,
                stats.duplicates,
                duration_ms / 1000,
            )
        return SearchOutcome(
            search_id=search_id,
            params=params,
            city_info=city,
            leads=leads,
            stats=stats,
            errors=errors,
            source_notes=notes,
            duration_ms=duration_ms,
            status=status,
            query=query,
        )
