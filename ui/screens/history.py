"""История поисков: детали, повтор, экспорт и удаление записей."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.models import SearchParams
from core.utils import clean_text, fmt_datetime, human_duration, truncate
from ui import prompts
from ui.dashboard import render_compact_header
from ui.theme import clear_screen, console, muted, section
from ui.widgets import SEARCH_STATUS, searches_panel


def _detail_panel(search: dict[str, Any], lead_count: int) -> Panel:
    status_key = str(search.get("status") or "running")
    label, style = SEARCH_STATUS.get(status_key, ("?", "lh.smoke"))
    table = Table.grid(padding=(0, 2))
    table.add_column(style="lh.dim", no_wrap=True, width=16)
    table.add_column(style="lh.white")

    def add(name: str, value: str, value_style: str = "lh.white") -> None:
        table.add_row(name.upper(), Text(value or "—", style=value_style))

    add("Поиск", f"#{search.get('id')}")
    table.add_row("СТАТУС", Text(label, style=style))
    add("Создан", fmt_datetime(search.get("created_at")))
    add("Город", clean_text(search.get("city")))
    add("Регион", clean_text(search.get("region")))
    add("Страна", clean_text(search.get("country")))
    add("Ниша", clean_text(search.get("niche")))
    add("Ключевые слова", clean_text(search.get("keywords")))
    add("Радиус", f"{int(search.get('radius') or 0):,} м".replace(",", " "))
    add("Лимит", str(search.get("limit_value") or 0))
    add("Найдено источником", str(search.get("total_found") or 0))
    add("После дедупа", str(search.get("after_dedup") or 0))
    add("После фильтров", str(search.get("saved") or 0))
    add("Новых в базе", str(search.get("new_leads") or 0), "lh.ok")
    add("Дубликатов", str(search.get("duplicates") or 0))
    add("С телефоном", str(search.get("with_phone") or 0))
    add("С email", str(search.get("with_email") or 0))
    add("Лидов привязано", str(lead_count))
    add("Длительность", human_duration(search.get("duration_ms") or 0))
    query = clean_text(search.get("query"))
    if query:
        add("Overpass-запрос", truncate(query, 120), "lh.muted")

    children: list[Any] = [table]
    errors = search.get("errors") or []
    if errors:
        children.extend(
            [
                Text(""),
                Panel(
                    "\n".join(f"· {error}" for error in errors),
                    title="[lh.danger]ОШИБКИ ПОИСКА[/]",
                    border_style="lh.border.hot",
                    padding=(0, 1),
                ),
            ]
        )
    return Panel(
        Group(*children),
        title=f"[lh.accent]ПОИСК #{search.get('id')}[/]",
        border_style="lh.border.hot" if errors else "lh.border",
        padding=(0, 1),
    )


def _choose_search(searches: list[dict[str, Any]]) -> dict[str, Any] | None:
    choices = []
    for search in searches:
        label = (
            f"#{search.get('id'):>3} · {fmt_datetime(search.get('created_at'), '%d.%m.%Y %H:%M')} · "
            f"{clean_text(search.get('city')) or '—'} · {clean_text(search.get('niche')) or '—'} · "
            f"{search.get('total_found') or 0} найдено"
        )
        choices.append(prompts.choice(label, str(search.get("id"))))
    value = prompts.select("Выбери поиск", choices)
    if value is None:
        return None
    return next((item for item in searches if str(item.get("id")) == value), None)


def _params_from_history(search: dict[str, Any]) -> SearchParams:
    data = search.get("params") or {}

    def number(key: str, fallback: int) -> int:
        try:
            return int(data.get(key, search.get(key, fallback)) or fallback)
        except (TypeError, ValueError):
            return fallback

    def flag(key: str, fallback: bool = False) -> bool:
        value = data.get(key, fallback)
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "on"}

    return SearchParams(
        city=clean_text(data.get("city") or search.get("city")),
        niche=clean_text(data.get("niche") or search.get("niche")),
        category_key=clean_text(data.get("category_key") or search.get("category_key")),
        keywords=clean_text(data.get("keywords") or search.get("keywords")),
        radius=number("radius", 5000),
        limit=number("limit", 250),
        only_with_phone=flag("only_with_phone"),
        require_address=flag("require_address"),
        include_website=flag("include_website"),
        source_ids=["osm"],
    )


def _search_actions(app, search: dict[str, Any]) -> None:
    from ui.screens.export import export_rows_interactive
    from ui.screens.leads import browse_leads
    from ui.screens.search import run_search_with_params
    from ui.theme import success, warning

    search_id = int(search["id"])
    lead_count = app.storage.count_leads({"search_id": search_id})
    while True:
        clear_screen()
        render_compact_header(app.storage, app.settings)
        console.print(_detail_panel(search, lead_count))
        action = prompts.select(
            "Действие с поиском",
            [
                prompts.choice("▣  Показать лиды этого поиска", "leads"),
                prompts.choice("↻  Повторить с теми же параметрами", "rerun"),
                prompts.choice("⇩  Экспорт CSV", "csv"),
                prompts.choice("⇩  Экспорт HTML", "html"),
                prompts.choice("✖  Удалить запись истории", "delete"),
                prompts.choice("←  Назад к истории", "back"),
            ],
        )
        if action in (None, "back"):
            return
        if action == "leads":
            browse_leads(
                app,
                {"search_id": search_id},
                title=f"ЛИДЫ ПОИСКА #{search_id}",
            )
        elif action == "rerun":
            params = _params_from_history(search)
            if not params.city or not params.niche:
                warning("В записи истории нет города или ниши — повторить поиск нельзя.")
                prompts.pause()
                continue
            run_search_with_params(app, params)
            return
        elif action in {"csv", "html"}:
            rows = app.storage.list_leads({"search_id": search_id}, limit=100000)
            if not rows:
                warning("У этого поиска нет сохранённых лидов.")
                prompts.pause()
                continue
            export_rows_interactive(
                app,
                rows,
                title=f"Поиск #{search_id}: {clean_text(search.get('niche'))} · {clean_text(search.get('city'))}",
                prefix=f"history_{search_id}",
                formats=[action],
            )
        elif action == "delete":
            confirmed = prompts.confirm(
                f"Удалить запись истории #{search_id}? Сами лиды останутся в базе.",
                default=False,
            )
            if not confirmed:
                continue
            app.storage.delete_search(search_id)
            success("Запись истории удалена. Лиды сохранены.")
            prompts.pause()
            return


def history_screen(app) -> None:
    from ui.theme import success

    while True:
        searches = app.storage.list_searches(limit=100)
        clear_screen()
        render_compact_header(app.storage, app.settings)
        section("ИСТОРИЯ ПОИСКОВ", "каждый запуск сохраняется локально; лиды не удаляются вместе с историей")
        console.print(searches_panel(searches))
        muted(f"Показано записей: {len(searches)}")
        action = prompts.select(
            "История",
            [
                prompts.choice("▣  Открыть поиск", "open"),
                prompts.choice("⌫  Очистить всю историю", "clear"),
                prompts.choice("←  Назад", "back"),
            ],
        )
        if action in (None, "back"):
            return
        if action == "open":
            if not searches:
                continue
            search = _choose_search(searches)
            if search is not None:
                _search_actions(app, search)
        elif action == "clear":
            if not searches:
                continue
            confirmed = prompts.confirm(
                f"Удалить все {len(searches)} записей истории? Лиды останутся в базе.",
                default=False,
            )
            if confirmed:
                count = app.storage.clear_history()
                success(f"Удалено записей: {count}. Лиды сохранены.")
                prompts.pause()
