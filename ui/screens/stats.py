"""Статистика охоты: база, воронка статусов, города, ниши и активность."""

from __future__ import annotations

from datetime import date

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import STATUSES
from core.utils import file_size, fmt_datetime, human_bytes, human_duration
from ui import prompts
from ui.dashboard import render_compact_header
from ui.theme import clear_screen, console, section, success
from ui.widgets import SEARCH_STATUS


def _bar(value: int, maximum: int, width: int = 22) -> Text:
    filled = 0 if maximum <= 0 else max(0, min(width, round(value / maximum * width)))
    text = Text()
    text.append("█" * filled, style="lh.crimson")
    text.append("░" * (width - filled), style="lh.border")
    return text


def _overview_panel(stats: dict) -> Panel:
    table = Table.grid(padding=(0, 4))
    table.add_column(style="lh.dim", no_wrap=True)
    table.add_column(style="lh.white")
    table.add_row("ЛИДОВ В БАЗЕ", f"[bold lh.white]{stats.get('total', 0)}[/]")
    table.add_row("С ТЕЛЕФОНОМ", str(stats.get("with_phone", 0)))
    table.add_row("С EMAIL", str(stats.get("with_email", 0)))
    table.add_row("С САЙТОМ", str(stats.get("with_website", 0)))
    table.add_row("ГОРОДОВ", str(stats.get("cities", 0)))
    table.add_row("НИШ", str(stats.get("niches", 0)))
    table.add_row("", "")
    table.add_row("ПОИСКОВ ВСЕГО", str(stats.get("searches", 0)))
    table.add_row("УСПЕШНЫХ", f"[lh.ok]{stats.get('completed_searches', 0)}[/]")
    table.add_row("С ОШИБКОЙ", f"[lh.danger]{stats.get('failed_searches', 0)}[/]")
    table.add_row("СЕГОДНЯ", str(stats.get("today_searches", 0)))
    table.add_row("НАЙДЕНО ИСТОЧНИКОМ", str(stats.get("found_total", 0)))
    table.add_row("НОВЫХ ЗА ВСЁ ВРЕМЯ", f"[lh.ok]{stats.get('new_total', 0)}[/]")
    last = stats.get("last_search") or ""
    table.add_row("ПОСЛЕДНИЙ ПОИСК", fmt_datetime(last) if last else "—")
    return Panel(
        table,
        title="[lh.accent]ОБЗОР[/]",
        border_style="lh.border.hot",
        padding=(0, 1),
    )


def _status_panel(stats: dict) -> Panel:
    counts = stats.get("status_counts") or {}
    total = max(1, int(stats.get("total", 0)))
    table = Table(
        box=None,
        show_header=True,
        header_style="lh.dim",
        padding=(0, 1),
        expand=True,
    )
    table.add_column("СТАТУС", style="lh.white", width=16)
    table.add_column("ЛИДОВ", justify="right", width=8, style="lh.white")
    table.add_column("ДОЛЯ", justify="right", width=8, style="lh.muted")
    table.add_column("РАСПРЕДЕЛЕНИЕ", ratio=1)
    for key, label in STATUSES.items():
        value = int(counts.get(key, 0))
        table.add_row(
            label,
            str(value),
            f"{value / total * 100:.0f}%",
            _bar(value, total, 24),
        )
    return Panel(
        table,
        title="[lh.accent]ВОРОНКА ЛИДОВ[/]",
        border_style="lh.border",
        padding=(0, 1),
    )


def _top_panel(title: str, rows: list[tuple[str, int]]) -> Panel:
    maximum = max((count for _, count in rows), default=0)
    table = Table(
        box=None,
        show_header=False,
        padding=(0, 1),
        expand=True,
    )
    table.add_column(style="lh.smoke", ratio=2)
    table.add_column(justify="right", width=6, style="lh.white")
    table.add_column(ratio=2)
    if not rows:
        table.add_row("Нет данных", "—", "")
    for name, count in rows:
        table.add_row(name, str(count), _bar(count, maximum, 18))
    return Panel(
        table,
        title=f"[lh.accent]{title}[/]",
        border_style="lh.border",
        padding=(0, 1),
    )


