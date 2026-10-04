"""
Historical backfill worker for TG-Voicer.
Walks through chat histories, finds un-transcribed voice messages, and processes them.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telethon import TelegramClient, utils
from telethon.tl import types

from .config import BackfillConfig
from .database import Database
from .filters import FilterEngine, get_chat_type
from .network import NetworkManager, is_network_error
from .transcriber import TelegramTranscriber
from . import ui

logger = logging.getLogger("tg_voicer.backfill")


class BackfillWorker:
    """Background scanner that processes historical voice messages in chats."""

    def __init__(
        self,
        client: TelegramClient,
        filter_engine: FilterEngine,
        transcriber: TelegramTranscriber,
        db: Database,
        config: BackfillConfig,
        network_manager: Optional[NetworkManager] = None,
        dry_run: bool = False,
    ):
        self.client = client
        self.filter_engine = filter_engine
        self.transcriber = transcriber
        self.db = db
        self.config = config
        self.network_manager = network_manager
        self.dry_run = dry_run
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def start(self) -> asyncio.Task:
        """Start the backfill worker as an asyncio background task."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        return self._task

    async def stop(self) -> None:
        """Gracefully stop the backfill worker."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("🛑 Background backfill stopped.")

    async def _run_loop(self) -> None:
        """Main loop that iterates through dialogs and processes history."""
        if self.config.randomize_delay:
            delay_str = f"случайная {self.config.delay_min_seconds:.1f}–{self.config.delay_max_seconds:.1f}с"
        else:
            delay_str = f"{self.config.delay_seconds:.1f}с"
        logger.info(
            f"🔄 Фоновый backfill запущен (пауза: {delay_str}, batch_size={self.config.batch_size})"
        )

        while self._running:
            try:
                completed_all = await self._scan_all_dialogs()
                if completed_all:
                    ui.print_all_completed()
                    logger.debug("All chat history backfilled. Standby mode.")
                    # Sleep in standby mode, checking for new chats every 15 minutes
                    for _ in range(15 * 60):
                        if not self._running:
                            break
                        await asyncio.sleep(1)
                else:
                    # If paused or reached limits
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if is_network_error(e):
                    logger.warning(f"⚠️ Сбой сети в цикле backfill: {e}. Ожидание интернета...")
                    if self.network_manager:
                        await self.network_manager.wait_for_connection()
                    else:
                        await asyncio.sleep(5)
                else:
                    logger.exception(f"Unexpected error in backfill worker: {e}")
                    await asyncio.sleep(10)

    async def _scan_all_dialogs(self) -> bool:
        """Iterate over all user dialogs and scan messages."""
        chats_scanned = 0
        total_eligible_dialogs = 0

        # Fetch dialogs with network retry
        dialogs = []
        while self._running:
            try:
                async for dialog in self.client.iter_dialogs():
                    dialogs.append(dialog)
                break
            except Exception as e:
                if is_network_error(e):
                    logger.warning(f"Ошибка сети при получении списка чатов: {e}. Ожидание интернета...")
                    if self.network_manager:
                        await self.network_manager.wait_for_connection()
                    else:
                        await asyncio.sleep(5)
                    dialogs.clear()
                    continue
                else:
                    logger.error(f"Не удалось получить список диалогов: {e}")
                    return False

        logger.info(f"📋 Обнаружено всего диалогов: {len(dialogs)}")

        for dialog in dialogs:
            if not self._running:
                return False

            chat_title = dialog.title or f"Chat_{dialog.id}"
            chat_id = utils.get_peer_id(dialog.entity)
            chat_type = get_chat_type(dialog.entity)

            # 1. Quick pre-filter check
            should_proc_chat, reason = self.filter_engine.should_process_dialog(dialog)
            if not should_proc_chat:
                logger.debug(f"⏭️ Пропуск чата '{chat_title}' ({chat_type}): {reason}")
                continue

            total_eligible_dialogs += 1
            if self.config.max_chats > 0 and chats_scanned >= self.config.max_chats:
                logger.info(f"Достигнут лимит чатов для сканирования ({self.config.max_chats})")
                return True

            # 2. Check cursor in database
            cursor = self.db.get_chat_cursor(chat_id)
            if cursor and cursor.get("history_completed") == 1:
                # History is already complete. Check if there are new recent messages since last run
                top_msg_id = getattr(dialog.message, "id", 0)
                newest_scanned = cursor.get("newest_scanned_id") or 0
                if top_msg_id > newest_scanned:
                    logger.debug(f"Досканирование новых сообщений в '{chat_title}'...")
                    await self._scan_chat_range(dialog, min_id=newest_scanned, max_id=top_msg_id + 1)
                continue

            # 3. Scan historical messages backwards
            chats_scanned += 1
            ui.print_scan_chat(chat_title=chat_title, chat_type=chat_type, chat_id=chat_id)
            await self._scan_chat_history(dialog, cursor)

        return True

    async def _scan_chat_history(self, dialog: Any, cursor: Optional[dict]) -> None:
        """Scan historical messages backwards from oldest_scanned_id."""
        chat_id = utils.get_peer_id(dialog.entity)
        chat_title = dialog.title or f"Chat_{chat_id}"
        chat_type = get_chat_type(dialog.entity)

        oldest_scanned_id = cursor.get("oldest_scanned_id") if cursor else None
        top_msg_id = getattr(dialog.message, "id", None)
        newest_scanned_id = cursor.get("newest_scanned_id") if cursor else top_msg_id

        messages_scanned = 0
        reached_end = False

        while self._running:
            if self.config.max_messages_per_chat > 0 and messages_scanned >= self.config.max_messages_per_chat:
                logger.info(f"Достигнут лимит сообщений ({self.config.max_messages_per_chat}) в '{chat_title}'")
                break

            limit = min(
                self.config.batch_size,
                self.config.max_messages_per_chat - messages_scanned if self.config.max_messages_per_chat > 0 else self.config.batch_size,
            )

            batch = []
            while self._running:
                try:
                    async for msg in self.client.iter_messages(
                        dialog.input_entity,
                        max_id=oldest_scanned_id or 0,
                        limit=limit,
                    ):
                        batch.append(msg)
                    break
                except Exception as e:
                    if is_network_error(e):
                        logger.warning(
                            f"Ошибка сети при чтении сообщений из '{chat_title}': {e}. "
                            f"Ожидание интернета..."
                        )
                        if self.network_manager:
                            await self.network_manager.wait_for_connection()
                        else:
                            await asyncio.sleep(5)
                        batch.clear()
                        continue
                    else:
                        logger.warning(f"Ошибка при чтении сообщений из '{chat_title}': {e}")
                        break

            if not batch:
                reached_end = True
                break

            for msg in batch:
                if not self._running:
                    break

                messages_scanned += 1
                if oldest_scanned_id is None or msg.id < oldest_scanned_id:
                    oldest_scanned_id = msg.id

                # Only examine voice or video note messages
                if not msg.voice and not msg.video_note:
                    continue

                await self._process_backfill_message(msg, dialog, chat_type)

            # Update cursor checkpoint in database
            self.db.update_chat_cursor(
                chat_id=chat_id,
                chat_title=chat_title,
                chat_type=chat_type,
                oldest_scanned_id=oldest_scanned_id,
                newest_scanned_id=newest_scanned_id,
                history_completed=reached_end,
                increment_scanned=len(batch),
            )

            if len(batch) < limit:
                reached_end = True
                break

        if reached_end:
            ui.print_chat_completed(chat_title=chat_title)
            self.db.update_chat_cursor(
                chat_id=chat_id,
                chat_title=chat_title,
                chat_type=chat_type,
                oldest_scanned_id=oldest_scanned_id,
                newest_scanned_id=newest_scanned_id,
                history_completed=True,
            )

    async def _scan_chat_range(self, dialog: Any, min_id: int, max_id: int) -> None:
        """Scan messages in range between min_id and max_id to catch up on new messages."""
        chat_type = get_chat_type(dialog.entity)
        chat_id = utils.get_peer_id(dialog.entity)
        newest_seen = min_id

        while self._running:
            try:
                async for msg in self.client.iter_messages(
                    dialog.input_entity,
                    min_id=min_id,
                    max_id=max_id,
                    limit=self.config.batch_size,
                ):
                    if not self._running:
                        break
                    if msg.id > newest_seen:
                        newest_seen = msg.id
                    if msg.voice or msg.video_note:
                        await self._process_backfill_message(msg, dialog, chat_type)
                break
            except Exception as e:
                if is_network_error(e):
                    logger.warning(f"Ошибка сети при досканировании новых сообщений: {e}. Ожидание интернета...")
                    if self.network_manager:
                        await self.network_manager.wait_for_connection()
                    else:
                        await asyncio.sleep(5)
                    continue
                else:
                    logger.warning(f"Ошибка при чтении сообщений диалога: {e}")
                    break

        self.db.update_chat_cursor(
            chat_id=chat_id,
            newest_scanned_id=newest_seen,
        )


    async def _process_backfill_message(self, msg: types.Message, dialog: Any, chat_type: str) -> None:
        """Process an individual voice or video message during backfill."""
        chat_id = utils.get_peer_id(dialog.entity)
        chat_title = dialog.title or f"Chat_{chat_id}"

        # Fast DB check: already processed?
        if self.db.is_message_processed(chat_id, msg.id):
            return

        try:
            sender = await msg.get_sender()
        except Exception:
            sender = None

        should_proc, reason, media_type, duration, existing_text = self.filter_engine.should_process_message(
            message=msg,
            chat=dialog.entity,
            sender=sender,
        )

        sender_name = utils.get_display_name(sender) if sender else "Unknown"

        # If message already has text/caption, save it and skip API request
        if existing_text and self.filter_engine.filters_cfg.skip_if_already_has_text:
            logger.info(
                f"ℹ️ [УЖЕ ЕСТЬ ТЕКСТ] msg_id={msg.id} в '{chat_title}' уже содержит текст/подпись: "
                f"\"{existing_text[:50]}...\". Запрос к Telegram пропущен."
            )
            self.db.save_message(
                chat_id=chat_id,
                msg_id=msg.id,
                media_type=media_type or "voice",
                sender_id=msg.sender_id,
                sender_name=sender_name,
                chat_title=chat_title,
                chat_type=chat_type,
                text=existing_text,
                status="done",
                is_live=False,
                duration_sec=duration,
                msg_date=msg.date,
            )
            return

        if not should_proc:
            logger.debug(f"[BACKFILL SKIP] msg_id={msg.id} in '{chat_title}': {reason}")
            self.db.mark_message_skipped(
                chat_id=chat_id,
                msg_id=msg.id,
                reason=reason,
                media_type=media_type,
                msg_date=msg.date,
                duration_sec=duration,
                sender_id=msg.sender_id,
                sender_name=sender_name,
                chat_title=chat_title,
                chat_type=chat_type,
            )
            return

        ui.print_voice_found(
            source="BACKFILL",
            media_type=media_type or "voice",
            duration=duration,
            sender_name=sender_name,
            chat_title=chat_title,
            msg_id=msg.id,
        )

        if self.dry_run:
            logger.info("   [DRY-RUN] Пропуск отправки запроса в API.")
            return

        # Pre-save into DB
        self.db.save_message(
            chat_id=chat_id,
            msg_id=msg.id,
            media_type=media_type or "voice",
            sender_id=msg.sender_id,
            sender_name=sender_name,
            chat_title=chat_title,
            chat_type=chat_type,
            status="pending",
            is_live=False,
            duration_sec=duration,
            msg_date=msg.date,
        )

        # Transcribe message
        result = await self.transcriber.transcribe(
            peer=dialog.input_entity,
            msg_id=msg.id,
            chat_id=chat_id,
            is_live=False,
        )

        sleep_time = self.config.delay_seconds

        ui.print_transcription_result(
            text=result.text,
            is_cached=result.was_already_transcribed,
            status=result.status,
            error=result.error_message,
        )

        sleep_time = self.config.get_delay(is_cached=result.was_already_transcribed)

        # Polite delay to respect Telegram rate limits and avoid FloodWait
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)
