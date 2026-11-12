"""Приложение Lead Hunter: инициализация, главный цикл и изоляция ошибок."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from config import (
    APP_EDITION,
    APP_NAME,
    DATA_DIR,
    DB_PATH,
    TAGLINE,
    VERSION,
    configure_windows_console,
    ensure_directories,
)
from core.engine import LeadEngine
from core.settings import Settings
from core.utils import now_iso
from database.storage import Storage
from ui import prompts
from ui.dashboard import render_dashboard, show_boot
from ui.menu import main_menu
from ui.theme import clear_screen, console, error

logger = logging.getLogger("lead_hunter.app")


def setup_logging() -> None:
    ensure_directories()
    logger_root = logging.getLogger("lead_hunter")
    if logger_root.handlers:
        return
    logger_root.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        DATA_DIR / "lead_hunter.log",
        maxBytes=1_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s · %(levelname)s · %(name)s · %(message)s")
    )
    logger_root.addHandler(handler)
    logger_root.propagate = False


class LeadHunterApp:
    def __init__(self) -> None:
        configure_windows_console()
        ensure_directories()
        setup_logging()
        self.storage = Storage(DB_PATH)
        self.settings = Settings(self.storage)
        logger.info("Lead Hunter %s запущен; база: %s", VERSION, self.storage.path)

    def create_engine(self) -> LeadEngine:
        return LeadEngine(self.storage, self.settings)

    def dispatch(self, action: str) -> None:
        if action == "search":
            from ui.screens.search import run_search_wizard

            run_search_wizard(self)
        elif action == "leads":
            from ui.screens.leads import browse_leads

            browse_leads(self)
        elif action == "saved_search":
            from ui.screens.leads import search_saved_leads

            search_saved_leads(self)
        elif action == "history":
            from ui.screens.history import history_screen

            history_screen(self)
        elif action == "export":
            from ui.screens.export import export_screen

            export_screen(self)
        elif action == "sources":
            from ui.screens.sources import sources_screen

            sources_screen(self)
        elif action == "settings":
            from ui.screens.settings import settings_screen

            settings_screen(self)
        elif action == "stats":
            from ui.screens.stats import stats_screen

            stats_screen(self)
        else:
            logger.warning("Неизвестное действие меню: %s", action)

    def run(self, boot: bool = True) -> int:
        self.settings.set("last_run", now_iso())
        try:
            if boot and self.settings.get_bool("animations", True):
                show_boot(self.settings)
            clear_screen()
            render_dashboard(self.storage, self.settings)
            prompts.pause("Нажми ENTER, чтобы открыть главное меню")
        except (KeyboardInterrupt, EOFError):
            self.close()
            return 0

        while True:
            try:
                action = main_menu(self)
            except (KeyboardInterrupt, EOFError):
                action = "exit"
            if action in (None, "exit"):
                break
            try:
                self.dispatch(action)
            except (KeyboardInterrupt, EOFError):
                clear_screen()
                console.print("[lh.dim]Возврат в главное меню.[/]")
            except Exception as exc:  # noqa: BLE001 - UI не должен падать целиком
                logger.exception("Ошибка в экране %s", action)
                clear_screen()
                error(
                    f"Экран завершился с ошибкой: {type(exc).__name__}: {exc}\n\n"
                    f"Подробности: {DATA_DIR / 'lead_hunter.log'}"
                )
                prompts.pause()

        self.goodbye()
        self.close()
        return 0

    def goodbye(self) -> None:
        stats = self.storage.stats()
        clear_screen()
        content = Text()
        content.append(APP_NAME + " ", style="lh.logo")
        content.append(APP_EDITION, style="lh.crimson")
        content.append(f"  v{VERSION}\n", style="lh.muted")
        content.append(TAGLINE + "\n\n", style="italic lh.smoke")
        content.append(
            f"Сохранённых лидов: {stats.get('total', 0)} · поисков: {stats.get('searches', 0)}\n",
            style="lh.smoke",
        )
        content.append("Данные остаются в локальной базе. До следующей охоты.", style="lh.dim")
        console.print(
            Panel(
                Align.center(Group(content)),
                title="[lh.accent]◈ СЕАНС ЗАВЕРШЁН[/]",
                border_style="lh.border.hot",
                padding=(1, 3),
            )
        )

    def close(self) -> None:
        try:
            self.storage.close()
        except Exception:
            pass
        logger.info("Lead Hunter остановлен")


def run_app() -> int:
    app = LeadHunterApp()
    try:
        return app.run()
    except Exception:
        logger.exception("Критическая ошибка приложения")
        raise