def _activity_panel(app) -> Panel:
    weekly = app.storage.weekly_searches(7)
    maximum = max((count for _, count in weekly), default=0)
    table = Table.grid(padding=(0, 2))
    table.add_column(style="lh.muted", no_wrap=True, width=10)
    table.add_column(justify="right", width=4, style="lh.white")
    table.add_column(ratio=1)
    months = (
        "янв", "фев", "мар", "апр", "май", "июн",
        "июл", "авг", "сен", "окт", "ноя", "дек",
    )
    today = date.today()
    for value, count in weekly:
        try:
            day = date.fromisoformat(value)
            label = f"{day.day:02d} {months[day.month - 1]}"
            if day == today:
                label += " •"
        except ValueError:
            label = value[5:10]
        table.add_row(label, str(count), _bar(count, maximum, 24))
    return Panel(
        table,
        title="[lh.accent]АКТИВНОСТЬ ЗА 7 ДНЕЙ[/]",
        subtitle="[lh.dim]число запусков поиска в день[/]",
        border_style="lh.border",
        padding=(0, 1),
    )


def _database_panel(app) -> Panel:
    stats = app.storage.stats()
    table = Table.grid(padding=(0, 3))
    table.add_column(style="lh.dim", no_wrap=True, width=18)
    table.add_column(style="lh.white")
    table.add_row("ФАЙЛ", app.storage.path.name)
    table.add_row("РАЗМЕР", human_bytes(file_size(app.storage.path)))
    table.add_row("ПУТЬ", str(app.storage.path))
    average = 0 if not stats.get("searches") else stats.get("new_total", 0) / stats["searches"]
    table.add_row("СРЕДНЕЕ НОВЫХ", f"{average:.1f} на поиск")
    return Panel(
        table,
        title="[lh.accent]ХРАНИЛИЩЕ[/]",
        border_style="lh.border",
        padding=(0, 1),
    )


def stats_screen(app) -> None:
    from ui.screens.export import export_rows_interactive

    while True:
        stats = app.storage.stats()
        clear_screen()
        render_compact_header(app.storage, app.settings)
        section("СТАТИСТИКА", "цифры считаются по локальной SQLite, без внешней аналитики")

        top = Table.grid(expand=True, padding=(0, 1))
        top.add_column(ratio=1)
        top.add_column(ratio=1)
        top.add_row(
            _top_panel("ТОП ГОРОДОВ", app.storage.top_cities(8)),
            _top_panel("ТОП НИШ", app.storage.top_niches(8)),
        )
        console.print(
            Panel(
                Group(
                    top,
                    Text(""),
                    _activity_panel(app),
                ),
                title="[lh.accent]КАРТА ОХОТЫ[/]",
                border_style="lh.border",
                padding=(0, 1),
            )
        )
        console.print(
            Panel(
                Group(
                    _overview_panel(stats),
                    Text(""),
                    _status_panel(stats),
                    Text(""),
                    _database_panel(app),
                ),
                title="[lh.accent]СВОДКА[/]",
                border_style="lh.border",
                padding=(0, 1),
            )
        )

        action = prompts.select(
            "Статистика",
            [
                prompts.choice("↻  Обновить", "refresh"),
                prompts.choice("⇩  Экспорт всех лидов", "export"),
                prompts.choice("⚒  Сжать базу (VACUUM)", "vacuum"),
                prompts.choice("←  Назад", "back"),
            ],
        )
        if action in (None, "back"):
            return
        if action == "export":
            rows = app.storage.list_leads(limit=100000)
            if not rows:
                from ui.theme import warning

                warning("В базе пока нет лидов.")
                prompts.pause()
                continue
            export_rows_interactive(app, rows, title="Все сохранённые лиды", prefix="all_leads")
        elif action == "vacuum":
            with console.status("[lh.crimson]Сжимаю базу…[/]", spinner="dots2"):
                app.storage.vacuum()
            success(f"База сжата: {human_bytes(file_size(app.storage.path))}")
            prompts.pause()
