"""Таблицы и карточки, общие для экранов приложения."""

from __future__ import annotations

import webbrowser
from typing import Any, Iterable

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import STATUSES
from core.utils import clean_text, fmt_datetime, fmt_relative, human_duration, map_links, truncate
from ui.theme import console, status_text


SEARCH_STATUS = {
    "ok": ("OK", "lh.ok"),
    "empty": ("ПУСТО", "lh.smoke"),
    "error": ("ОШИБКА", "lh.danger"),
    "cancelled": ("ОТМЕНА", "lh.warn"),
    "running": ("ИДЁТ", "lh.amber"),
}


def leads_table(rows: Iterable[dict[str, Any]], start_index: int = 1) -> Table:
    rows = list(rows)
    narrow = console.width < 110
    very_narrow = console.width < 92
    table = Table(
        box=None,
        show_header=True,
        header_style="lh.dim",
        expand=True,
        padding=(0, 1),
        row_styles=["", "on #0e0e12"],
    )
    table.add_column("#", justify="right", width=4, style="lh.muted")
    table.add_column("НАЗВАНИЕ", style="lh.white", no_wrap=False, ratio=3)
    table.add_column("ТЕЛЕФОН", style="lh.crimson", no_wrap=True, width=18)
    if not very_narrow:
        table.add_column("ГОРОД", style="lh.smoke", no_wrap=True, width=16)
    if not narrow:
        table.add_column("НИША", style="lh.smoke", no_wrap=True, width=15)
    table.add_column("СТАТУС", no_wrap=True, width=11)
    if not narrow:
        table.add_column("ИСТОЧНИК", style="lh.muted", no_wrap=True, width=10)
    table.add_column("НАЙДЕН", style="lh.muted", no_wrap=True, width=11)

    for index, lead in enumerate(rows, start=start_index):
        name = clean_text(lead.get("name"))
        address = clean_text(lead.get("address"))
        name_cell = Text(name, style="lh.white")
        if address:
            name_cell.append("\n" + truncate(address, 38), style="lh.muted")
        phone = clean_text(lead.get("phone")) or "—"
        values = [
            str(index),
            name_cell,
            phone,
        ]
        if not very_narrow:
            values.append(clean_text(lead.get("city")) or "—")
        if not narrow:
            values.append(truncate(clean_text(lead.get("niche")), 15) or "—")
        values.append(status_text(str(lead.get("status") or "new")))
        if not narrow:
            source = clean_text(lead.get("source"))
            values.append(truncate(source.split("/")[0].strip(), 10))
        values.append(fmt_datetime(lead.get("found_at"), "%d.%m %H:%M"))
        table.add_row(*values)
    return table


def leads_panel(
    rows: list[dict[str, Any]],
    total: int,
    page: int,
    pages: int,
    title: str = "НАЙДЕННЫЕ ЛИДЫ",
    start_index: int | None = None,
) -> Panel:
    start = (start_index if start_index is not None else (page - 1) * max(1, len(rows)) + 1)
    body = leads_table(rows, start_index=start)
    if not rows:
        body = Text("Лидов по этому фильтру нет.", style="lh.smoke")
    subtitle = f"страница {page}/{pages} · всего {total} · ↓/↑ и Enter для действий"
    return Panel(
        body,
        title=f"[lh.accent]{title}[/]",
        subtitle=f"[lh.dim]{subtitle}[/]",
        border_style="lh.border",
        padding=(0, 1),
    )


