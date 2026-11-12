"""Главный экран, компактная шапка и заставка запуска."""

from __future__ import annotations

import platform
import sys
import time

from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from config import (
    APP_EDITION,
    APP_NAME,
    DEFAULT_ENDPOINTS,
    TAGLINE,
    VERSION,
)
from ui.reaper import dashboard_art, logo_text, print_art
from ui.theme import console
from ui.theme import muted
from core.utils import file_size, fmt_datetime, fmt_relative


def _stat_block(value: object, label: str, accent: bool = False) -> Text:
    value_style = "bold lh.red" if accent else "bold lh.white"
    block = Text()
    block.append(f"{value}", style=value_style)
    block.append("\n" + label.upper(), style="lh.dim")
    return block


def _stats_table(stats: dict) -> Table:
    table = Table.grid(padding=(0, 4))
    table.add_column(justify="left")
    table.add_column(justify="left")
    table.add_row(
        _stat_block(stats.get("found_total", 0), "найдено", True),
        _stat_block(stats.get("total", 0), "сохранено"),
    )
    table.add_row(
        _stat_block(stats.get("searches", 0), "поисков"),
        _stat_block(stats.get("with_phone", 0), "с телефоном"),
    )
    table.add_row(
        _stat_block(stats.get("cities", 0), "городов"),
        _stat_block(stats.get("niches", 0), "ниш"),
    )
    return table


def _system_table(storage, settings, stats: dict) -> Table:
    endpoints = settings.get_list("endpoints") or list(DEFAULT_ENDPOINTS)
    enabled = settings.get_bool("source_osm_enabled", True)
    status_style = "lh.ok" if enabled else "lh.warn"
    status_label = "READY" if enabled else "OSM OFF"
    last_run = settings.get("last_run", "")
    last_search = stats.get("last_search") or ""
    table = Table.grid(padding=(0, 2))
    table.add_column(style="lh.dim", no_wrap=True)
    table.add_column(style="lh.white")
    table.add_row(
        "СИСТЕМА",
        Text.from_markup(f"[{status_style}]● {status_label}[/]  [lh.muted]локально · без сервера[/]"),
    )
    table.add_row("БАЗА", f"[lh.white]{storage.path.name}[/] [lh.muted]· {file_size(storage.path) // 1024} КБ[/]")
    table.add_row(
        "ИСТОЧНИК",
        f"[lh.white]{'OSM Overpass' if enabled else 'отключён'}[/] [lh.muted]· {len(endpoints)} зеркал[/]",
    )
    table.add_row(
        "СРЕДА",
        f"[lh.white]Python {platform.python_version()}[/] [lh.muted]· {platform.system()} {platform.release()}[/]",
    )
    table.add_row("ЗАПУСК", f"[lh.smoke]{fmt_relative(str(last_run))}[/]")
    table.add_row("ПОИСК", f"[lh.smoke]{fmt_datetime(str(last_search)) if last_search else 'ещё не было'}[/]")
    return table


