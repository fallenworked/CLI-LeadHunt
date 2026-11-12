"""Настройки приложения: параметры поиска, сеть, интерфейс и данные."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import (
    DATA_DIR,
    DB_PATH,
    DEFAULT_SETTINGS,
    RESULTS_DIR,
)
from core.utils import file_size, human_bytes
from ui import prompts
from ui.dashboard import render_compact_header
from ui.theme import clear_screen, console, error, muted, section, success, warning


def _ask_int(message: str, default: int, minimum: int, maximum: int) -> int | None:
    def validate(value: str) -> bool | str:
        try:
            number = int(value.strip())
        except ValueError:
            return "Введи целое число"
        if not minimum <= number <= maximum:
            return f"Допустимо от {minimum} до {maximum}"
        return True

    value = prompts.text(message, str(default), validate=validate)
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _ask_float(message: str, default: float, minimum: float, maximum: float) -> float | None:
    def validate(value: str) -> bool | str:
        try:
            number = float(value.strip().replace(",", "."))
        except ValueError:
            return "Введи число"
        if not minimum <= number <= maximum:
            return f"Допустимо от {minimum} до {maximum}"
        return True

    value = prompts.text(message, str(default), validate=validate)
    if value is None:
        return None
    try:
        return float(value.strip().replace(",", "."))
    except ValueError:
        return None


def _settings_panel(app) -> Panel:
    settings = app.settings
    table = Table.grid(padding=(0, 3))
    table.add_column(style="lh.dim", no_wrap=True, width=24)
    table.add_column(style="lh.white")
    table.add_row("ГОРОД ПО УМОЛЧАНИЮ", str(settings.get("default_city", "")))
    table.add_row("НИША ПО УМОЛЧАНИЮ", str(settings.get("default_niche", "")))
    table.add_row("РАДИУС", f"{settings.get_int('default_radius', 5000):,} м".replace(",", " "))
    table.add_row("ЛИМИТ", str(settings.get_int("default_limit", 250)))
    table.add_row("ТОЛЬКО С ТЕЛЕФОНОМ", "да" if settings.get_bool("default_only_phone") else "нет")
    table.add_row("ТОЛЬКО С АДРЕСОМ", "да" if settings.get_bool("default_require_address") else "нет")
    table.add_row("ВКЛЮЧАТЬ САЙТЫ", "да" if settings.get_bool("default_include_website") else "нет")
    table.add_row("ТАЙМАУТ ЗАПРОСА", f"{settings.get_int('request_timeout', 30)} с")
    table.add_row("ИНТЕРВАЛ МЕЖДУ ПОИСКАМИ", f"{float(settings.get('min_request_interval', 1.2) or 1.2):.1f} с")
    table.add_row("СТРОК НА СТРАНИЦЕ", str(settings.get_int("page_size", 15)))
    table.add_row("АНИМАЦИИ", "включены" if settings.get_bool("animations", True) else "выключены")
    table.add_row("ЗЕРКАЛ", str(len(settings.get_list("endpoints") or DEFAULT_SETTINGS["endpoints"])))
    table.add_row("ИСТОЧНИК OSM", "включён" if settings.get_bool("source_osm_enabled", True) else "отключён")
    info = Table.grid(padding=(0, 3))
    info.add_column(style="lh.dim", no_wrap=True, width=24)
    info.add_column(style="lh.muted")
    info.add_row("БАЗА", f"{DB_PATH} · {human_bytes(file_size(DB_PATH))}")
    info.add_row("ДАННЫЕ", str(DATA_DIR))
    info.add_row("ОТЧЁТЫ", str(RESULTS_DIR))
    return Panel(
        _compose(table, info),
        title="[lh.accent]НАСТРОЙКИ[/]",
        subtitle="[lh.dim]изменения сохраняются в локальной SQLite сразу[/]",
        border_style="lh.border",
        padding=(0, 1),
    )


def _compose(*renderables):
    from rich.console import Group

    children = []
    for index, item in enumerate(renderables):
        if index:
            children.append(Text(""))
        children.append(item)
    return Group(*children)


def _edit_defaults(app) -> None:
    settings = app.settings
    city = prompts.text("Город по умолчанию", default=str(settings.get("default_city", "Москва")))
    if city is None:
        return
    settings.set("default_city", city.strip() or "Москва")

    niche = prompts.text("Ниша по умолчанию", default=str(settings.get("default_niche", "стоматология")))
    if niche is None:
        return
    settings.set("default_niche", niche.strip() or "стоматология")

    radius = _ask_int("Радиус по умолчанию, метров", settings.get_int("default_radius", 5000), 500, 20000)
    if radius is None:
        return
    settings.set("default_radius", radius)

    limit = _ask_int("Лимит лидов по умолчанию", settings.get_int("default_limit", 250), 10, 1000)
    if limit is None:
        return
    settings.set("default_limit", limit)

    phone = prompts.confirm("По умолчанию только с телефоном?", default=settings.get_bool("default_only_phone"))
    if phone is None:
        return
    settings.set("default_only_phone", phone)

    address = prompts.confirm(
        "По умолчанию только с адресом?",
        default=settings.get_bool("default_require_address"),
    )
    if address is None:
        return
    settings.set("default_require_address", address)

    website = prompts.confirm(
        "По умолчанию включать бизнесы с сайтом?",
        default=settings.get_bool("default_include_website"),
    )
    if website is None:
        return
    settings.set("default_include_website", website)
    success("Параметры поиска сохранены.")
    prompts.pause()


def _edit_network(app) -> None:
    settings = app.settings
    timeout = _ask_int(
        "Таймаут запроса к источнику, секунд (10–90)",
        settings.get_int("request_timeout", 30),
        10,
        90,
    )
    if timeout is None:
        return
    settings.set("request_timeout", timeout)

    interval = _ask_float(
        "Минимальный интервал между поисками, секунд (0.5–10)",
        float(settings.get("min_request_interval", 1.2) or 1.2),
        0.5,
        10.0,
    )
    if interval is None:
        return
    settings.set("min_request_interval", round(interval, 2))
    success("Сетевые настройки сохранены.")
    prompts.pause()


def _edit_interface(app) -> None:
    settings = app.settings
    page_size = _ask_int("Строк лидов на странице (5–50)", settings.get_int("page_size", 15), 5, 50)
    if page_size is None:
        return
    settings.set("page_size", page_size)

    animations = prompts.confirm("Показывать анимацию запуска?", default=settings.get_bool("animations", True))
    if animations is None:
        return
    settings.set("animations", animations)
    success("Настройки интерфейса сохранены.")
    prompts.pause()


def _reset_settings(app) -> None:
    confirmed = prompts.confirm(
        "Сбросить все настройки к значениям по умолчанию? Лиды и история не удаляются.",
        default=False,
    )
    if not confirmed:
        return
    for key, value in DEFAULT_SETTINGS.items():
        app.settings.set(key, value)
    success("Настройки сброшены.")
    prompts.pause()


def _danger_zone(app) -> None:
    action = prompts.select(
        "Работа с данными",
        [
            prompts.choice("⌫  Очистить историю поисков (лиды останутся)", "history"),
            prompts.choice("⌫  Удалить все лиды (история останется)", "leads"),
            prompts.choice("☠  Полностью очистить базу", "all"),
            prompts.choice("←  Назад", "back"),
        ],
    )
    if action in (None, "back"):
        return
    if action == "history":
        confirmed = prompts.confirm("Очистить всю историю поисков?", default=False)
        if confirmed:
            count = app.storage.clear_history()
            success(f"Удалено записей истории: {count}.")
            prompts.pause()
        return
    if action == "leads":
        confirmed = prompts.confirm("Удалить ВСЕ сохранённые лиды? Это необратимо.", default=False)
        if confirmed:
            count = app.storage.clear_leads()
            success(f"Удалено лидов: {count}.")
            prompts.pause()
        return

    warning("Полная очистка удалит лиды, историю и кеш городов. Отменить это нельзя.")
    phrase = prompts.text("Напиши УДАЛИТЬ, чтобы подтвердить полную очистку")
    if phrase is None:
        return
    if phrase.strip().upper() != "УДАЛИТЬ":
        warning("Фраза не совпала. Очистка отменена.")
        prompts.pause()
        return
    app.storage.clear_all()
    success("База очищена. Настройки сохранены.")
    prompts.pause()


def _maintenance(app) -> None:
    action = prompts.select(
        "Обслуживание базы",
        [
            prompts.choice("Сжать базу (VACUUM)", "vacuum"),
            prompts.choice("Показать путь к данным", "path"),
            prompts.choice("←  Назад", "back"),
        ],
    )
    if action in (None, "back"):
        return
    if action == "vacuum":
        with console.status("[lh.crimson]Сжимаю базу…[/]", spinner="dots2"):
            app.storage.vacuum()
        success(f"База сжата. Размер: {human_bytes(file_size(DB_PATH))}")
        prompts.pause()
    elif action == "path":
        console.print(f"[lh.dim]База:[/] [lh.white]{DB_PATH}[/]")
        console.print(f"[lh.dim]Данные:[/] [lh.white]{DATA_DIR}[/]")
        console.print(f"[lh.dim]Отчёты:[/] [lh.white]{RESULTS_DIR}[/]")
        prompts.pause()


def settings_screen(app) -> None:
    while True:
        clear_screen()
        render_compact_header(app.storage, app.settings)
        section("НАСТРОЙКИ", "локально, без аккаунтов и облака")
        console.print(_settings_panel(app))
        action = prompts.select(
            "Настройки",
            [
                prompts.choice("⌕  Параметры поиска по умолчанию", "defaults"),
                prompts.choice("⚙  Сеть, таймауты и интервал", "network"),
                prompts.choice("▤  Интерфейс и страницы", "interface"),
                prompts.choice("↺  Сбросить настройки", "reset"),
                prompts.choice("⚒  Обслуживание базы", "maintenance"),
                prompts.choice("☠  Очистка данных", "danger"),
                prompts.choice("←  Назад", "back"),
            ],
        )
        if action in (None, "back"):
            return
        if action == "defaults":
            _edit_defaults(app)
        elif action == "network":
            _edit_network(app)
        elif action == "interface":
            _edit_interface(app)
        elif action == "reset":
            _reset_settings(app)
        elif action == "maintenance":
            _maintenance(app)
        elif action == "danger":
            _danger_zone(app)
