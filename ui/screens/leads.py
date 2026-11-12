"""Просмотр сохранённых лидов: страницы, фильтры, карточка и действия."""

from __future__ import annotations

import math
import webbrowser
from typing import Any

from rich.panel import Panel
from rich.text import Text

from config import STATUSES
from core.utils import clean_text, map_links
from ui import prompts
from ui.dashboard import render_compact_header
from ui.theme import clear_screen, console, muted, section
from ui.widgets import lead_detail_panel, leads_panel


def _pages(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / max(1, page_size)))


def _filter_summary(filters: dict[str, Any]) -> str:
    parts: list[str] = []
    if filters.get("query"):
        parts.append(f"поиск: {filters['query']}")
    if filters.get("city"):
        parts.append(f"город: {filters['city']}")
    if filters.get("niche"):
        parts.append(f"ниша: {filters['niche']}")
    if filters.get("status"):
        parts.append(f"статус: {STATUSES.get(str(filters['status']), filters['status'])}")
    if filters.get("has_phone"):
        parts.append("только с телефоном")
    if filters.get("search_id"):
        parts.append(f"поиск #{filters['search_id']}")
    return " · ".join(parts) if parts else "без фильтров"


def _choose_lead(rows: list[dict[str, Any]], start_index: int) -> dict[str, Any] | None:
    choices = []
    for offset, lead in enumerate(rows):
        name = clean_text(lead.get("name")) or "без названия"
        city = clean_text(lead.get("city"))
        phone = clean_text(lead.get("phone"))
        label = f"{start_index + offset:>2}. {name}"
        if city:
            label += f" · {city}"
        if phone:
            label += f" · {phone}"
        choices.append(prompts.choice(label, str(lead.get("id"))))
    if not choices:
        return None
    value = prompts.select("Открыть лид", choices)
    if value is None:
        return None
    return next((lead for lead in rows if str(lead.get("id")) == value), None)


def _open_maps(lead: dict[str, Any]) -> None:
    links = map_links(lead)
    choices = [
        prompts.choice("Яндекс Карты", links["yandex"]),
        prompts.choice("2ГИС", links["2gis"]),
        prompts.choice("OpenStreetMap", links["osm"]),
    ]
    if links.get("yandex_point"):
        choices.insert(0, prompts.choice("Точка на Яндекс Картах", links["yandex_point"]))
    if links.get("osm_point"):
        choices.append(prompts.choice("Точка на OpenStreetMap", links["osm_point"]))
    url = prompts.select("Куда открыть карту?", choices)
    if url:
        webbrowser.open(url)
        muted("Ссылка открыта в браузере.")


def _change_status(app, lead: dict[str, Any]) -> dict[str, Any]:
    current = str(lead.get("status") or "new")
    choices = [prompts.choice(label, key) for key, label in STATUSES.items()]
    value = prompts.select("Новый статус лида", choices, default=current)
    if value is None:
        return lead
    app.storage.update_lead_status(int(lead["id"]), value)
    from ui.theme import success

    success(f"Статус обновлён: {STATUSES.get(value, value)}")
    return app.storage.get_lead(int(lead["id"])) or lead


def _edit_notes(app, lead: dict[str, Any]) -> dict[str, Any]:
    current = clean_text(lead.get("notes"))
    value = prompts.text(
        "Заметка по лиду (пусто — очистить)",
        default=current,
        instruction="Enter — сохранить · Ctrl+C — назад",
    )
    if value is None:
        return lead
    app.storage.update_lead_notes(int(lead["id"]), clean_text(value))
    from ui.theme import success

    success("Заметка сохранена.")
    return app.storage.get_lead(int(lead["id"])) or lead


def view_lead(app, lead_id: int) -> None:
    from ui.screens.export import export_rows_interactive

    while True:
        lead = app.storage.get_lead(int(lead_id))
        if lead is None:
            from ui.theme import warning

            warning("Лид не найден. Возможно, он был удалён.")
            prompts.pause()
            return
        clear_screen()
        render_compact_header(app.storage, app.settings)
        console.print(lead_detail_panel(lead))
        choices = [
            prompts.choice("✎  Изменить статус", "status"),
            prompts.choice("✎  Заметка", "notes"),
            prompts.choice("↗  Открыть на карте", "map"),
            prompts.choice("⇩  Экспорт этого лида", "export"),
            prompts.choice("✖  Удалить лид", "delete"),
            prompts.choice("←  Назад к списку", "back"),
        ]
        action = prompts.select("Действие с лидом", choices)
        if action in (None, "back"):
            return
        if action == "status":
            lead = _change_status(app, lead)
        elif action == "notes":
            lead = _edit_notes(app, lead)
        elif action == "map":
            _open_maps(lead)
            prompts.pause()
        elif action == "export":
            export_rows_interactive(
                app,
                [lead],
                title=f"Лид #{lead['id']}: {lead.get('name', '')}",
                prefix=f"lead_{lead['id']}",
            )
        elif action == "delete":
            confirmed = prompts.confirm(
                f"Удалить лид «{clean_text(lead.get('name'))}» без возможности восстановления?",
                default=False,
            )
            if confirmed:
                app.storage.delete_lead(int(lead["id"]))
                from ui.theme import success

                success("Лид удалён.")
                prompts.pause()
                return


