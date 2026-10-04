"""
Realtime message listener for TG-Voicer.
Instantly intercepts incoming/outgoing voice notes and video notes and triggers transcription.
"""

from __future__ import annotations

import logging
from typing import Optional

from telethon import TelegramClient, events, utils

from .database import Database
from .filters import FilterEngine
from .transcriber import TelegramTranscriber

logger = logging.getLogger("tg_voicer.realtime")


class RealtimeListener:
    """Listens for new messages in real-time and immediately transcribes eligible voice messages."""

    def __init__(
        self,
        client: TelegramClient,
        filter_engine: FilterEngine,
        transcriber: TelegramTranscriber,
        db: Database,
    ):
        self.client = client
        self.filter_engine = filter_engine
        self.transcriber = transcriber
        self.db = db
        self._handler_ref = None

    def start(self) -> None:
        """Register event handler on TelegramClient."""
        if self._handler_ref is not None:
            return

        @self.client.on(events.NewMessage)
        async def on_new_message(event: events.NewMessage.Event):
            message = event.message
            if not message:
                return

            # Fast preliminary check: only inspect messages that have voice or video note media
            if not message.voice and not message.video_note:
                return

            await self._process_live_message(message)

        self._handler_ref = on_new_message
        logger.info("⚡ Real-time voice message listener started.")

    def stop(self) -> None:
        """Remove event handler."""
        if self._handler_ref is not None:
            self.client.remove_event_handler(self._handler_ref)
            self._handler_ref = None
            logger.info("🛑 Real-time voice message listener stopped.")

    async def _process_live_message(self, message: events.NewMessage.Event) -> None:
        try:
            chat = await message.get_chat()
            sender = await message.get_sender()
        except Exception as e:
            logger.debug(f"Failed to fetch chat or sender for live message {message.id}: {e}")
            chat = None
            sender = None

        should_proc, reason, media_type, duration = self.filter_engine.should_process_message(
            message=message,
            chat=chat,
            sender=sender,
        )

        chat_id = message.chat_id
        msg_id = message.id
        chat_title = utils.get_display_name(chat) if chat else f"Chat_{chat_id}"
        sender_name = utils.get_display_name(sender) if sender else "Unknown"

        if not should_proc:
            logger.debug(f"[LIVE IGNORED] Message {msg_id} in '{chat_title}': {reason}")
            # Optionally mark as skipped in DB
            self.db.mark_message_skipped(chat_id, msg_id, reason)
            return

        media_label = "🎤 Голосовое" if media_type == "voice" else "📹 Кружочек"
        logger.info(
            f"⚡ [LIVE] Поймано новое {media_label} ({duration:.1f}с) "
            f"от {sender_name} в '{chat_title}' (id={msg_id}). Расшифровываем..."
        )

        # Pre-save message to DB
        self.db.save_message(
            chat_id=chat_id,
            msg_id=msg_id,
            media_type=media_type or "voice",
            sender_id=message.sender_id,
            sender_name=sender_name,
            chat_title=chat_title,
            status="pending",
            is_live=True,
            duration_sec=duration,
            msg_date=message.date,
        )

        # Execute transcription
        result = await self.transcriber.transcribe(
            peer=message.chat_id,
            msg_id=msg_id,
            chat_id=chat_id,
            is_live=True,
        )

        if result.status == "done":
            preview = result.text.replace("\n", " ") if result.text else ""
            if len(preview) > 80:
                preview = preview[:77] + "..."
            logger.info(f"✅ [LIVE] Расшифровано: \"{preview}\"")
        elif result.status == "pending":
            logger.info("⏳ [LIVE] Запрос отправлен в Telegram. Обработка выполняется на сервере.")
        else:
            logger.warning(f"⚠️ [LIVE] Не удалось расшифровать: {result.error_message}")
