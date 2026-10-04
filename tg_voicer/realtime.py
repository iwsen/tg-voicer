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
from .network import NetworkManager, is_network_error
from .transcriber import TelegramTranscriber
from . import ui

logger = logging.getLogger("tg_voicer.realtime")


class RealtimeListener:
    """Listens for new messages in real-time and immediately transcribes eligible voice messages."""

    def __init__(
        self,
        client: TelegramClient,
        filter_engine: FilterEngine,
        transcriber: TelegramTranscriber,
        db: Database,
        network_manager: Optional[NetworkManager] = None,
    ):
        self.client = client
        self.filter_engine = filter_engine
        self.transcriber = transcriber
        self.db = db
        self.network_manager = network_manager
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
        chat = None
        sender = None
        for attempt in range(2):
            try:
                chat = await message.get_chat()
                sender = await message.get_sender()
                break
            except Exception as e:
                if is_network_error(e):
                    if self.network_manager:
                        await self.network_manager.wait_for_connection()
                    else:
                        await asyncio.sleep(2)
                else:
                    logger.debug(f"Failed to fetch chat or sender for live message {message.id}: {e}")
                    break

        should_proc, reason, media_type, duration, existing_text = self.filter_engine.should_process_message(
            message=message,
            chat=chat,
            sender=sender,
        )

        chat_id = message.chat_id
        msg_id = message.id
        chat_title = utils.get_display_name(chat) if chat else f"Chat_{chat_id}"
        sender_name = utils.get_display_name(sender) if sender else "Unknown"

        # If message already has text/caption, save it and skip API request
        if existing_text and self.filter_engine.filters_cfg.skip_if_already_has_text:
            logger.info(
                f"ℹ️ [УЖЕ ЕСТЬ ТЕКСТ] Новое сообщение id={msg_id} в '{chat_title}' уже содержит текст/подпись: "
                f"\"{existing_text[:50]}...\". Запрос к Telegram пропущен."
            )
            self.db.save_message(
                chat_id=chat_id,
                msg_id=msg_id,
                media_type=media_type or "voice",
                sender_id=message.sender_id,
                sender_name=sender_name,
                chat_title=chat_title,
                text=existing_text,
                status="done",
                is_live=True,
                duration_sec=duration,
                msg_date=message.date,
            )
            return

        if not should_proc:
            logger.debug(f"[LIVE IGNORED] Message {msg_id} in '{chat_title}': {reason}")
            # Optionally mark as skipped in DB
            self.db.mark_message_skipped(
                chat_id=chat_id,
                msg_id=msg_id,
                reason=reason,
                media_type=media_type,
                msg_date=message.date,
                duration_sec=duration,
                sender_id=message.sender_id,
                sender_name=sender_name,
                chat_title=chat_title,
            )
            return

        ui.print_voice_found(
            source="LIVE",
            media_type=media_type or "voice",
            duration=duration,
            sender_name=sender_name,
            chat_title=chat_title,
            msg_id=msg_id,
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

        ui.print_transcription_result(
            text=result.text,
            is_cached=result.was_already_transcribed,
            status=result.status,
            error=result.error_message,
        )
