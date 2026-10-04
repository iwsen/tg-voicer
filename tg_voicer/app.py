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

from tg_voicer import __version__
from .backfill import BackfillWorker
from .config import AppConfig
from .database import Database
from .filters import FilterEngine
from .network import NetworkManager, is_network_error
from .i18n import t
from .realtime import RealtimeListener
from .transcriber import TelegramTranscriber
from . import ui

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

        self.network_manager = NetworkManager(self.client)

        self.transcriber = TelegramTranscriber(
            client=self.client,
            db=self.db,
            network_manager=self.network_manager,
            wait_for_completion=self.config.realtime.wait_for_completion,
            timeout_seconds=self.config.realtime.timeout_seconds,
        )

        self.realtime_listener = RealtimeListener(
            client=self.client,
            filter_engine=self.filter_engine,
            transcriber=self.transcriber,
            db=self.db,
            network_manager=self.network_manager,
        )

        self.backfill_worker = BackfillWorker(
            client=self.client,
            filter_engine=self.filter_engine,
            transcriber=self.transcriber,
            db=self.db,
            config=self.config.backfill,
            network_manager=self.network_manager,
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
        while not self._shutdown_event.is_set():
            try:
                if not self.client.is_connected():
                    await self.client.connect()
                break
            except Exception as e:
                if is_network_error(e):
                    ui.print_network_offline(5)
                    logger.warning(f"Ошибка сети при подключении к Telegram: {e}. Повтор через 5с...")
                    await asyncio.sleep(5)
                else:
                    raise

        # Check authorization with network resilience
        is_auth = False
        while not self._shutdown_event.is_set():
            try:
                is_auth = await self.client.is_user_authorized()
                break
            except Exception as e:
                if is_network_error(e):
                    await self.network_manager.wait_for_connection()
                else:
                    raise

        if not is_auth:
            if getattr(self.config.telegram, "auth_method", "qr") == "phone":
                logger.info(t("login_phone_start"))
                await self.client.start()
            else:
                await self._login_with_qr()

        me = None
        while not self._shutdown_event.is_set():
            try:
                me = await self.client.get_me()
                break
            except Exception as e:
                if is_network_error(e):
                    await self.network_manager.wait_for_connection()
                else:
                    raise

        if not me:
            raise RuntimeError("Failed to fetch Telegram user profile")
        user_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
        user_handle = f"@{me.username}" if me.username else f"ID:{me.id}"
        is_premium = bool(getattr(me, "premium", False))

        if self.live_only:
            mode_desc = t("mode_live_only")
        elif self.backfill_only:
            mode_desc = t("mode_backfill_only")
        else:
            mode_desc = t("mode_all")

        filter_summaries = []
        if self.config.filters.ignore_types:
            filter_summaries.append(t("filter_ignore_types", types=", ".join(self.config.filters.ignore_types)))
        if self.config.filters.ignored_chats:
            filter_summaries.append(t("filter_ignored_chats", count=len(self.config.filters.ignored_chats)))
        if self.config.filters.ignored_users:
            filter_summaries.append(t("filter_ignored_users", count=len(self.config.filters.ignored_users)))
        if self.config.filters.allowed_chats:
            filter_summaries.append(t("filter_allowed_chats", count=len(self.config.filters.allowed_chats)))
        if self.config.filters.allowed_users:
            filter_summaries.append(t("filter_allowed_users", count=len(self.config.filters.allowed_users)))

        ui.print_banner(
            version=__version__,
            user_name=user_name,
            user_handle=user_handle,
            is_premium=is_premium,
            mode_desc=mode_desc,
            db_path=str(self.config.storage.db_path),
            filter_summaries=filter_summaries,
        )

        tasks = []

        # 1. Start Realtime Listener (unless --backfill-only or realtime disabled)
        if not self.backfill_only and self.config.realtime.enabled:
            self.realtime_listener.start()

        # 2. Start Background Backfill Worker (unless --live-only or backfill disabled)
        if not self.live_only and self.config.backfill.enabled:
            backfill_task = self.backfill_worker.start()
            tasks.append(backfill_task)

        # 3. Start background network connection watchdog
        self.network_manager.start_watchdog()

        ui.console.print(f"[dim]{t('app_ready')}[/dim]")

        # If backfill-only mode, wait for backfill task to finish
        if self.backfill_only:
            try:
                await tasks[0]
            except asyncio.CancelledError:
                pass
            return

        # Otherwise wait for shutdown event
        await self._shutdown_event.wait()

    async def _login_with_qr(self) -> None:
        """Authenticate with Telegram using QR code scan."""
        import getpass
        import sys
        import qrcode
        from telethon.errors import SessionPasswordNeededError

        print("\n" + "=" * 65)
        print(t("qr_header"))
        print("=" * 65)
        print(t("qr_step1"))
        print(t("qr_step2"))
        print(t("qr_step3"))
        print("=" * 65 + "\n")

        svg_opened = False
        svg_path = Path("data/login_qr.svg")
        svg_path.parent.mkdir(parents=True, exist_ok=True)

        while not await self.client.is_user_authorized():
            try:
                qr_login = await self.client.qr_login()

                # Print ASCII QR code directly in terminal
                qr = qrcode.QRCode()
                qr.add_data(qr_login.url)
                qr.print_ascii(invert=True)

                # Save SVG vector image for convenient scanning from screen
                try:
                    import qrcode.image.svg
                    img = qrcode.make(qr_login.url, image_factory=qrcode.image.svg.SvgPathImage)
                    img.save(str(svg_path))
                    print("\n" + t("qr_saved_file", path=svg_path.absolute()))
                    if not svg_opened and sys.platform == "darwin":
                        import subprocess
                        subprocess.Popen(["open", str(svg_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        svg_opened = True
                except Exception as e:
                    logger.debug(f"Could not generate SVG QR: {e}")

                print("\n" + t("qr_waiting"))

                try:
                    await qr_login.wait()
                    print("\n" + t("qr_scanned"))
                    break
                except SessionPasswordNeededError:
                    print("\n" + t("qr_2fa_notice"))
                    password = getpass.getpass(t("qr_2fa_prompt")).strip()
                    await self.client.sign_in(password=password)
                    print(t("qr_2fa_accepted"))
                    break
                except asyncio.TimeoutError:
                    print("\n" + t("qr_timeout"))
                    continue
            except SessionPasswordNeededError:
                print("\n" + t("qr_2fa_notice"))
                password = getpass.getpass(t("qr_2fa_prompt")).strip()
                await self.client.sign_in(password=password)
                print(t("qr_2fa_accepted"))
                break
            except Exception as e:
                logger.error(t("qr_error", error=e))
                raise

    async def stop(self) -> None:
        """Stop application components cleanly."""
        logger.info(t("app_stopping"))
        await self.network_manager.stop()
        self.realtime_listener.stop()
        await self.backfill_worker.stop()
        await self.client.disconnect()
        self.db.close()
        self._shutdown_event.set()
        logger.info(t("app_session_safe"))
