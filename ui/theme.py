"""Тема Lead Hunter: графит, кровь, сталь и один яркий красный акцент."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from config import STATUS_STYLES, STATUSES

THEME = Theme(
    {
        "lh.bg": "#0b0b0e",
        "lh.surface": "#121217",
        "lh.white": "#ececf0",
        "lh.smoke": "#8a8a95",
        "lh.muted": "#55555f",
        "lh.dim": "#6c6c78",
        "lh.border": "#3a1a21",
        "lh.border.hot": "#7d0a1b",
        "lh.crimson": "#c8102e",
        "lh.red": "#ff2d46",
        "lh.blood": "#7d0a1b",
        "lh.green": "#79c39a",
        "lh.amber": "#e0a95a",
        "lh.blue": "#7fa7d8",
        "lh.title": "bold #ececf0",
        "lh.accent": "bold #ff2d46",
        "lh.logo": "bold #ececf0",
        "lh.danger": "bold #ff4d5e",
        "lh.ok": "bold #79c39a",
        "lh.warn": "bold #e0a95a",
        "lh.art.reaper": "#79101f",
        "lh.art.blade": "#a3122a",
        "lh.art.shaft": "#55555e",
        "lh.eyes": "bold #ff2d46",
        "lh.status.new": "#a8a8b4",
        "lh.status.contacted": "#6fa9d8",
        "lh.status.interested": "#e0a95a",
        "lh.status.proposal": "#b9a1ec",
        "lh.status.won": "#79c39a",
        "lh.status.rejected": "#8b6470",
        "lh.rule": "#3a1a21",
    }
)

console = Console(theme=THEME, highlight=False, emoji=False, soft_wrap=False)


def clear_screen() -> None:
    if console.is_terminal:
        console.clear()


def status_text(status: str) -> Text:
    key = (status or "new").lower()
    label = STATUSES.get(key, status or "—")
    return Text(label, style=STATUS_STYLES.get(key, "lh.smoke"))


def rule(title: str = "") -> None:
    if title:
        console.print(f"[lh.border]────[/] [lh.accent]{title}[/] [lh.border]{'─' * max(0, console.width - len(title) - 8)}[/]")
    else:
        console.print(f"[lh.border]{'─' * console.width}[/]")


def section(title: str, subtitle: str = "") -> None:
    console.print()
    console.print(f"[lh.accent]◈[/] [lh.title]{title}[/]")
    if subtitle:
        console.print(f"  [lh.dim]{subtitle}[/]")
    console.print(f"[lh.border]{'─' * min(console.width, 96)}[/]")


def error(message: str) -> None:
    console.print(Panel(Text(message, style="lh.danger"), border_style="lh.border.hot", title="[lh.danger]ОШИБКА[/]", title_align="left"))


def warning(message: str) -> None:
    console.print(Panel(Text(message, style="lh.warn"), border_style="lh.amber", title="[lh.warn]ВНИМАНИЕ[/]", title_align="left"))


def success(message: str) -> None:
    console.print(f"[lh.ok]✔[/] {message}")


def info(message: str) -> None:
    console.print(f"[lh.crimson]›[/] {message}")


def muted(message: str) -> None:
    console.print(f"[lh.muted]{message}[/]")


def kv_table(rows: list[tuple[str, str]], title: str = "") -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="lh.dim", no_wrap=True)
    table.add_column(style="lh.white")
    for key, value in rows:
        table.add_row(key.upper(), value)
    if title:
        return table
    return table


def make_panel(renderable, title: str = "", subtitle: str = ""):
    return Panel(
        renderable,
        title=f"[lh.accent]{title}[/]" if title else None,
        subtitle=f"[lh.dim]{subtitle}[/]" if subtitle else None,
        border_style="lh.border",
        padding=(0, 1),
    )
