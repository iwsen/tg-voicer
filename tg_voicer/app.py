"""
Main application class for TG-Voicer.
Coordinates Telegram connection, listener, and backfill background worker.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional

from telethon import TelegramClient

from .backfill import BackfillWorker
from .config import AppConfig
from .database import Database
from .filters import FilterEngine
from .realtime import RealtimeListener
from .transcriber import TelegramTranscriber

logger = logging.getLogger("tg_voicer.app")


class VoicerApp:
    """Core application orchestrator."""

    def __init__(
        self,
        config: AppConfig,
        live_only: bool = False,
        backfill_only: bool = False,
        dry_run: bool = False,
    ):
        self.config = config
        self.live_only = live_only
        self.backfill_only = backfill_only
        self.dry_run = dry_run

        self.db = Database(self.config.storage.db_path)
        self.filter_engine = FilterEngine(self.config.filters, self.config.telegram)

        session_path = Path("data") / self.config.telegram.session_name
        session_path.parent.mkdir(parents=True, exist_ok=True)

        self.client = TelegramClient(
            str(session_path),
            self.config.telegram.api_id,
            self.config.telegram.api_hash,
        )

        self.transcriber = TelegramTranscriber(
            client=self.client,
            db=self.db,
            wait_for_completion=self.config.realtime.wait_for_completion,
            timeout_seconds=self.config.realtime.timeout_seconds,
        )

        self.realtime_listener = RealtimeListener(
            client=self.client,
            filter_engine=self.filter_engine,
            transcriber=self.transcriber,
            db=self.db,
        )

        self.backfill_worker = BackfillWorker(
            client=self.client,
            filter_engine=self.filter_engine,
            transcriber=self.transcriber,
            db=self.db,
            config=self.config.backfill,
            dry_run=self.dry_run,
        )

        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the application and connect to Telegram."""
        # Ensure credentials exist
        if not self.config.telegram.api_id or not self.config.telegram.api_hash:
            raise ValueError(
                "API credentials missing! Please configure api_id and api_hash in config.toml"
            )

        logger.info("Connecting to Telegram...")
        await self.client.start()

        me = await self.client.get_me()
        user_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
        user_handle = f"@{me.username}" if me.username else f"ID:{me.id}"
        is_premium = bool(getattr(me, "premium", False))

        logger.info(f"👤 Вошли как: {user_name} ({user_handle})")
        if is_premium:
            logger.info("🌟 Статус: Telegram Premium АКТИВЕН (нативная расшифровка доступна)")
        else:
            logger.warning(
                "⚠️ ВНИМАНИЕ: На этом аккаунте не обнаружена активная подписка Telegram Premium! "
                "Кнопка расшифровки сообщений в Telegram требует Premium."
            )

        # Log filter configuration summary
        if self.config.filters.ignore_types:
            logger.info(f"🚫 Игнорируемые типы чатов: {', '.join(self.config.filters.ignore_types)}")
        if self.config.filters.ignored_chats:
            logger.info(f"🚫 Игнорируемые чаты: {len(self.config.filters.ignored_chats)} правил")
        if self.config.filters.ignored_users:
            logger.info(f"🚫 Игнорируемые пользователи: {len(self.config.filters.ignored_users)} правил")
        if self.config.filters.allowed_chats:
            logger.info(f"🎯 Белый список чатов активен ({len(self.config.filters.allowed_chats)} чатов)")
        if self.config.filters.allowed_users:
            logger.info(f"🎯 Белый список пользователей активен ({len(self.config.filters.allowed_users)} пользователей)")

        tasks = []

        # 1. Start Realtime Listener (unless --backfill-only or realtime disabled)
        if not self.backfill_only and self.config.realtime.enabled:
            self.realtime_listener.start()

        # 2. Start Background Backfill Worker (unless --live-only or backfill disabled)
        if not self.live_only and self.config.backfill.enabled:
            backfill_task = self.backfill_worker.start()
            tasks.append(backfill_task)

        logger.info("🚀 TG-Voicer запущен и готов к работе! Для выхода нажмите Ctrl+C.")

        # If backfill-only mode, wait for backfill task to finish
        if self.backfill_only:
            try:
                await tasks[0]
            except asyncio.CancelledError:
                pass
            return

        # Otherwise wait for shutdown event
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        """Stop application components cleanly."""
        logger.info("🛑 Остановка сервисов TG-Voicer...")
        self.realtime_listener.stop()
        await self.backfill_worker.stop()
        await self.client.disconnect()
        self._shutdown_event.set()
        logger.info("👋 Сессия Telegram безопасно завершена.")
