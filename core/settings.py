"""Типизированный доступ к настройкам, хранящимся в SQLite."""

from __future__ import annotations

import json
from typing import Any

from config import DEFAULT_SETTINGS


class Settings:
    def __init__(self, storage) -> None:
        self.storage = storage

    def get(self, key: str, default: Any = None) -> Any:
        raw = self.storage.get_setting(key)
        if raw is None:
            return DEFAULT_SETTINGS.get(key, default)
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "on"}

    def get_list(self, key: str) -> list[str]:
        value = self.get(key, [])
        if isinstance(value, list):
            return [str(item) for item in value]
        return []

    def set(self, key: str, value: Any) -> None:
        self.storage.set_setting(key, json.dumps(value, ensure_ascii=False))

    def update(self, **values: Any) -> None:
        for key, value in values.items():
            self.set(key, value)

    def all(self) -> dict[str, Any]:
        data = dict(DEFAULT_SETTINGS)
        for key in DEFAULT_SETTINGS:
            data[key] = self.get(key)
        return data
