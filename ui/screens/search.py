"""Экран поиска: мастер параметров, живой прогресс и результаты."""

from __future__ import annotations

import math
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from config import STATUSES
from core.dictionaries import NICHES, find_niche
from core.models import SearchOutcome, SearchParams
from core.settings import Settings
from core.utils import clean_text, human_duration
from ui import prompts
from ui.dashboard import render_compact_header
from ui.theme import clear_screen, console
from ui.widgets import leads_panel

CUSTOM_NICHE = "__custom__"


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
    if value is None or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _summary(params: SearchParams) -> Panel:
    table = Table.grid(padding=(0, 3))
    table.add_column(style="lh.dim", no_wrap=True)
    table.add_column(style="lh.white")
    filters = []
    if params.only_with_phone:
        filters.append("только с телефоном")
    if params.require_address:
        filters.append("только с адресом")
    if params.include_website:
        filters.append("включая сайты")
    if params.keywords:
        filters.append(f"ключевые слова: {params.keywords}")
    table.add_row("ГОРОД", params.city)
    table.add_row("НИША", params.niche)
    table.add_row("РАДИУС", f"{params.radius:,} м".replace(",", " "))
    table.add_row("ЛИМИТ", str(params.limit))
    table.add_row("ФИЛЬТРЫ", " · ".join(filters) if filters else "без дополнительных фильтров")
    table.add_row("ИСТОЧНИК", "OpenStreetMap / Overpass")
    return Panel(
        table,
        title="[lh.accent]ПАРАМЕТРЫ ОХОТЫ[/]",
        border_style="lh.border",
        padding=(0, 1),
    )


def run_search_wizard(app) -> None:
    settings: Settings = app.settings
    if not settings.get_bool("source_osm_enabled", True):
        from ui.theme import warning

        warning(
            "OpenStreetMap отключён. Включи источник в разделе «Управление источниками», "
            "иначе поиск невозможен."
        )
        prompts.pause()
        return

    city = prompts.text(
        "Город (можно любой, неизвестный будет геокодирован)",
        default=str(settings.get("default_city", "Москва")),
        validate=lambda value: bool(value.strip()) or "Город не может быть пустым",
    )
    if city is None:
        return
    city = clean_text(city)

    niche_choices = [prompts.choice(niche.label, niche.key) for niche in NICHES]
    niche_choices.append(prompts.choice("▸ Другая ниша / ключевой запрос", CUSTOM_NICHE))
    default_niche = str(settings.get("default_niche", "стоматология"))
    default_key = default_niche if find_niche(default_niche) else None
    niche_key = prompts.select("Ниша", niche_choices, default=default_key)
    if niche_key is None:
        return

    if niche_key == CUSTOM_NICHE:
        custom = prompts.text(
            "Ключевое слово для поиска по названию",
            default="" if find_niche(default_niche) else default_niche,
            validate=lambda value: bool(value.strip()) or "Введи ключевое слово",
        )
        if custom is None:
            return
        niche = clean_text(custom)
        category_key = ""
    else:
        niche_obj = find_niche(niche_key)
        niche = niche_obj.key if niche_obj else niche_key
        category_key = niche

    radius = settings.get_int("default_radius", 5000)
    limit = settings.get_int("default_limit", 250)
    only_phone = settings.get_bool("default_only_phone", False)
    require_address = settings.get_bool("default_require_address", False)
    include_website = settings.get_bool("default_include_website", False)
    keywords = ""

    advanced = prompts.confirm("Настроить радиус, лимит и фильтры?", default=False)
    if advanced is None:
        return
    if advanced:
        radius_value = _ask_int("Радиус поиска, метров (500–20000)", radius, 500, 20000)
        if radius_value is None:
            return
        radius = radius_value
        limit_value = _ask_int("Максимум лидов в результате (10–1000)", limit, 10, 1000)
        if limit_value is None:
            return
        limit = limit_value
        only_phone_value = prompts.confirm("Только лиды с телефоном?", default=only_phone)
        if only_phone_value is None:
            return
        only_phone = only_phone_value
        address_value = prompts.confirm("Только лиды с адресом?", default=require_address)
        if address_value is None:
            return
        require_address = address_value
        website_value = prompts.confirm("Включать бизнесы с сайтом?", default=include_website)
        if website_value is None:
            return
        include_website = website_value
        keywords_value = prompts.text(
            "Доп. ключевые слова через запятую (пусто — не фильтровать)",
            default=keywords,
        )
        if keywords_value is None:
            return
        keywords = clean_text(keywords_value)

    params = SearchParams(
        city=city,
        niche=niche,
        category_key=category_key,
        keywords=keywords,
        radius=radius,
        limit=limit,
        only_with_phone=only_phone,
        require_address=require_address,
        include_website=include_website,
        source_ids=["osm"],
    )

    clear_screen()
    render_compact_header(app.storage, app.settings)
    console.print(_summary(params))
    start = prompts.confirm("Запустить охоту?", default=True)
    if not start:
        return
    run_search_with_params(app, params)