def render_dashboard(storage, settings, compact: bool = False) -> None:
    stats = storage.stats()
    if compact:
        render_compact_header(storage, settings, stats)
        return

    art = dashboard_art()
    left = Group(
        Align.center(art),
        Text(""),
        Align.center(Text("— MEMENTO VENDERE —", style="lh.muted")),
    )

    right = Table.grid(padding=(0, 0))
    right.add_column()
    logo = logo_text()
    right.add_row(logo)
    right.add_row(Text("LOCAL EDITION", style="lh.crimson"))
    right.add_row(Text(""))
    right.add_row(Text(TAGLINE, style="italic lh.smoke"))
    right.add_row(Text(""))
    right.add_row(Text("─" * 42, style="lh.rule"))
    right.add_row(_stats_table(stats))
    right.add_row(Text(""))
    right.add_row(_system_table(storage, settings, stats))
    right.add_row(Text(""))
    right.add_row(
        Text.from_markup(f"[lh.dim]VERSION[/] [lh.white]{VERSION}[/]  [lh.dim]·[/]  [lh.dim]STORAGE[/] [lh.white]SQLite[/]")
    )

    layout = Table.grid(expand=True, padding=(0, 2))
    if console.width >= 100:
        layout.add_column(justify="center", no_wrap=True)
        layout.add_column(justify="left")
        layout.add_row(left, right)
    else:
        layout.add_column(justify="center")
        layout.add_row(left)
        layout.add_row(Text(""))
        layout.add_row(Align.center(right))

    panel = Panel(
        layout,
        title="[lh.accent]◈ LEAD HUNTER // COMMAND DECK[/]",
        subtitle="[lh.dim]LOCAL EDITION · OFFLINE · SQLITE[/]",
        border_style="lh.border.hot",
        padding=(0, 2),
    )
    console.print(panel)
    console.print(
        Align.center(
            Text.from_markup(
                "[lh.muted]Нажми [/][lh.white]ENTER[/][lh.muted], чтобы открыть меню охоты[/]"
            )
        )
    )


def render_compact_header(storage, settings, stats: dict | None = None) -> None:
    stats = stats or storage.stats()
    enabled = settings.get_bool("source_osm_enabled", True)
    status = "[lh.ok]● READY[/]" if enabled else "[lh.warn]● OSM OFF[/]"
    left = Text.from_markup(
        f"[lh.accent]◈[/] [lh.logo]LEAD HUNTER[/] [lh.dim]·[/] [lh.crimson]LOCAL EDITION[/]  "
        f"[lh.muted]v{VERSION}[/]"
    )
    right = Text.from_markup(
        f"{status}  [lh.dim]│[/] [lh.dim]ЛИДЫ[/] [lh.white]{stats.get('total', 0)}[/]  "
        f"[lh.dim]│[/] [lh.dim]ПОИСКИ[/] [lh.white]{stats.get('searches', 0)}[/]"
    )
    grid = Table.grid(expand=True)
    grid.add_column(justify="left")
    grid.add_column(justify="right")
    grid.add_row(left, right)
    subtitle = Text(TAGLINE, style="lh.dim")
    panel = Panel(
        Group(grid, subtitle),
        border_style="lh.border",
        padding=(0, 1),
    )
    console.print(panel)


def show_boot(settings) -> None:
    """Короткая атмосферная заставка. Не имитирует результаты поиска."""
    if not settings.get_bool("animations", True):
        return
    console.clear()
    welcome = Table.grid(expand=True)
    welcome.add_column(justify="center")
    welcome.add_row(logo_text())
    welcome.add_row(Text(APP_EDITION, style="lh.crimson"))
    welcome.add_row(Text(TAGLINE, style="italic lh.smoke"))
    welcome.add_row(Text(""))
    console.print(Align.center(welcome))
    steps = [
        ("ЯДРО", "Загрузка охотничьего ядра"),
        ("БАЗА", "Подключение локального хранилища SQLite"),
        ("СПРАВОЧНИКИ", "Загрузка городов и ниш"),
        ("ИСТОЧНИКИ", "Проверка реестра источников"),
        ("ТЕМА", "Включение терминального протокола"),
    ]
    with Progress(
        SpinnerColumn(style="lh.red"),
        TextColumn("[lh.smoke]{task.description}"),
        BarColumn(bar_width=34, style="lh.border", complete_style="lh.crimson", finished_style="lh.red"),
        TextColumn("[lh.dim]{task.percentage:>3.0f}%"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Инициализация", total=len(steps))
        for label, description in steps:
            progress.update(task, description=f"{label:<12} {description}")
            time.sleep(0.11)
            progress.advance(task)
    console.print(f"[lh.ok]✔[/] [lh.smoke]Система готова. Добро пожаловать на охоту.[/]")
    time.sleep(0.2)
