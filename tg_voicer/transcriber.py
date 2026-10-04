"""
Telegram Premium Speech-to-Text Transcriber.
Calls MTProto messages.TranscribeAudioRequest and listens for UpdateTranscribedAudio.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from telethon import TelegramClient, events, utils
from telethon.errors import (
    FloodWaitError,
    MsgIdInvalidError,
    PremiumAccountRequiredError,
    RPCError,
)
from telethon.tl import types
from telethon.tl.functions.messages import TranscribeAudioRequest

from .database import Database

logger = logging.getLogger("tg_voicer.transcriber")


@dataclass
class TranscriptionResult:
    status: str  # 'done', 'pending', 'failed', 'skipped'
    text: Optional[str] = None
    transcription_id: Optional[int] = None
    error_message: Optional[str] = None


class TelegramTranscriber:
    """Manages Telegram Premium voice transcription requests and updates."""

    def __init__(
        self,
        client: TelegramClient,
        db: Database,
        wait_for_completion: bool = True,
        timeout_seconds: int = 30,
    ):
        self.client = client
        self.db = db
        self.wait_for_completion = wait_for_completion
        self.timeout_seconds = timeout_seconds

        # Map (chat_id, msg_id) -> asyncio.Future[TranscriptionResult]
        self._pending_futures: Dict[Tuple[int, int], asyncio.Future[TranscriptionResult]] = {}
        # Concurrency lock to avoid overwhelming Telegram MTProto transport
        self._rpc_lock = asyncio.Lock()
        # High priority event for live requests to pause/preempt backfill if needed
        self._live_processing_event = asyncio.Event()
        self._live_processing_event.set()

        self._setup_event_handlers()

    def _setup_event_handlers(self) -> None:
        """Register raw MTProto update listener for UpdateTranscribedAudio."""
        @self.client.on(events.Raw(types.UpdateTranscribedAudio))
        async def on_transcribed_audio(update: types.UpdateTranscribedAudio):
            peer_id = utils.get_peer_id(update.peer)
            msg_id = update.msg_id
            text = update.text or ""
            is_pending = bool(update.pending)
            transcription_id = update.transcription_id

            logger.debug(
                f"[MTProto Update] peer={peer_id} msg_id={msg_id} "
                f"pending={is_pending} text='{text[:40]}...'"
            )

            # Update database if transcription has text or finished
            if not is_pending:
                self.db.update_transcription(
                    chat_id=peer_id,
                    msg_id=msg_id,
                    transcription_id=transcription_id,
                    text=text,
                    status="done",
                )

                # Resolve any pending future waiting for this message
                future = self._pending_futures.get((peer_id, msg_id))
                if future and not future.done():
                    future.set_result(
                        TranscriptionResult(
                            status="done",
                            text=text,
                            transcription_id=transcription_id,
                        )
                    )

    async def transcribe(
        self,
        peer: Any,
        msg_id: int,
        chat_id: int,
        is_live: bool = False,
    ) -> TranscriptionResult:
        """
        Request Telegram Premium transcription for a voice message or video note.
        Handles rate limits, pending status polling, and error recovery.
        """
        # 1. Check if already transcribed in DB
        existing = self.db.get_message(chat_id, msg_id)
        if existing and existing.get("status") == "done" and existing.get("text"):
            logger.debug(f"Message {msg_id} in {chat_id} already transcribed in DB: '{existing['text'][:30]}...'")
            return TranscriptionResult(
                status="done",
                text=existing["text"],
                transcription_id=existing.get("transcription_id"),
            )

        # 2. Acquire lock and resolve input peer
        async with self._rpc_lock:
            try:
                input_peer = await self.client.get_input_entity(peer)
            except Exception as e:
                err_msg = f"Failed to resolve input peer: {e}"
                logger.error(err_msg)
                return TranscriptionResult(status="failed", error_message=err_msg)

            # 3. Call TranscribeAudioRequest with FloodWait handling
            max_retries = 3
            current_try = 0
            res = None

            while current_try < max_retries:
                current_try += 1
                try:
                    res = await self.client(
                        TranscribeAudioRequest(peer=input_peer, msg_id=msg_id)
                    )
                    break
                except FloodWaitError as e:
                    wait_time = e.seconds + 2
                    logger.warning(
                        f"⏳ Telegram FloodWait: server requested {e.seconds}s pause. "
                        f"Sleeping {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                except PremiumAccountRequiredError:
                    err_msg = "Telegram Premium required for speech-to-text"
                    logger.error(f"❌ {err_msg}")
                    self.db.mark_message_failed(chat_id, msg_id, err_msg)
                    return TranscriptionResult(status="failed", error_message=err_msg)
                except MsgIdInvalidError:
                    err_msg = f"Message {msg_id} no longer exists or invalid ID"
                    logger.warning(err_msg)
                    self.db.mark_message_failed(chat_id, msg_id, err_msg)
                    return TranscriptionResult(status="failed", error_message=err_msg)
                except RPCError as e:
                    err_msg = f"Telegram RPC error: {e}"
                    logger.warning(err_msg)
                    self.db.mark_message_failed(chat_id, msg_id, err_msg)
                    return TranscriptionResult(status="failed", error_message=err_msg)
                except Exception as e:
                    err_msg = f"Unexpected error while calling TranscribeAudioRequest: {e}"
                    logger.exception(err_msg)
                    self.db.mark_message_failed(chat_id, msg_id, err_msg)
                    return TranscriptionResult(status="failed", error_message=err_msg)

            if not res:
                return TranscriptionResult(
                    status="failed", error_message="Exceeded max retries for TranscribeAudioRequest"
                )

        # 4. Handle response
        transcription_id = getattr(res, "transcription_id", None)
        text = getattr(res, "text", "") or ""
        is_pending = getattr(res, "pending", False)

        if not is_pending:
            # Transcription is immediately available
            self.db.update_transcription(
                chat_id=chat_id,
                msg_id=msg_id,
                transcription_id=transcription_id,
                text=text,
                status="done",
            )
            return TranscriptionResult(
                status="done",
                text=text,
                transcription_id=transcription_id,
            )

        # If pending and user wants to wait for completion
        if self.wait_for_completion:
            loop = asyncio.get_running_loop()
            future: asyncio.Future[TranscriptionResult] = loop.create_future()
            self._pending_futures[(chat_id, msg_id)] = future

            try:
                # Wait for MTProto update or poll periodically
                poll_interval = 3.0
                elapsed = 0.0

                while elapsed < self.timeout_seconds:
                    try:
                        # Wait for MTProto update event with a short timeout
                        wait_slice = min(poll_interval, self.timeout_seconds - elapsed)
                        return await asyncio.wait_for(asyncio.shield(future), timeout=wait_slice)
                    except asyncio.TimeoutError:
                        elapsed += poll_interval
                        # Poll by re-invoking request
                        async with self._rpc_lock:
                            try:
                                poll_res = await self.client(
                                    TranscribeAudioRequest(peer=input_peer, msg_id=msg_id)
                                )
                                if not getattr(poll_res, "pending", False):
                                    p_text = getattr(poll_res, "text", "") or ""
                                    p_tid = getattr(poll_res, "transcription_id", transcription_id)
                                    self.db.update_transcription(
                                        chat_id=chat_id,
                                        msg_id=msg_id,
                                        transcription_id=p_tid,
                                        text=p_text,
                                        status="done",
                                    )
                                    return TranscriptionResult(
                                        status="done",
                                        text=p_text,
                                        transcription_id=p_tid,
                                    )
                            except Exception:
                                pass

            except asyncio.CancelledError:
                raise
            finally:
                self._pending_futures.pop((chat_id, msg_id), None)

        # If not waiting or timeout reached: transcription is initiated in cloud
        self.db.update_transcription(
            chat_id=chat_id,
            msg_id=msg_id,
            transcription_id=transcription_id,
            text=text,
            status="pending",
        )
        return TranscriptionResult(
            status="pending",
            text=text,
            transcription_id=transcription_id,
        )
