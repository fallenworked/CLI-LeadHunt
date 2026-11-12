"""Экран экспорта лидов: CSV, автономный HTML-отчёт и выбор охвата."""

from __future__ import annotations

import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from rich.table import Table

from config import RESULTS_DIR, STATUSES
from core.utils import clean_text, fmt_datetime, human_bytes
from exporters.common import default_export_path
from exporters.csv_export import export_csv
from exporters.html_export import export_html
from ui import prompts
from ui.dashboard import render_compact_header
from ui.theme import clear_screen, console, error, muted, section, success, warning


def _ensure_extension(path: Path, extension: str) -> Path:
    if path.suffix.lower() != f".{extension}":
        return path.with_suffix(f".{extension}")
    return path


def _resolve_path(raw: str, prefix: str, extension: str) -> Path:
    value = raw.strip()
    if not value:
        return default_export_path(RESULTS_DIR, prefix, extension)
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = RESULTS_DIR / candidate
    if candidate.is_dir():
        return default_export_path(candidate, prefix, extension)
    return _ensure_extension(candidate, extension)


def _ask_formats(formats: Iterable[str] | None) -> list[str] | None:
    if formats is not None:
        return list(formats)
    value = prompts.select(
        "Формат экспорта",
        [
            prompts.choice("HTML-отчёт (автономный, тёмная тема)", "html"),
            prompts.choice("CSV (Excel, UTF-8 BOM)", "csv"),
            prompts.choice("Оба формата", "both"),
        ],
    )
    if value is None:
        return None
    return ["html"] if value == "html" else ["csv"] if value == "csv" else ["html", "csv"]


def export_rows_interactive(
    app,
    rows: list[dict[str, Any]],
    title: str,
    prefix: str,
    formats: Iterable[str] | None = None,
) -> list[Path]:
    """Экспортирует переданные лиды. Возвращает список созданных файлов."""
    if not rows:
        warning("Нет данных для экспорта.")
        prompts.pause()
        return []
    selected = _ask_formats(formats)
    if not selected:
        return []

    console.print(
        f"[lh.dim]К экспорту:[/] [lh.white]{len(rows)}[/] [lh.dim]лидов · "
        f"[lh.dim]формат:[/] [lh.white]{', '.join(selected)}[/]"
    )
    rename = prompts.confirm("Указать свои имена файлов? (иначе — авто в папке results)", default=False)
    if rename is None:
        return []

    created: list[Path] = []
    for extension in selected:
        default_path = default_export_path(RESULTS_DIR, prefix, extension)
        path = default_path
        if rename:
            raw = prompts.text(
                f"Путь для {extension.upper()} (пусто — {default_path.name})",
                default="",
            )
            if raw is None:
                continue
            path = _resolve_path(raw, prefix, extension)
        try:
            if extension == "html":
                path = export_html(
                    rows,
                    path,
                    title=title,
                    subtitle=f"Сгенерировано локально · {datetime.now().astimezone().strftime('%d.%m.%Y %H:%M')}",
                )
            else:
                path = export_csv(rows, path)
        except OSError as exc:
            error(f"Не удалось записать {extension.upper()}: {exc}")
            continue
        created.append(path)
        success(f"{extension.upper()} сохранён: [lh.white]{path}[/] · {human_bytes(path.stat().st_size)}")

    if not created:
        prompts.pause()
        return []

    html_files = [path for path in created if path.suffix.lower() == ".html"]
    open_report = prompts.confirm(
        "Открыть HTML-отчёт в браузере?" if html_files else "Открыть папку с файлами?",
        default=True,
    )
    if open_report:
        try:
            if html_files:
                webbrowser.open(html_files[0].resolve().as_uri())
            else:
                webbrowser.open(created[0].parent.resolve().as_uri())
        except Exception as exc:  # noqa: BLE001 - браузер может отсутствовать
            warning(f"Не удалось открыть файл автоматически: {exc}")
            muted(str(created[0].parent))
    prompts.pause()
    return created


def export_screen(app) -> None:
    while True:
        clear_screen()
        render_compact_header(app.storage, app.settings)
        section("ЭКСПОРТ ЛИДОВ", "CSV для таблиц · HTML-отчёт с поиском и фильтрами работает без интернета")

        scope = prompts.select(
            "Что экспортировать?",
            [
                prompts.choice("Все сохранённые лиды", "all"),
                prompts.choice("Лиды одного города", "city"),
                prompts.choice("Лиды одной ниши", "niche"),
                prompts.choice("Лиды с определённым статусом", "status"),
                prompts.choice("Результаты конкретного поиска", "search"),
                prompts.choice("←  Назад", "back"),
            ],
        )
        if scope in (None, "back"):
            return

        filters: dict[str, Any] = {}
        title = "Все лиды"
        prefix = "all_leads"

        if scope == "city":
            cities = app.storage.distinct_values("city")
            if cities:
                console.print("[lh.dim]Города в базе:[/] " + ", ".join(cities[:20]))
            value = prompts.text("Город", validate=lambda item: bool(item.strip()) or "Укажи город")
            if value is None:
                continue
            filters["city"] = clean_text(value)
            title = f"Город: {filters['city']}"
            prefix = f"city_{filters['city']}"
        elif scope == "niche":
            niches = app.storage.distinct_values("niche")
            if niches:
                console.print("[lh.dim]Ниши в базе:[/] " + ", ".join(niches[:20]))
            value = prompts.text("Ниша", validate=lambda item: bool(item.strip()) or "Укажи нишу")
            if value is None:
                continue
            filters["niche"] = clean_text(value)
            title = f"Ниша: {filters['niche']}"
            prefix = f"niche_{filters['niche']}"
        elif scope == "status":
            key = prompts.select(
                "Статус",
                [prompts.choice(label, code) for code, label in STATUSES.items()],
            )
            if key is None:
                continue
            filters["status"] = key
            title = f"Статус: {STATUSES.get(key, key)}"
            prefix = f"status_{key}"
        elif scope == "search":
            searches = app.storage.list_searches(limit=100)
            if not searches:
                warning("История поисков пуста. Сначала выполни поиск.")
                prompts.pause()
                continue
            value = prompts.select(
                "Поиск",
                [
                    prompts.choice(
                        f"#{item['id']} · {fmt_datetime(item.get('created_at'), '%d.%m.%Y %H:%M')} · "
                        f"{clean_text(item.get('city')) or '—'} · {clean_text(item.get('niche')) or '—'} · "
                        f"{item.get('total_found') or 0} найдено",
                        str(item["id"]),
                    )
                    for item in searches
                ],
            )
            if value is None:
                continue
            filters["search_id"] = int(value)
            search = app.storage.get_search(int(value))
            title = (
                f"Поиск #{value}: {clean_text((search or {}).get('niche'))} · "
                f"{clean_text((search or {}).get('city'))}"
            )
            prefix = f"search_{value}"

        rows = app.storage.list_leads(filters, limit=100000)
        if not rows:
            warning("По выбранному охвату лидов нет.")
            prompts.pause()
            continue

        summary = Table.grid(padding=(0, 3))
        summary.add_column(style="lh.dim")
        summary.add_column(style="lh.white")
        summary.add_row("ОХВАТ", title)
        summary.add_row("ЛИДОВ", str(len(rows)))
        summary.add_row(
            "С ТЕЛЕФОНОМ",
            str(sum(1 for row in rows if clean_text(row.get("phone")))),
        )
        console.print(summary)

        export_rows_interactive(
            app,
            rows,
            title=title,
            prefix=prefix,
        )
