"""
Utility functions and logging configuration for TG-Voicer.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from rich.logging import RichHandler

from .config import LoggingConfig
from .ui import console, print_stats_table, print_voice_heatmap


def setup_logging(cfg: LoggingConfig) -> None:
    """Configure console and file logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, cfg.level, logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Rich Console handler
    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        log_time_format="[%H:%M:%S]",
        omit_repeated_times=False,
        markup=False,
    )
    console_formatter = logging.Formatter("%(message)s")
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
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("telethon.client.updates").setLevel(logging.WARNING)
    logging.getLogger("telethon.network").setLevel(logging.WARNING)
    logging.getLogger("telethon.extensions").setLevel(logging.WARNING)