@dataclass
class _ProgressState:
    started: float = field(default_factory=time.monotonic)
    city: str = ""
    phase: str = "Подготовка"
    source: str = ""
    source_status: str = ""
    found: int = 0
    processed: int = 0
    mirrors: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    finished: bool = False


def _progress_panel(state: _ProgressState, params: SearchParams) -> Panel:
    elapsed = time.monotonic() - state.started
    header = Table.grid(padding=(0, 2))
    header.add_column(width=3)
    header.add_column(style="lh.white")
    header.add_column(justify="right", style="lh.muted")
    spinner = Spinner("dots2", style="lh.red")
    header.add_row(spinner, Text("ОХОТА ИДЁТ", style="bold lh.white"), Text(f"{elapsed:0.1f} с", style="lh.muted"))
    city_line = state.city or f"{params.city} · координаты ещё не получены"
    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="lh.dim", no_wrap=True)
    meta.add_column(style="lh.white")
    meta.add_row("ЦЕЛЬ", f"{params.niche} · {city_line}")
    meta.add_row("ИСТОЧНИК", state.source or "OpenStreetMap / Overpass")
    meta.add_row("ФАЗА", state.phase)
    meta.add_row(
        "СЧЁТЧИК",
        f"[lh.white]{state.found}[/] лидов · [lh.dim]объектов обработано:[/] [lh.white]{state.processed}[/]",
    )
    children: list[Any] = [header, Text(""), meta]
    if state.mirrors:
        mirror_table = Table(
            box=None,
            show_header=True,
            header_style="lh.dim",
            padding=(0, 1),
            expand=True,
        )
        mirror_table.add_column("ЗЕРКАЛО", style="lh.smoke", ratio=2)
        mirror_table.add_column("СТАТУС", width=10)
        mirror_table.add_column("ДЕТАЛИ", style="lh.muted", ratio=3)
        icons = {"pending": ("…", "lh.muted"), "ok": ("✔", "lh.ok"), "error": ("✖", "lh.danger")}
        for endpoint, info in state.mirrors.items():
            host = urlparse(endpoint).netloc or endpoint
            icon, style = icons.get(info.get("status"), ("…", "lh.muted"))
            mirror_table.add_row(
                host,
                Text(icon, style=style),
                str(info.get("message") or "ожидание"),
            )
        children.extend([Text(""), mirror_table])
    if state.errors:
        children.extend(
            [
                Text(""),
                Panel(
                    "\n".join(state.errors),
                    title="[lh.danger]ОШИБКИ[/]",
                    border_style="lh.border.hot",
                    padding=(0, 1),
                ),
            ]
        )
    return Panel(
        Group(*children),
        title="[lh.accent]◈ ПОИСК ЛИДОВ[/]",
        subtitle="[lh.dim]Ctrl+C — отменить · прогресс обновляется в реальном времени[/]",
        border_style="lh.border.hot",
        padding=(0, 1),
    )


