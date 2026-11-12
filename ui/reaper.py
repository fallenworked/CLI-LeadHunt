"""ASCII-композиция Смерти с косой и блочный логотип."""

from __future__ import annotations

from rich.text import Text

from ui.theme import console

# Классическая Смерть с косой. Тело — тёмная кровь, лезвие и древко — сталь.
REAPER = [
    ";::::;",
    "           ;::::; :;",
    "         ;:::::'   :;",
    "        ;:::::;     ;.",
    "       ,:::::'       ;           OOO\\",
    "       ::::::;       ;          OOOOO\\",
    "       ;:::::;       ;         OOOOOOOO",
    "      ,;::::::;     ;'         / OOOOOOO",
    "    ;:::::::::`. ,,,;.        /  / DOOOOOO",
    "  .';:::::::::::::::::;,     /  /     DOOOO",
    ",::::::;::::::;;;;::::;,   /  /        DOOO",
    ";`::::::`'::::::;;;::::: ,#/  /          DOOO",
    ":`:::::::`;::::::;;::: ;::#  /            DOOO",
    "::`:::::::`;:::::::: ;::::# /              DOO",
    "`:`:::::::`;:::::: ;::::::#/               DOO",
    ":::`:::::::`;; ;:::::::::##                OO",
    "::::`:::::::`;::::::::;:::#                OO",
    "`:::::`::::::::::::;'`:;::#                O",
    "  `:::::`::::::::;' /  / `:#",
    "   ::::::`:::::;'  /  /   `#",
]

# Уменьшенная версия для узких или низких терминалов.
COMPACT = [
    "      ;::::;",
    "    ;:::::; :;          OOO\\",
    "  ,:::::'   ;          / OOOO",
    " ;:::::;   ;'         / DOOO",
    "::::::;  ,#/        /   DOO",
    "`:::::;:# /        /    OO",
    "  `:::;' /  /     `#",
]

LOGO = [
    "╦  ╔═╗╔═╗╔╦╗  ╦ ╦╦ ╦╔╗╔╔╦╗╔═╗╦═╗",
    "║  ║╣ ╠═╣ ║║  ╠═╣║ ║║║║ ║ ║╣ ╠╦╝",
    "╩═╝╚═╝╩ ╩═╩╝  ╩ ╩╚═╝╝╚╝ ╩ ╚═╝╩╚═",
]

_BLADE_CHARS = set("OD")
_HANDLE_CHARS = set("/\\#")


def _char_style(char: str) -> str:
    if char in _BLADE_CHARS:
        return "lh.art.blade"
    if char in _HANDLE_CHARS:
        return "lh.art.shaft"
    return "lh.art.reaper"


def _art_text(lines: list[str]) -> Text:
    text = Text()
    for line in lines:
        for char in line.rstrip():
            text.append(char, style=_char_style(char))
        text.append("\n")
    text.rstrip()
    return text


def reaper_text(compact: bool = False) -> Text:
    return _art_text(COMPACT if compact else REAPER)


def logo_text() -> Text:
    text = Text()
    for index, line in enumerate(LOGO):
        text.append(line + "\n", style="lh.logo" if index < 2 else "lh.crimson")
    text.rstrip()
    return text


def dashboard_art() -> Text:
    use_compact = console.height < 36 or console.width < 78
    return reaper_text(compact=use_compact)


def print_art(compact: bool = False) -> None:
    console.print(reaper_text(compact=compact))
