"""OpenStreetMap / Overpass API — единственный рабочий источник старого проекта.

Алгоритм сохранён: несколько публичных зеркал опрашиваются параллельно, берётся
первое с непустым ответом. Мы не обходим ограничения источников: соблюдаем
User-Agent, таймауты и минимальный интервал между поисками.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from config import DEFAULT_ENDPOINTS, USER_AGENT
from core.models import CityInfo, Lead, SearchParams
from core.parser import build_overpass_query, parse_overpass_elements
from sources.base import ProgressCallback, SourceCancelled, SourceError, SourceResult

TEST_QUERY = (
    '[out:json][timeout:12];node["amenity"="cafe"]'
    "(55.7500,37.6100,55.7600,37.6200);out center 1;"
)


@dataclass
class MirrorOutcome:
    endpoint: str
    ok: bool
    elements: list[dict[str, Any]]
    error: str = ""
    latency_ms: int = 0
    remark: str = ""


class OverpassSource:
    id = "osm"
    name = "OpenStreetMap / Overpass"
    description = (
        "Публичные POI OpenStreetMap. Без API-ключа. Ищет бизнесы без сайта "
        "по нишам и ключевым словам."
    )
    requires_key = False

    def __init__(
        self,
        endpoints: list[str] | None = None,
        timeout: int = 30,
        min_interval: float = 1.2,
        user_agent: str = USER_AGENT,
    ) -> None:
        self.endpoints = [endpoint.strip() for endpoint in (endpoints or DEFAULT_ENDPOINTS) if endpoint.strip()]
        self.timeout = max(10, int(timeout))
        self.min_interval = max(0.0, float(min_interval))
        self.user_agent = user_agent
        self._rate_lock = threading.Lock()
        self._last_request = 0.0

    def _wait_rate_limit(self) -> None:
        with self._rate_lock:
            wait = self.min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    def _fetch_mirror(
        self,
        endpoint: str,
        query: str,
        results: "queue.Queue[MirrorOutcome]",
    ) -> None:
        started = time.monotonic()
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                headers={
                    "User-Agent": self.user_agent,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=self.timeout,
            )
            latency = int((time.monotonic() - started) * 1000)
            if response.status_code != 200:
                results.put(
                    MirrorOutcome(
                        endpoint=endpoint,
                        ok=False,
                        elements=[],
                        error=f"HTTP {response.status_code}",
                        latency_ms=latency,
                    )
                )
                return
            try:
                data = response.json()
            except ValueError:
                results.put(
                    MirrorOutcome(
                        endpoint=endpoint,
                        ok=False,
                        elements=[],
                        error="ответ не является JSON",
                        latency_ms=latency,
                    )
                )
                return
            elements = data.get("elements")
            if not isinstance(elements, list):
                results.put(
                    MirrorOutcome(
                        endpoint=endpoint,
                        ok=False,
                        elements=[],
                        error="в ответе нет elements",
                        latency_ms=latency,
                    )
                )
                return
            results.put(
                MirrorOutcome(
                    endpoint=endpoint,
                    ok=True,
                    elements=elements,
                    latency_ms=latency,
                    remark=str(data.get("remark") or ""),
                )
            )
        except requests.exceptions.Timeout:
            results.put(
                MirrorOutcome(
                    endpoint=endpoint,
                    ok=False,
                    elements=[],
                    error=f"таймаут {self.timeout} с",
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
            )
        except requests.exceptions.RequestException as exc:
            results.put(
                MirrorOutcome(
                    endpoint=endpoint,
                    ok=False,
                    elements=[],
                    error=f"{type(exc).__name__}: {str(exc)[:120]}",
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.put(
                MirrorOutcome(
                    endpoint=endpoint,
                    ok=False,
                    elements=[],
                    error=f"{type(exc).__name__}: {str(exc)[:120]}",
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
            )

    def search(
        self,
        city: CityInfo,
        params: SearchParams,
        progress: ProgressCallback | None = None,
        cancel=None,
    ) -> SourceResult:
        if not self.endpoints:
            raise SourceError("не задано ни одного зеркала Overpass")

        progress = progress or (lambda event: None)
        started = time.monotonic()
        query = build_overpass_query(
            city,
            niche=params.niche,
            keywords=params.keywords,
            radius=params.radius,
            limit=params.limit,
            timeout=self.timeout,
        )
        progress(
            {
                "type": "phase",
                "phase": "query",
                "message": f"Запрос к Overpass сформирован · {len(self.endpoints)} зеркал",
                "query": query,
            }
        )
        for endpoint in self.endpoints:
            progress(
                {
                    "type": "mirror",
                    "source": self.name,
                    "endpoint": endpoint,
                    "status": "pending",
                    "message": "ожидание",
                }
            )

        self._wait_rate_limit()
        outcome_queue: "queue.Queue[MirrorOutcome]" = queue.Queue()
        threads: list[threading.Thread] = []
        for endpoint in self.endpoints:
            thread = threading.Thread(
                target=self._fetch_mirror,
                args=(endpoint, query, outcome_queue),
                daemon=True,
                name=f"overpass-{urlparse(endpoint).netloc}",
            )
            thread.start()
            threads.append(thread)

        outcomes: list[MirrorOutcome] = []
        winner: MirrorOutcome | None = None
        deadline = time.monotonic() + self.timeout + 3
        while len(outcomes) < len(threads):
            if cancel is not None and cancel.is_set():
                raise SourceCancelled("поиск отменён пользователем")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                outcome = outcome_queue.get(timeout=min(0.25, remaining))
            except queue.Empty:
                continue
            outcomes.append(outcome)
            if outcome.ok:
                progress(
                    {
                        "type": "mirror",
                        "source": self.name,
                        "endpoint": outcome.endpoint,
                        "status": "ok",
                        "count": len(outcome.elements),
                        "latency_ms": outcome.latency_ms,
                        "message": f"{len(outcome.elements)} объектов · {outcome.latency_ms} мс",
                    }
                )
                if outcome.elements and winner is None:
                    winner = outcome
                    break
            else:
                progress(
                    {
                        "type": "mirror",
                        "source": self.name,
                        "endpoint": outcome.endpoint,
                        "status": "error",
                        "error": outcome.error,
                        "latency_ms": outcome.latency_ms,
                        "message": outcome.error,
                    }
                )
        for thread in threads:
            thread.join(timeout=0.02)

        successful = [item for item in outcomes if item.ok]
        failed = [item for item in outcomes if not item.ok]
        warnings: list[str] = []
        if winner is None and successful:
            # Все доступные зеркала ответили, но совпадений нет.
            winner = successful[0]
            if winner.remark:
                warnings.append(f"Overpass: {winner.remark}")
        if winner is None:
            details = "; ".join(
                f"{urlparse(item.endpoint).netloc}: {item.error}" for item in failed
            ) or "все зеркала не ответили вовремя"
            raise SourceError(f"OpenStreetMap недоступен ({details})")

        if successful and winner is not None:
            other_errors = [item for item in outcomes if not item.ok]
            if other_errors:
                warnings.append(
                    "Не ответили зеркала: "
                    + ", ".join(urlparse(item.endpoint).netloc for item in other_errors)
                )

        elements = winner.elements
        leads = parse_overpass_elements(
            elements,
            source=self.name,
            city=city,
            niche=params.niche,
            keywords=params.keywords,
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        progress(
            {
                "type": "count",
                "source": self.name,
                "found": len(leads),
                "processed": len(elements),
                "message": f"Получено объектов: {len(elements)}, лидов после разбора: {len(leads)}",
            }
        )
        return SourceResult(
            source_id=self.id,
            source_name=self.name,
            leads=leads,
            warnings=warnings,
            query=query,
            elapsed_ms=elapsed_ms,
            raw_elements=len(elements),
            meta={
                "endpoint": winner.endpoint,
                "mirrors_ok": len(successful),
                "mirrors_failed": len(failed),
                "mirror_latency_ms": winner.latency_ms,
            },
        )


def test_endpoints(
    endpoints: list[str],
    timeout: int = 15,
    user_agent: str = USER_AGENT,
) -> list[dict[str, Any]]:
    """Реальная проверка зеркал небольшим запросом. Без имитации."""
    results: "queue.Queue[dict[str, Any]]" = queue.Queue()

    def check(endpoint: str) -> None:
        started = time.monotonic()
        try:
            response = requests.post(
                endpoint,
                data={"data": TEST_QUERY},
                headers={"User-Agent": user_agent},
                timeout=max(8, int(timeout)),
            )
            latency = int((time.monotonic() - started) * 1000)
            if response.status_code != 200:
                results.put(
                    {
                        "endpoint": endpoint,
                        "ok": False,
                        "latency_ms": latency,
                        "message": f"HTTP {response.status_code}",
                        "elements": 0,
                    }
                )
                return
            data = response.json()
            elements = data.get("elements")
            if not isinstance(elements, list):
                message = "ответ без elements"
                if data.get("remark"):
                    message = str(data["remark"])[:160]
                results.put(
                    {
                        "endpoint": endpoint,
                        "ok": False,
                        "latency_ms": latency,
                        "message": message,
                        "elements": 0,
                    }
                )
                return
            results.put(
                {
                    "endpoint": endpoint,
                    "ok": True,
                    "latency_ms": latency,
                    "message": f"OK · {len(elements)} объектов",
                    "elements": len(elements),
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.put(
                {
                    "endpoint": endpoint,
                    "ok": False,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                    "message": f"{type(exc).__name__}: {str(exc)[:120]}",
                    "elements": 0,
                }
            )

    threads = [threading.Thread(target=check, args=(endpoint,), daemon=True) for endpoint in endpoints]
    for thread in threads:
        thread.start()
    collected: list[dict[str, Any]] = []
    deadline = time.monotonic() + max(10, int(timeout)) + 2
    while len(collected) < len(endpoints) and time.monotonic() < deadline:
        try:
            collected.append(results.get(timeout=0.25))
        except queue.Empty:
            continue
    known = {item["endpoint"] for item in collected}
    for endpoint in endpoints:
        if endpoint not in known:
            collected.append(
                {
                    "endpoint": endpoint,
                    "ok": False,
                    "latency_ms": 0,
                    "message": "нет ответа",
                    "elements": 0,
                }
            )
    order = {endpoint: index for index, endpoint in enumerate(endpoints)}
    return sorted(collected, key=lambda item: order.get(item["endpoint"], 999))
