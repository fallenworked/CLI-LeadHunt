"""Обёртка над questionary: единый стиль и безопасная отмена по Ctrl+C."""

from __future__ import annotations

from typing import Callable, Iterable, Sequence

import questionary
from questionary import Choice, Style

from ui.theme import console

QSTYLE = Style(
    [
        ("qmark", "fg:#ff2d46 bold"),
        ("question", "fg:#ececf0 bold"),
        ("answer", "fg:#ff2d46 bold"),
        ("pointer", "fg:#ff2d46 bold"),
        ("highlighted", "fg:#ff2d46 bold"),
        ("selected", "fg:#c8102e"),
        ("separator", "fg:#3a1a21"),
        ("instruction", "fg:#6c6c78"),
        ("text", "fg:#ececf0"),
        ("disabled", "fg:#55555f italic"),
    ]
)

SELECTED = "__selected__"


def _safe_ask(prompt):
    try:
        return prompt.ask()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[lh.dim]Отменено.[/]")
        return None


def select(
    message: str,
    choices: Sequence[str | Choice],
    default: str | None = None,
    instruction: str = "↑/↓ — выбор · Enter — подтвердить · Ctrl+C — назад",
) -> str | None:
    return _safe_ask(
        questionary.select(
            message,
            choices=list(choices),
            default=default,
            style=QSTYLE,
            qmark="◈",
            pointer="▸",
            instruction=instruction,
        )
    )


def text(
    message: str,
    default: str = "",
    instruction: str = "Enter — подтвердить · Ctrl+C — назад",
    validate: Callable[[str], bool | str] | None = None,
) -> str | None:
    return _safe_ask(
        questionary.text(
            message,
            default=default,
            style=QSTYLE,
            qmark="›",
            instruction=instruction,
            validate=validate,
        )
    )


def confirm(message: str, default: bool = True) -> bool | None:
    return _safe_ask(
        questionary.confirm(
            message,
            default=default,
            style=QSTYLE,
            qmark="◈",
            instruction="Y — да · N — нет",
        )
    )


def checkbox(
    message: str,
    choices: Iterable[str | Choice],
    instruction: str = "Space — выбрать · Enter — подтвердить",
) -> list[str] | None:
    return _safe_ask(
        questionary.checkbox(
            message,
            choices=list(choices),
            style=QSTYLE,
            qmark="◈",
            pointer="▸",
            instruction=instruction,
        )
    )


def pause(message: str = "Нажми ENTER, чтобы вернуться") -> None:
    try:
        console.input(f"\n[lh.dim]{message}[/] ")
    except (KeyboardInterrupt, EOFError):
        pass


def choice(title: str, value: str | None = None, description: str = "") -> Choice:
    return Choice(title, value=value if value is not None else title, description=description or None)
