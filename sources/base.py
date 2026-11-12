"""Базовые интерфейсы источников лидов."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from core.models import CityInfo, Lead, SearchParams

ProgressCallback = Callable[[dict], None]


class SourceError(Exception):
    """Источник недоступен или вернул ошибку."""


class SourceCancelled(Exception):
    """Поиск отменён пользователем."""


@dataclass
class SourceResult:
    source_id: str
    source_name: str
    leads: list[Lead] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    query: str = ""
    elapsed_ms: int = 0
    raw_elements: int = 0
    meta: dict = field(default_factory=dict)


class LeadSource(Protocol):
    id: str
    name: str
    description: str
    requires_key: bool

    def search(
        self,
        city: CityInfo,
        params: SearchParams,
        progress: ProgressCallback | None = None,
        cancel=None,
    ) -> SourceResult: ...
