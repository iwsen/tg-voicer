"""
Filtering engine for TG-Voicer.
Evaluates chats, users, chat types, and media according to configuration rules.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple, Union
from telethon.tl import types
from telethon import utils

from .config import FiltersConfig, TelegramConfig


def normalize_identifier(identifier: Union[int, str]) -> Union[int, str]:
    """Normalize input identifier: clean up usernames or convert numeric strings."""
    if isinstance(identifier, int):
        return identifier
    s = str(identifier).strip()
    # Check if purely numeric
    if s.lstrip("-").isdigit():
        try:
            return int(s)
        except ValueError:
            pass
    # If starts with @, remove it for uniform username comparison
    if s.startswith("@"):
        return s[1:].lower()
    return s.lower()


def match_entity(
    target_id: Optional[int],
    target_username: Optional[str],
    target_title: Optional[str],
    patterns: List[Union[int, str]],
) -> Optional[Union[int, str]]:
    """
    Check if an entity (chat or user) matches any pattern in the list.
    Returns the matching pattern if found, or None.
    """
    if not patterns:
        return None

    clean_username = target_username.lstrip("@").lower() if target_username else None
    clean_title = target_title.lower() if target_title else None

    for pat in patterns:
        norm_pat = normalize_identifier(pat)

        # 1. Match by numeric ID
        if isinstance(norm_pat, int) and target_id is not None:
            if norm_pat == target_id:
                return pat
            # Handle channel -100 prefix discrepancies if applicable
            str_pat = str(norm_pat).removeprefix("-100").removeprefix("-")
            str_tgt = str(target_id).removeprefix("-100").removeprefix("-")
            if str_pat == str_tgt:
                return pat

        # 2. Match by username
        elif isinstance(norm_pat, str) and clean_username:
            if norm_pat == clean_username:
                return pat

        # 3. Match by Title / Name (substring or exact)
        elif isinstance(norm_pat, str) and clean_title:
            if norm_pat in clean_title:
                return pat

    return None


def get_chat_type(entity: Any) -> str:
    """
    Determine chat type from Telethon entity:
    Returns: 'channel', 'supergroup', 'group', 'bot', 'private', or 'unknown'
    """
    if isinstance(entity, types.User):
        if getattr(entity, "bot", False):
            return "bot"
        return "private"
    elif isinstance(entity, types.Chat):
        return "group"
    elif isinstance(entity, types.Channel):
        if getattr(entity, "megagroup", False) or getattr(entity, "gigagroup", False):
            return "supergroup"
        return "channel"
    return "unknown"


class FilterEngine:
    """Rule engine for checking whether messages and chats should be transcribed."""

    def __init__(self, filters_cfg: FiltersConfig, telegram_cfg: TelegramConfig):
        self.filters_cfg = filters_cfg
        self.telegram_cfg = telegram_cfg

        # Normalize ignored types into a set
        self.ignored_types: set[str] = set()
        for t in filters_cfg.ignore_types:
            clean = t.strip().lower()
            if clean in ("channel", "channels"):
                self.ignored_types.add("channel")
            elif clean in ("group", "groups"):
                self.ignored_types.add("group")
                self.ignored_types.add("supergroup")
            elif clean in ("supergroup", "supergroups"):
                self.ignored_types.add("supergroup")
            elif clean in ("private", "direct", "users", "user", "dm", "dms"):
                self.ignored_types.add("private")
            elif clean in ("bot", "bots"):
                self.ignored_types.add("bot")

    def is_chat_type_ignored(self, chat_type: str) -> bool:
        """Check if chat type is ignored."""
        if chat_type in self.ignored_types:
            return True
        # If 'group' is ignored, also ignore 'supergroup'
        if "group" in self.ignored_types and chat_type in ("group", "supergroup"):
            return True
        return False

    def should_process_dialog(self, dialog: Any) -> Tuple[bool, str]:
        """
        Quick check for dialogs in backfill.
        Returns (should_process, reason).
        """
        entity = dialog.entity
        chat_type = get_chat_type(entity)
        chat_id = utils.get_peer_id(entity)
        username = getattr(entity, "username", None)
        title = utils.get_display_name(entity)

        # 1. Check chat type
        if self.is_chat_type_ignored(chat_type):
            return False, f"Chat type '{chat_type}' is in ignore_types"

        # 2. Check Whitelist (allowed_chats)
        if self.filters_cfg.allowed_chats:
            matched_allowed = match_entity(chat_id, username, title, self.filters_cfg.allowed_chats)
            if not matched_allowed:
                return False, "Chat is not in allowed_chats whitelist"

        # 3. Check Blacklist (ignored_chats)
        matched_ignored = match_entity(chat_id, username, title, self.filters_cfg.ignored_chats)
        if matched_ignored:
            return False, f"Chat matches ignored_chats rule: '{matched_ignored}'"

        return True, "OK"

    def should_process_message(
        self,
        message: types.Message,
        chat: Any,
        sender: Any,
    ) -> Tuple[bool, str, Optional[str], float]:
        """
        Detailed check for a specific message.
        Returns (should_process, reason, media_type, duration_sec).
        """
        # 1. Outgoing check
        if message.out and not self.telegram_cfg.transcribe_outgoing:
            return False, "Outgoing message (transcribe_outgoing is false)", None, 0.0

        # 2. Media check (voice or video note)
        media_type = None
        duration = 0.0

        voice_doc = message.voice
        video_note_doc = message.video_note

        if voice_doc:
            if not self.telegram_cfg.transcribe_voice:
                return False, "Voice notes disabled in config", None, 0.0
            media_type = "voice"
            # Extract duration
            for attr in voice_doc.attributes:
                if isinstance(attr, types.DocumentAttributeAudio):
                    duration = float(getattr(attr, "duration", 0))
                    break
        elif video_note_doc:
            if not self.telegram_cfg.transcribe_video_notes:
                return False, "Video notes disabled in config", None, 0.0
            media_type = "video_note"
            # Extract duration
            for attr in video_note_doc.attributes:
                if isinstance(attr, types.DocumentAttributeVideo):
                    duration = float(getattr(attr, "duration", 0.0))
                    break
        else:
            return False, "Message has no voice or video note", None, 0.0

        # 3. Duration check
        if self.filters_cfg.min_duration_seconds > 0 and duration < self.filters_cfg.min_duration_seconds:
            return False, f"Duration {duration:.1f}s < min {self.filters_cfg.min_duration_seconds}s", media_type, duration

        if self.filters_cfg.max_duration_seconds > 0 and duration > self.filters_cfg.max_duration_seconds:
            return False, f"Duration {duration:.1f}s > max {self.filters_cfg.max_duration_seconds}s", media_type, duration

        # 4. Chat type check
        chat_type = get_chat_type(chat) if chat else "unknown"
        if self.is_chat_type_ignored(chat_type):
            return False, f"Chat type '{chat_type}' is in ignore_types", media_type, duration

        # 5. Chat Whitelist & Blacklist
        chat_id = utils.get_peer_id(chat) if chat else message.chat_id
        chat_username = getattr(chat, "username", None) if chat else None
        chat_title = utils.get_display_name(chat) if chat else None

        if self.filters_cfg.allowed_chats:
            matched_allowed = match_entity(chat_id, chat_username, chat_title, self.filters_cfg.allowed_chats)
            if not matched_allowed:
                return False, "Chat is not in allowed_chats whitelist", media_type, duration

        matched_ignored = match_entity(chat_id, chat_username, chat_title, self.filters_cfg.ignored_chats)
        if matched_ignored:
            return False, f"Chat matches ignored_chats rule: '{matched_ignored}'", media_type, duration

        # 6. Sender Whitelist & Blacklist
        sender_id = message.sender_id
        sender_username = getattr(sender, "username", None) if sender else None
        sender_name = utils.get_display_name(sender) if sender else None

        if self.filters_cfg.allowed_users:
            matched_user_allowed = match_entity(sender_id, sender_username, sender_name, self.filters_cfg.allowed_users)
            if not matched_user_allowed:
                return False, "Sender is not in allowed_users whitelist", media_type, duration

        matched_user_ignored = match_entity(sender_id, sender_username, sender_name, self.filters_cfg.ignored_users)
        if matched_user_ignored:
            return False, f"Sender matches ignored_users rule: '{matched_user_ignored}'", media_type, duration

        return True, "OK", media_type, duration