def _edit_filters(app, filters: dict[str, Any]) -> None:
    query = prompts.text("Поиск по названию, телефону, адресу, заметкам", default=str(filters.get("query", "")))
    if query is None:
        return
    filters["query"] = clean_text(query)

    city = prompts.text("Город (пусто — любой)", default=str(filters.get("city", "")))
    if city is None:
        return
    filters["city"] = clean_text(city)

    niche = prompts.text("Ниша (пусто — любая)", default=str(filters.get("niche", "")))
    if niche is None:
        return
    filters["niche"] = clean_text(niche)

    status_choices = [prompts.choice("Любой статус", "")] + [
        prompts.choice(label, key) for key, label in STATUSES.items()
    ]
    status = prompts.select(
        "Статус",
        status_choices,
        default=str(filters.get("status", "")),
    )
    if status is None:
        return
    filters["status"] = status

    phone = prompts.confirm("Только лиды с телефоном?", default=bool(filters.get("has_phone")))
    if phone is None:
        return
    filters["has_phone"] = phone


def _export_filtered(app, filters: dict[str, Any], rows: list[dict[str, Any]], title: str) -> None:
    from ui.screens.export import export_rows_interactive

    total = app.storage.count_leads(filters)
    if total == 0:
        from ui.theme import warning

        warning("По текущему фильтру нет лидов для экспорта.")
        prompts.pause()
        return
    scope = prompts.select(
        "Что экспортировать?",
        [
            prompts.choice(f"Все лиды по фильтру ({total})", "all"),
            prompts.choice(f"Только текущую страницу ({len(rows)})", "page"),
        ],
    )
    if scope is None:
        return
    selected = app.storage.list_leads(filters, limit=100000) if scope == "all" else rows
    export_rows_interactive(
        app,
        selected,
        title=title,
        prefix="leads",
    )


def browse_leads(
    app,
    filters: dict[str, Any] | None = None,
    title: str = "СОХРАНЁННЫЕ ЛИДЫ",
) -> None:
    filters = dict(filters or {})
    page = 1
    page_size = max(5, app.settings.get_int("page_size", 15))

    while True:
        total = app.storage.count_leads(filters)
        pages = _pages(total, page_size)
        page = max(1, min(page, pages))
        start_index = (page - 1) * page_size + 1
        rows = app.storage.list_leads(filters, limit=page_size, offset=(page - 1) * page_size)

        clear_screen()
        render_compact_header(app.storage, app.settings)
        section(title, _filter_summary(filters))
        console.print(leads_panel(rows, total, page, pages, title=title, start_index=start_index))

        actions: list = []
        if pages > 1:
            actions.extend(
                [
                    prompts.choice(f"→  Следующая страница ({page + 1}/{pages})", "next"),
                    prompts.choice(f"←  Предыдущая страница ({page - 1}/{pages})", "prev"),
                ]
            )
        actions.extend(
            [
                prompts.choice("▣  Открыть лид", "open"),
                prompts.choice("⌕  Фильтры и поиск", "filter"),
                prompts.choice("↺  Сбросить фильтры", "reset"),
                prompts.choice("⇩  Экспорт", "export"),
                prompts.choice("←  Назад", "back"),
            ]
        )
        action = prompts.select("Действие", actions)
        if action in (None, "back"):
            return
        if action == "next":
            page = min(pages, page + 1)
        elif action == "prev":
            page = max(1, page - 1)
        elif action == "filter":
            _edit_filters(app, filters)
            page = 1
        elif action == "reset":
            filters.clear()
            page = 1
        elif action == "open":
            lead = _choose_lead(rows, start_index)
            if lead is not None:
                view_lead(app, int(lead["id"]))
        elif action == "export":
            _export_filtered(app, filters, rows, title)


def search_saved_leads(app) -> None:
    """Быстрый поиск по уже сохранённым лидам, без обращения к сети."""
    query = prompts.text(
        "Что искать в сохранённых лидах? (название, телефон, адрес, заметки)",
        validate=lambda value: bool(value.strip()) or "Введи поисковый запрос",
    )
    if query is None:
        return
    text = clean_text(query)
    filters = {"query": text}
    total = app.storage.count_leads(filters)
    if total == 0:
        clear_screen()
        render_compact_header(app.storage, app.settings)
        console.print(
            Panel(
                Text(f"По запросу «{text}» ничего не найдено.", style="lh.smoke"),
                title="[lh.accent]ПОИСК ПО СОХРАНЁННЫМ ЛИДАМ[/]",
                border_style="lh.border",
            )
        )
        prompts.pause()
        return
    browse_leads(app, filters, title=f"ПОИСК: {text[:40]}")