def run_search_with_params(app, params: SearchParams) -> SearchOutcome | None:
    state = _ProgressState()
    events: "queue.Queue[dict]" = queue.Queue()
    cancel = threading.Event()
    holder: dict[str, Any] = {}

    def worker() -> None:
        engine = None
        try:
            engine = app.create_engine()
            outcome = engine.search(params, progress=events.put, cancel=cancel)
            holder["outcome"] = outcome
        except Exception as exc:  # noqa: BLE001
            holder["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if engine is not None and getattr(engine, "storage", None) is not app.storage:
                try:
                    engine.storage.close()
                except Exception:
                    pass

    thread = threading.Thread(target=worker, daemon=True, name="lead-hunter-search")
    thread.start()
    clear_screen()
    render_compact_header(app.storage, app.settings)

    cancelled = False
    try:
        with Live(
            _progress_panel(state, params),
            console=console,
            refresh_per_second=10,
            transient=False,
            vertical_overflow="visible",
        ) as live:
            while thread.is_alive() or not events.empty():
                try:
                    event = events.get(timeout=0.08)
                except queue.Empty:
                    live.update(_progress_panel(state, params))
                    continue
                _apply_event(state, event)
                live.update(_progress_panel(state, params))
    except KeyboardInterrupt:
        cancelled = True
        cancel.set()
        console.print("\n[lh.warn]Отмена поиска…[/]")
        thread.join(timeout=3.0)
    thread.join(timeout=0.5)

    if cancelled:
        from ui.theme import warning

        warning("Поиск отменён. Незавершённые данные не сохранены.")
        prompts.pause()
        return None

    if "error" in holder:
        from ui.theme import error as show_error

        show_error(holder["error"])
        prompts.pause()
        return None

    outcome: SearchOutcome | None = holder.get("outcome")
    if outcome is None:
        from ui.theme import error as show_error

        show_error("Поиск не вернул результат. Проверь журнал data/lead_hunter.log.")
        prompts.pause()
        return None

    console.print(_outcome_panel(outcome))
    if outcome.errors:
        from rich.panel import Panel as RichPanel

        console.print(
            RichPanel(
                "\n".join(outcome.errors),
                title="[lh.danger]ОШИБКИ ИСТОЧНИКОВ[/]",
                border_style="lh.border.hot",
                padding=(0, 1),
            )
        )
    if outcome.source_notes:
        console.print(
            Panel(
                "\n".join(f"· {note}" for note in outcome.source_notes),
                title="[lh.dim]ЗАМЕТКИ[/]",
                border_style="lh.border",
                padding=(0, 1),
            )
        )

    if not outcome.leads:
        if outcome.status == "error":
            console.print(
                "[lh.warn]Совет:[/] открой «Управление источниками» → «Проверить зеркала», "
                "или попробуй другой город / радиус."
            )
        prompts.pause()
        return outcome

    _results_actions(app, outcome)
    return outcome


def _apply_event(state: _ProgressState, event: dict) -> None:
    kind = event.get("type")
    if kind == "phase":
        state.phase = str(event.get("message") or event.get("phase") or state.phase)
    elif kind == "resolved":
        city = event.get("city") or {}
        state.city = ", ".join(
            str(part) for part in (city.get("name"), city.get("country")) if part
        )
    elif kind == "source_start":
        state.source = str(event.get("source") or "")
        state.phase = "Идёт запрос к источнику"
    elif kind == "mirror":
        endpoint = str(event.get("endpoint") or "")
        state.mirrors[endpoint] = {
            "status": event.get("status"),
            "message": event.get("message") or event.get("error") or "",
        }
        if event.get("status") == "ok":
            state.found = max(state.found, int(event.get("count") or 0))
    elif kind == "count":
        state.found = max(state.found, int(event.get("found") or 0))
        state.processed = max(state.processed, int(event.get("processed") or 0))
        state.phase = "Разбор и проверка данных"
    elif kind == "source_done":
        state.source = str(event.get("source") or state.source)
        state.found = max(state.found, int(event.get("found") or 0))
        state.phase = "Источник завершил работу"
    elif kind == "source_error":
        message = str(event.get("error") or "неизвестная ошибка")
        if message not in state.errors:
            state.errors.append(f"{event.get('source')}: {message}")
        state.phase = "Ошибка источника — продолжаю"
    elif kind == "fatal":
        message = str(event.get("error") or "неизвестная ошибка")
        if message not in state.errors:
            state.errors.append(message)
        state.phase = "Внутренняя ошибка"
    elif kind == "cancelled":
        state.phase = "Отменено"
    elif kind == "done":
        state.finished = True
        state.phase = "Готово"


def _outcome_panel(outcome: SearchOutcome) -> Panel:
    stats = outcome.stats
    city = outcome.city_info.name if outcome.city_info else outcome.params.city
    table = Table.grid(padding=(0, 3))
    table.add_column(style="lh.dim", no_wrap=True)
    table.add_column(style="lh.white")
    table.add_row("ЦЕЛЬ", f"{outcome.params.niche} · {city}")
    table.add_row("НАЙДЕНО", f"[bold lh.white]{stats.raw_found}[/]")
    table.add_row("ПОСЛЕ ДЕДУПА", f"{stats.after_dedup}")
    table.add_row("ПОСЛЕ ФИЛЬТРОВ", f"{stats.saved}")
    table.add_row("НОВЫХ В БАЗЕ", f"[lh.ok]{stats.new_leads}[/]")
    table.add_row("ДУБЛИКАТОВ", f"{stats.duplicates}")
    table.add_row("С ТЕЛЕФОНОМ", f"{stats.with_phone}")
    table.add_row("ВРЕМЯ", human_duration(outcome.duration_ms))
    if stats.filter_reasons:
        table.add_row(
            "ОТФИЛЬТРОВАНО",
            " · ".join(f"{reason}: {count}" for reason, count in stats.filter_reasons.items()),
        )
    table.add_row("SEARCH ID", str(outcome.search_id))
    status_label = {
        "ok": ("ЗАВЕРШЁН", "lh.ok"),
        "empty": ("ПУСТО", "lh.warn"),
        "error": ("ОШИБКА", "lh.danger"),
        "cancelled": ("ОТМЕНЁН", "lh.warn"),
    }.get(outcome.status, (outcome.status, "lh.smoke"))
    table.add_row("СТАТУС", Text(status_label[0], style=status_label[1]))
    border = "lh.border.hot" if outcome.errors or outcome.status == "error" else "lh.border"
    title = "◈ РЕЗУЛЬТАТ ОХОТЫ" if outcome.leads else "◈ ОХОТА ЗАВЕРШЕНА"
    return Panel(
        table,
        title=f"[lh.accent]{title}[/]",
        border_style=border,
        padding=(0, 1),
    )


def _results_actions(app, outcome: SearchOutcome) -> None:
    filters = {"search_id": outcome.search_id}
    while True:
        page_size = max(5, app.settings.get_int("page_size", 10))
        rows = app.storage.list_leads(filters, limit=page_size, offset=0)
        total = app.storage.count_leads(filters)
        console.print(leads_panel(rows, total, 1, max(1, math.ceil(total / page_size)), title="РЕЗУЛЬТАТЫ ПОИСКА"))
        choices = [
            prompts.choice("▣  Просмотреть все результаты", "browse"),
            prompts.choice("⇩  Экспорт CSV", "csv"),
            prompts.choice("⇩  Экспорт HTML", "html"),
            prompts.choice("↻  Повторить поиск", "repeat"),
            prompts.choice("←  В главное меню", "back"),
        ]
        action = prompts.select("Что дальше?", choices)
        if action in (None, "back"):
            return
        if action == "browse":
            from ui.screens.leads import browse_leads

            browse_leads(app, filters, title=f"ЛИДЫ ПОИСКА #{outcome.search_id}")
        elif action == "csv":
            from ui.screens.export import export_rows_interactive

            rows_all = app.storage.list_leads(filters, limit=100000)
            export_rows_interactive(
                app,
                rows_all,
                title=f"Поиск #{outcome.search_id}: {outcome.params.niche} · {outcome.params.city}",
                prefix=f"search_{outcome.search_id}_{outcome.params.niche}_{outcome.params.city}",
                formats=["csv"],
            )
        elif action == "html":
            from ui.screens.export import export_rows_interactive

            rows_all = app.storage.list_leads(filters, limit=100000)
            export_rows_interactive(
                app,
                rows_all,
                title=f"Поиск #{outcome.search_id}: {outcome.params.niche} · {outcome.params.city}",
                prefix=f"search_{outcome.search_id}_{outcome.params.niche}_{outcome.params.city}",
                formats=["html"],
            )
        elif action == "repeat":
            run_search_with_params(app, outcome.params)
            return
