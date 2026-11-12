"""Главное меню Lead Hunter."""

from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import TAGLINE, VERSION
from core.utils import fmt_datetime, fmt_relative
from ui import prompts
from ui.dashboard import render_compact_header
from ui.theme import clear_screen, console, muted


MENU_ITEMS = [
    ("search", "⚔  Начать поиск лидов", "новый поиск по городу, нише и фильтрам"),
    ("leads", "▣  Сохранённые лиды", "просмотр базы, статусы, заметки, удаление"),
    ("saved_search", "⌕  Поиск по сохранённым", "быстрый поиск без обращения к сети"),
    ("history", "↺  История поисков", "детали, повтор, экспорт и очистка"),
    ("export", "⇩  Экспорт CSV / HTML", "автономный отчёт с фильтрами"),
    ("sources", "◈  Управление источниками", "зеркала Overpass и реальная проверка"),
    ("settings", "⚙  Настройки", "параметры, сеть, интерфейс, данные"),
    ("stats", "▤  Статистика", "воронка, города, ниши, активность"),
    ("exit", "⏻  Выход", "закрыть Lead Hunter"),
]


def _menu_panel(app) -> Panel:
    stats = app.storage.stats()
    last = stats.get("last_search") or ""
    enabled = app.settings.get_bool("source_osm_enabled", True)
    status = "[lh.ok]● READY[/]" if enabled else "[lh.warn]● OSM OFF[/]"
    table = Table.grid(padding=(0, 3))
    table.add_column(style="lh.dim", no_wrap=True, width=14)
    table.add_column(style="lh.white")
    table.add_row("СИСТЕМА", Text.from_markup(f"{status} [lh.muted]локально · без сети до запуска поиска[/]"))
    table.add_row("ЛИДЫ", f"[lh.white]{stats.get('total', 0)}[/] [lh.dim]сохранено ·[/] [lh.white]{stats.get('with_phone', 0)}[/] [lh.dim]с телефоном[/]")
    table.add_row("ПОИСКИ", f"[lh.white]{stats.get('searches', 0)}[/] [lh.dim]всего ·[/] [lh.white]{stats.get('today_searches', 0)}[/] [lh.dim]сегодня[/]")
    table.add_row("ПОСЛЕДНИЙ", f"[lh.smoke]{fmt_datetime(last) if last else 'ещё не было'}[/]")
    if last:
        table.add_row("АКТИВНОСТЬ", f"[lh.dim]{fmt_relative(last)}[/]")
    return Panel(
        Group(
            Text(TAGLINE, style="italic lh.smoke"),
            Text(""),
            table,
        ),
        title="[lh.accent]◈ ГЛАВНОЕ МЕНЮ[/]",
        subtitle=f"[lh.dim]LEAD HUNTER · LOCAL EDITION · v{VERSION}[/]",
        border_style="lh.border.hot",
        padding=(0, 2),
    )


def main_menu(app) -> str | None:
    clear_screen()
    render_compact_header(app.storage, app.settings)
    console.print(_menu_panel(app))
    muted("Управление: ↑/↓ · Enter · Ctrl+C — выход")
    choices = [prompts.choice(label, key, description) for key, label, description in MENU_ITEMS]
    return prompts.select(
        "Выбери действие",
        choices,
        instruction="↑/↓ — выбор · Enter — открыть · Ctrl+C — выход",
    )
