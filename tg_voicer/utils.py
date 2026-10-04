"""
Utility functions and logging configuration for TG-Voicer.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from .config import LoggingConfig


class ColoredFormatter(logging.Formatter):
    """Clean terminal logging with ANSI colors."""

    COLORS = {
        logging.DEBUG: "\033[36m",     # Cyan
        logging.INFO: "\033[32m",      # Green
        logging.WARNING: "\033[33m",   # Yellow
        logging.ERROR: "\033[31m",     # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, "")
        reset = self.RESET if color else ""
        levelname = f"{color}{record.levelname:<7}{reset}"
        record.color_levelname = levelname  # type: ignore
        return super().format(record)


def setup_logging(cfg: LoggingConfig) -> None:
    """Configure console and file logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, cfg.level, logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_format = "%(asctime)s [%(color_levelname)s] %(name)s: %(message)s"
    console_formatter = ColoredFormatter(console_format, datefmt="%H:%M:%S")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler
    if cfg.log_to_file and cfg.log_file_path:
        log_path = Path(cfg.log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
        file_format = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
        file_formatter = logging.Formatter(file_format, datefmt="%Y-%m-%d %H:%M:%S")
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Mute noisy telethon logs
    logging.getLogger("telethon.network").setLevel(logging.WARNING)
    logging.getLogger("telethon.extensions").setLevel(logging.WARNING)


def print_stats_table(stats: Dict[str, Any], recent: List[Dict[str, Any]]) -> None:
    """Print formatted statistics to console."""
    print("\n" + "=" * 65)
    print(" 📊 TG-VOICER СТАТИСТИКА")
    print("=" * 65)
    print(f"  ✅ Успешно расшифровано:        {stats.get('transcribed_done', 0)}")
    print(f"  ⚡ Перехвачено в реальном времени: {stats.get('live_captured', 0)}")
    print(f"  ⏳ В процессе обработки:        {stats.get('transcribed_pending', 0)}")
    print(f"  ⏭️ Пропущено фильтрами:         {stats.get('skipped', 0)}")
    print(f"  ⚠️ Ошибок:                      {stats.get('failed', 0)}")
    print(f"  📁 Всего обработано чатов:      {stats.get('chats_total', 0)}")
    print(f"  🏁 Чатов с пройденной историей: {stats.get('chats_history_completed', 0)}")
    print("=" * 65)

    if recent:
        print("\n 📝 Последние расшифровки:")
        print("-" * 65)
        for i, item in enumerate(recent, 1):
            media = "🎤" if item.get("media_type") == "voice" else "📹"
            chat = item.get("chat_title") or f"Chat {item.get('chat_id')}"
            sender = item.get("sender_name") or "Unknown"
            dur = f"{item.get('duration_sec', 0):.0f}с"
            text = (item.get("text") or "").strip().replace("\n", " ")
            if len(text) > 75:
                text = text[:72] + "..."
            live_tag = " [LIVE]" if item.get("is_live") else ""
            print(f"  {i}. {media} {chat} | {sender} ({dur}){live_tag}:")
            print(f"     \"{text}\"")
        print("=" * 65 + "\n")