def lead_detail_panel(lead: dict[str, Any]) -> Panel:
    links = map_links(lead)
    extra = lead.get("extra") or {}
    contacts = extra.get("contacts") or {}
    contact_text = ", ".join(f"{key}: {value}" for key, value in contacts.items()) or "—"
    table = Table.grid(padding=(0, 2))
    table.add_column(style="lh.dim", no_wrap=True, width=15)
    table.add_column(style="lh.white")

    def add(label: str, value: str, style: str = "lh.white") -> None:
        table.add_row(label.upper(), Text(value or "—", style=style))

    add("Название", clean_text(lead.get("name")), "bold lh.white")
    table.add_row("СТАТУС", status_text(str(lead.get("status") or "new")))
    add("Телефон", clean_text(lead.get("phone")) or "—", "lh.red")
    add("Email", clean_text(lead.get("email")) or "—")
    add("Адрес", clean_text(lead.get("address")) or "—")
    add("Город", ", ".join(part for part in (clean_text(lead.get("city")), clean_text(lead.get("region")), clean_text(lead.get("country"))) if part) or "—")
    add("Ниша", clean_text(lead.get("niche")) or "—")
    add("Тип", clean_text(lead.get("lead_type")) or "—")
    add("Часы", clean_text(lead.get("opening_hours")) or "—")
    add("Сайт", clean_text(lead.get("website")) or "—")
    add("Контакты", contact_text)
    if lead.get("lat") is not None and lead.get("lon") is not None:
        add("Координаты", f"{lead['lat']}, {lead['lon']}")
    add("Источник", clean_text(lead.get("source")) or "—")
    add("Найден", fmt_datetime(lead.get("found_at")))
    add("Обновлён", fmt_relative(lead.get("last_seen_at")))
    add("Заметки", clean_text(lead.get("notes")) or "—", "lh.smoke")
    table.add_row("")
    table.add_row(
        "ССЫЛКИ",
        Text.from_markup(
            f"[lh.crimson]Яндекс[/] [lh.muted]{links['yandex']}[/]\n"
            f"[lh.crimson]2ГИС[/]  [lh.muted]{links['2gis']}[/]\n"
            f"[lh.crimson]OSM[/]   [lh.muted]{links['osm']}[/]"
        ),
    )
    return Panel(
        table,
        title=f"[lh.accent]ЛИД #{lead.get('id')}[/]",
        subtitle="[lh.dim]ENTER на карточке не нужен — выбери действие в меню[/]",
        border_style="lh.border.hot",
        padding=(0, 1),
    )


def searches_table(searches: Iterable[dict[str, Any]]) -> Table:
    searches = list(searches)
    narrow = console.width < 110
    table = Table(
        box=None,
        show_header=True,
        header_style="lh.dim",
        expand=True,
        padding=(0, 1),
        row_styles=["", "on #0e0e12"],
    )
    table.add_column("#", justify="right", width=4, style="lh.muted")
    table.add_column("ДАТА", no_wrap=True, width=16, style="lh.smoke")
    table.add_column("ГОРОД", no_wrap=True, width=16, style="lh.white")
    table.add_column("НИША", no_wrap=True, width=15, style="lh.smoke")
    table.add_column("НАЙДЕНО", justify="right", width=9, style="lh.white")
    table.add_column("НОВЫХ", justify="right", width=8, style="lh.ok")
    table.add_column("ДУБЛИ", justify="right", width=8, style="lh.muted")
    if not narrow:
        table.add_column("ВРЕМЯ", justify="right", width=10, style="lh.muted")
        table.add_column("ОШИБКИ", justify="right", width=8, style="lh.danger")
    table.add_column("СТАТУС", no_wrap=True, width=10)

    for search in searches:
        label, style = SEARCH_STATUS.get(str(search.get("status")), ("?", "lh.smoke"))
        values = [
            str(search.get("id")),
            fmt_datetime(search.get("created_at"), "%d.%m.%Y %H:%M"),
            truncate(clean_text(search.get("city")), 16),
            truncate(clean_text(search.get("niche")), 15),
            str(search.get("total_found") or 0),
            str(search.get("new_leads") or 0),
            str(search.get("duplicates") or 0),
        ]
        if not narrow:
            values.append(human_duration(search.get("duration_ms") or 0))
            values.append(str(len(search.get("errors") or [])))
        values.append(Text(label, style=style))
        table.add_row(*values)
    return table


def searches_panel(searches: list[dict[str, Any]]) -> Panel:
    body = searches_table(searches)
    if not searches:
        body = Text("История пока пуста. Запусти первый поиск.", style="lh.smoke")
    return Panel(
        body,
        title="[lh.accent]ИСТОРИЯ ПОИСКОВ[/]",
        subtitle="[lh.dim]лиды хранятся отдельно и не удаляются вместе с историей[/]",
        border_style="lh.border",
        padding=(0, 1),
    )


def open_lead_link(lead: dict[str, Any], network: str = "yandex") -> None:
    links = map_links(lead)
    url = links.get(network) or links.get("yandex")
    if url:
        webbrowser.open(url)


def status_choices() -> list[tuple[str, str]]:
    return [(key, label) for key, label in STATUSES.items()]
