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
from .transcriber import TelegramTranscriber

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
        dry_run: bool = False,
    ):
        self.client = client
        self.filter_engine = filter_engine
        self.transcriber = transcriber
        self.db = db
        self.config = config
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
        logger.info(
            f"🔄 Background backfill initialized "
            f"(delay={self.config.delay_seconds}s, batch_size={self.config.batch_size})"
        )

        while self._running:
            try:
                completed_all = await self._scan_all_dialogs()
                if completed_all:
                    logger.info("🎉 [BACKFILL] Вся доступная история чатов полностью обработана!")
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
                logger.exception(f"Unexpected error in backfill worker: {e}")
                await asyncio.sleep(10)

    async def _scan_all_dialogs(self) -> bool:
        """Iterate over all user dialogs and scan messages."""
        chats_scanned = 0
        total_eligible_dialogs = 0

        # Fetch dialogs
        dialogs = []
        async for dialog in self.client.iter_dialogs():
            dialogs.append(dialog)

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
            logger.info(f"🔍 [BACKFILL] Сканирование чата: '{chat_title}' ({chat_type}) [id={chat_id}]...")
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
            try:
                async for msg in self.client.iter_messages(
                    dialog.input_entity,
                    max_id=oldest_scanned_id or 0,
                    limit=limit,
                ):
                    batch.append(msg)
            except Exception as e:
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
            logger.info(f"🏁 Завершена вся история чата '{chat_title}'.")
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

        should_proc, reason, media_type, duration = self.filter_engine.should_process_message(
            message=msg,
            chat=dialog.entity,
            sender=sender,
        )

        sender_name = utils.get_display_name(sender) if sender else "Unknown"

        if not should_proc:
            logger.debug(f"[BACKFILL SKIP] msg_id={msg.id} in '{chat_title}': {reason}")
            self.db.mark_message_skipped(chat_id, msg.id, reason)
            return

        media_label = "🎤 Голосовое" if media_type == "voice" else "📹 Кружочек"
        logger.info(
            f"📥 [BACKFILL] Найдено {media_label} ({duration:.1f}с) "
            f"от {sender_name} в '{chat_title}' (id={msg.id}). Расшифровываем..."
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

        if result.status == "done":
            preview = result.text.replace("\n", " ") if result.text else ""
            if len(preview) > 80:
                preview = preview[:77] + "..."
            logger.info(f"✅ [BACKFILL] Расшифровано: \"{preview}\"")
        elif result.status == "pending":
            logger.info("⏳ [BACKFILL] Запрос отправлен. Обработка на сервере Telegram.")
        else:
            logger.warning(f"⚠️ [BACKFILL] Ошибка: {result.error_message}")

        # Polite delay to respect Telegram rate limits and avoid FloodWait
        if self.config.delay_seconds > 0:
            await asyncio.sleep(self.config.delay_seconds)
