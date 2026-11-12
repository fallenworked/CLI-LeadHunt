"""Точка входа Lead Hunter Local Edition.

Интерактивный режим:      python main.py
Поиск без меню:            python main.py --search "Москва" --niche кафе
Проверка зеркал Overpass:  python main.py --check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import (
    APP_EDITION,
    APP_NAME,
    DEFAULT_ENDPOINTS,
    RESULTS_DIR,
    TAGLINE,
    VERSION,
    configure_windows_console,
    ensure_directories,
)
from core.models import SearchParams
from core.utils import human_bytes, human_duration
from exporters.common import default_export_path
from exporters.csv_export import export_csv
from exporters.html_export import export_html
from sources.osm_overpass import test_endpoints
from ui.theme import console


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lead-hunter",
        description=f"{APP_NAME} {APP_EDITION} — локальный поиск лидов через OpenStreetMap.",
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_EDITION} v{VERSION}")
    parser.add_argument(
        "--search",
        nargs="?",
        const="",
        metavar="ГОРОД",
        help="выполнить поиск без меню и выйти (город можно передать и через --city)",
    )
    parser.add_argument("--city", help="город для --search")
    parser.add_argument("--niche", help="ниша или ключевое слово (по умолчанию из настроек)")
    parser.add_argument("--keywords", default="", help="дополнительные ключевые слова через запятую")
    parser.add_argument("--radius", type=int, help="радиус поиска в метрах (500–20000)")
    parser.add_argument("--limit", type=int, help="максимум лидов (10–1000)")
    parser.add_argument("--only-phone", action="store_true", help="только лиды с телефоном")
    parser.add_argument("--require-address", action="store_true", help="только лиды с адресом")
    parser.add_argument("--include-website", action="store_true", help="включать бизнесы с сайтом")
    parser.add_argument(
        "--format",
        choices=("none", "csv", "html", "both"),
        default="none",
        help="экспортировать результат после поиска",
    )
    parser.add_argument("--check", action="store_true", help="проверить доступность зеркал Overpass и выйти")
    parser.add_argument("--no-anim", action="store_true", help="не показывать анимацию запуска")
    return parser


def _print_banner(subtitle: str = "") -> None:
    text = Text()
    text.append(APP_NAME, style="lh.logo")
    text.append("  " + APP_EDITION, style="lh.crimson")
    text.append(f"  v{VERSION}\n", style="lh.muted")
    text.append(TAGLINE, style="italic lh.smoke")
    if subtitle:
        text.append(f"\n{subtitle}", style="lh.dim")
    console.print(
        Panel(
            text,
            title="[lh.accent]◈ LEAD HUNTER // CLI[/]",
            border_style="lh.border.hot",
            padding=(0, 2),
        )
    )


def _progress(event: dict) -> None:
    kind = event.get("type")
    if kind == "phase":
        console.print(f"[lh.crimson]›[/] [lh.smoke]{event.get('message', '')}[/]")
    elif kind == "resolved":
        console.print(f"[lh.ok]✔[/] [lh.smoke]{event.get('message', '')}[/]")
    elif kind == "source_start":
        console.print(f"[lh.crimson]◈[/] [lh.white]{event.get('source', '')}[/]")
    elif kind == "mirror":
        if event.get("status") == "error":
            host = urlparse(str(event.get("endpoint") or "")).netloc or event.get("endpoint")
            console.print(f"  [lh.danger]✖[/] [lh.muted]{host}: {event.get('message', '')}[/]")
        elif event.get("status") == "ok":
            host = urlparse(str(event.get("endpoint") or "")).netloc or event.get("endpoint")
            console.print(
                f"  [lh.ok]✔[/] [lh.muted]{host}: {event.get('message', '')}[/]"
            )
    elif kind == "count":
        console.print(
            f"  [lh.dim]объектов:[/] [lh.white]{event.get('processed', 0)}[/] "
            f"[lh.dim]· лидов:[/] [lh.white]{event.get('found', 0)}[/]"
        )
    elif kind == "source_done":
        console.print(f"[lh.ok]✔[/] [lh.smoke]{event.get('message', '')}[/]")
    elif kind == "source_error":
        console.print(f"[lh.danger]✖[/] [lh.smoke]{event.get('message', '')}[/]")
    elif kind == "fatal":
        console.print(f"[lh.danger]✖[/] [lh.smoke]{event.get('message', '')}[/]")


def _print_outcome(outcome) -> None:
    stats = outcome.stats
    city = outcome.city_info.name if outcome.city_info else outcome.params.city
    table = Table.grid(padding=(0, 3))
    table.add_column(style="lh.dim", no_wrap=True)
    table.add_column(style="lh.white")
    table.add_row("ЦЕЛЬ", f"{outcome.params.niche} · {city}")
    table.add_row("НАЙДЕНО", str(stats.raw_found))
    table.add_row("ПОСЛЕ ДЕДУПА", str(stats.after_dedup))
    table.add_row("ПОСЛЕ ФИЛЬТРОВ", str(stats.saved))
    table.add_row("НОВЫХ В БАЗЕ", f"[lh.ok]{stats.new_leads}[/]")
    table.add_row("ДУБЛИКАТОВ", str(stats.duplicates))
    table.add_row("С ТЕЛЕФОНОМ", str(stats.with_phone))
    table.add_row("ВРЕМЯ", human_duration(outcome.duration_ms))
    table.add_row("SEARCH ID", str(outcome.search_id))
    table.add_row("СТАТУС", outcome.status.upper())
    console.print(
        Panel(
            table,
            title="[lh.accent]РЕЗУЛЬТАТ[/]",
            border_style="lh.border.hot" if outcome.errors else "lh.border",
            padding=(0, 1),
        )
    )
    if outcome.errors:
        console.print(
            Panel(
                "\n".join(f"· {item}" for item in outcome.errors),
                title="[lh.danger]ОШИБКИ[/]",
                border_style="lh.border.hot",
                padding=(0, 1),
            )
        )
    if outcome.source_notes:
        console.print(
            Panel(
                "\n".join(f"· {item}" for item in outcome.source_notes),
                title="[lh.dim]ЗАМЕТКИ[/]",
                border_style="lh.border",
                padding=(0, 1),
            )
        )


def _cli_export(outcome, mode: str) -> list[Path]:
    rows = [lead.to_dict() for lead in outcome.leads]
    if not rows:
        return []
    title = f"{outcome.params.niche} · {outcome.params.city}"
    prefix = f"{outcome.params.niche}_{outcome.params.city}"
    created: list[Path] = []
    extensions = ["csv"] if mode == "csv" else ["html"] if mode == "html" else ["csv", "html"]
    for extension in extensions:
        path = default_export_path(RESULTS_DIR, prefix, extension)
        if extension == "csv":
            path = export_csv(rows, path)
        else:
            path = export_html(rows, path, title=title)
        created.append(path)
        console.print(
            f"[lh.ok]✔[/] {extension.upper()}: [lh.white]{path}[/] "
            f"[lh.dim]· {human_bytes(path.stat().st_size)}[/]"
        )
    return created


def _cli_check(app) -> int:
    _print_banner("Проверка доступности публичных зеркал Overpass API")
    endpoints = app.settings.get_list("endpoints") or list(DEFAULT_ENDPOINTS)
    timeout = max(8, min(25, app.settings.get_int("request_timeout", 30)))
    with console.status("[lh.crimson]Выполняю реальные запросы…[/]", spinner="dots2"):
        results = test_endpoints(endpoints, timeout=timeout)
    table = Table(
        box=None,
        show_header=True,
        header_style="lh.dim",
        expand=True,
        padding=(0, 1),
    )
    table.add_column("ЗЕРКАЛО", style="lh.smoke", ratio=2)
    table.add_column("СТАТУС", width=9)
    table.add_column("ЗАДЕРЖКА", justify="right", width=10, style="lh.muted")
    table.add_column("ОТВЕТ", ratio=3)
    for item in results:
        ok = bool(item.get("ok"))
        table.add_row(
            str(item.get("endpoint")),
            Text("OK" if ok else "FAIL", style="lh.ok" if ok else "lh.danger"),
            f"{int(item.get('latency_ms') or 0)} мс" if ok else "—",
            str(item.get("message") or ""),
        )
    console.print(Panel(table, title="[lh.accent]ЗЕРКАЛА OVERPASS[/]", border_style="lh.border", padding=(0, 1)))
    working = sum(1 for item in results if item.get("ok"))
    console.print(
        f"[lh.dim]Рабочих зеркал:[/] [lh.white]{working}[/] [lh.dim]из[/] [lh.white]{len(results)}[/]"
    )
    return 0 if working else 1


def _cli_search(app, args: argparse.Namespace) -> int:
    city = (args.city or args.search or "").strip()
    if not city:
        console.print("[lh.danger]Ошибка:[/] укажи город: --search Москва или --city Москва")
        return 2
    settings = app.settings
    niche = (args.niche or str(settings.get("default_niche", "стоматология"))).strip()
    radius = args.radius or settings.get_int("default_radius", 5000)
    limit = args.limit or settings.get_int("default_limit", 250)
    if not 500 <= radius <= 20000:
        console.print("[lh.danger]Ошибка:[/] радиус должен быть от 500 до 20000 метров")
        return 2
    if not 10 <= limit <= 1000:
        console.print("[lh.danger]Ошибка:[/] лимит должен быть от 10 до 1000")
        return 2

    params = SearchParams(
        city=city,
        niche=niche,
        category_key="",
        keywords=args.keywords.strip(),
        radius=radius,
        limit=limit,
        only_with_phone=bool(args.only_phone),
        require_address=bool(args.require_address),
        include_website=bool(args.include_website),
        source_ids=["osm"],
    )
    _print_banner(f"Город: {city} · ниша: {niche} · радиус: {radius} м · лимит: {limit}")
    engine = app.create_engine()
    outcome = engine.search(params, progress=_progress)
    _print_outcome(outcome)
    if args.format != "none" and outcome.leads:
        _cli_export(outcome, args.format)
    if outcome.status == "error" and not outcome.leads:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_windows_console()
    ensure_directories()
    parser = build_parser()
    args = parser.parse_args(argv)

    # Импорт приложения после разбора аргументов, чтобы --version работал быстро.
    from ui.app import LeadHunterApp, setup_logging

    setup_logging()
    app = LeadHunterApp()
    try:
        if args.check:
            return _cli_check(app)
        if args.search is not None:
            return _cli_search(app, args)
        return app.run(boot=not args.no_anim)
    except KeyboardInterrupt:
        console.print("\n[lh.dim]Прервано пользователем.[/]")
        return 130
    finally:
        app.close()


if __name__ == "__main__":
    sys.exit(main())
