"""Управление источником OpenStreetMap/Overpass и реальная проверка зеркал."""

from __future__ import annotations

from urllib.parse import urlparse

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import DEFAULT_ENDPOINTS
from sources.osm_overpass import test_endpoints
from sources.registry import SOURCE_CATALOG
from ui import prompts
from ui.dashboard import render_compact_header
from ui.theme import clear_screen, console, muted, section, success, warning


def _endpoints(app) -> list[str]:
    return app.settings.get_list("endpoints") or list(DEFAULT_ENDPOINTS)


def _status_panel(app) -> Panel:
    enabled = app.settings.get_bool("source_osm_enabled", True)
    endpoints = _endpoints(app)
    catalog = SOURCE_CATALOG[0]
    table = Table.grid(padding=(0, 2))
    table.add_column(style="lh.dim", no_wrap=True, width=16)
    table.add_column(style="lh.white")
    table.add_row(
        "СТАТУС",
        Text.from_markup(
            "[lh.ok]● ВКЛЮЧЁН[/]" if enabled else "[lh.warn]● ОТКЛЮЧЁН[/]"
        ),
    )
    table.add_row("ИСТОЧНИК", catalog["name"])
    table.add_row("ТИП", str(catalog["type"]))
    table.add_row("КЛЮЧ", "не требуется")
    table.add_row("ЗЕРКАЛА", str(len(endpoints)))
    table.add_row("ОПИСАНИЕ", str(catalog["description"]))

    mirrors = Table(
        box=None,
        show_header=True,
        header_style="lh.dim",
        padding=(0, 1),
        expand=True,
    )
    mirrors.add_column("#", justify="right", width=3, style="lh.muted")
    mirrors.add_column("ЗЕРКАЛО", style="lh.smoke", ratio=2)
    mirrors.add_column("ХОСТ", style="lh.muted", ratio=1)
    for index, endpoint in enumerate(endpoints, start=1):
        mirrors.add_row(str(index), endpoint, urlparse(endpoint).netloc or "—")
    if not endpoints:
        mirrors.add_row("—", "Список пуст", "—")
    return Panel(
        _compose(table, mirrors),
        title="[lh.accent]ИСТОЧНИК ДАННЫХ[/]",
        subtitle="[lh.dim]статус ниже — только реальные ответы сети[/]",
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


def _test(app) -> None:
    endpoints = _endpoints(app)
    if not endpoints:
        warning("Список зеркал пуст. Добавь хотя бы одно зеркало Overpass.")
        prompts.pause()
        return
    timeout = max(8, min(25, app.settings.get_int("request_timeout", 30)))
    clear_screen()
    render_compact_header(app.storage, app.settings)
    section("ПРОВЕРКА ЗЕРКАЛ", f"реальный запрос к {len(endpoints)} зеркалам · таймаут {timeout} с")
    with console.status("[lh.crimson]Проверяю Overpass API…[/]", spinner="dots2"):
        results = test_endpoints(endpoints, timeout=timeout)

    table = Table(
        box=None,
        show_header=True,
        header_style="lh.dim",
        padding=(0, 1),
        expand=True,
    )
    table.add_column("ЗЕРКАЛО", style="lh.smoke", ratio=2)
    table.add_column("СТАТУС", width=9)
    table.add_column("ЗАДЕРЖКА", justify="right", width=10, style="lh.muted")
    table.add_column("ОТВЕТ", ratio=3)
    for item in results:
        ok = bool(item.get("ok"))
        table.add_row(
            urlparse(str(item.get("endpoint"))).netloc,
            Text("✔ OK" if ok else "✖ FAIL", style="lh.ok" if ok else "lh.danger"),
            f"{int(item.get('latency_ms') or 0)} мс" if ok else "—",
            Text(str(item.get("message") or "—"), style="lh.smoke" if ok else "lh.danger"),
        )
    console.print(
        Panel(
            table,
            title="[lh.accent]РЕЗУЛЬТАТ ПРОВЕРКИ[/]",
            border_style="lh.border",
            padding=(0, 1),
        )
    )
    working = sum(1 for item in results if item.get("ok"))
    if working:
        success(f"Рабочих зеркал: {working} из {len(results)}. Поиск будет использовать их параллельно.")
    else:
        warning(
            "Ни одно зеркало не ответило. Проверь интернет, VPN/файрвол или добавь другое зеркало. "
            "Приложение не подменяет ошибку выдуманными данными."
        )
    prompts.pause()


def _add_endpoint(app) -> None:
    endpoints = _endpoints(app)

    def validate(value: str) -> bool | str:
        value = value.strip()
        if not value.startswith(("https://", "http://")):
            return "URL должен начинаться с https:// или http://"
        if value in endpoints:
            return "Такое зеркало уже есть в списке"
        return True

    value = prompts.text("URL зеркала Overpass", validate=validate)
    if value is None:
        return
    endpoints.append(value.strip())
    app.settings.set("endpoints", endpoints)
    success("Зеркало добавлено. Проверь его кнопкой «Проверить зеркала».")
    prompts.pause()


def _remove_endpoint(app) -> None:
    endpoints = _endpoints(app)
    if not endpoints:
        return
    value = prompts.select(
        "Какое зеркало удалить?",
        [prompts.choice(endpoint, endpoint) for endpoint in endpoints],
    )
    if value is None:
        return
    endpoints = [endpoint for endpoint in endpoints if endpoint != value]
    app.settings.set("endpoints", endpoints)
    success(f"Зеркало удалено: {value}")
    prompts.pause()


def _reset_endpoints(app) -> None:
    confirmed = prompts.confirm("Вернуть список зеркал по умолчанию?", default=True)
    if not confirmed:
        return
    app.settings.set("endpoints", list(DEFAULT_ENDPOINTS))
    success("Список зеркал восстановлен.")
    prompts.pause()


def _toggle_source(app) -> None:
    enabled = app.settings.get_bool("source_osm_enabled", True)
    if enabled:
        confirmed = prompts.confirm(
            "Отключить OpenStreetMap? Поиск лидов станет невозможен, пока источник выключен.",
            default=False,
        )
        if confirmed:
            app.settings.set("source_osm_enabled", False)
            warning("Источник отключён. Сохранённые лиды и история остаются доступны.")
            prompts.pause()
    else:
        app.settings.set("source_osm_enabled", True)
        success("OpenStreetMap включён.")
        prompts.pause()


def _info() -> None:
    text = Text()
    text.append("OpenStreetMap / Overpass\n", style="bold lh.white")
    text.append(
        "\nИсточник не требует регистрации, ключей и оплаты. Данные предоставляют "
        "участники OpenStreetMap по лицензии ODbL.\n\n",
        style="lh.smoke",
    )
    text.append("Правила использования:\n", style="bold lh.crimson")
    for line in (
        "• приложение отправляет только реальные запросы Overpass и не обходит лимиты;",
        "• между поисками выдерживается минимальный интервал (настройка «интервал»);",
        "• при публикации данных указывай «© OpenStreetMap contributors»;",
        "• публичные зеркала могут быть недоступны — это показывается как ошибка, а не скрывается.",
    ):
        text.append(line + "\n", style="lh.smoke")
    text.append(
        "\nЕсли нужно больше запросов, используй собственный Overpass-сервер или официальные "
        "каналы OpenStreetMap.",
        style="lh.dim",
    )
    console.print(
        Panel(
            text,
            title="[lh.accent]О ИСТОЧНИКЕ[/]",
            border_style="lh.border",
            padding=(0, 1),
        )
    )
    prompts.pause()


def sources_screen(app) -> None:
    while True:
        clear_screen()
        render_compact_header(app.storage, app.settings)
        section("УПРАВЛЕНИЕ ИСТОЧНИКАМИ", "реальные публичные API · без ключей и регистрации")
        console.print(_status_panel(app))
        muted("Проверка зеркал выполняет настоящий запрос и показывает фактический результат.")
        action = prompts.select(
            "Источники",
            [
                prompts.choice("◎  Проверить зеркала (реальная сеть)", "test"),
                prompts.choice("＋  Добавить зеркало", "add"),
                prompts.choice("−  Удалить зеркало", "remove"),
                prompts.choice("↺  Сбросить зеркала по умолчанию", "reset"),
                prompts.choice("◐  Включить / отключить OpenStreetMap", "toggle"),
                prompts.choice("ℹ  Правила и лицензия", "info"),
                prompts.choice("←  Назад", "back"),
            ],
        )
        if action in (None, "back"):
            return
        if action == "test":
            _test(app)
        elif action == "add":
            _add_endpoint(app)
        elif action == "remove":
            _remove_endpoint(app)
        elif action == "reset":
            _reset_endpoints(app)
        elif action == "toggle":
            _toggle_source(app)
        elif action == "info":
            _info()
