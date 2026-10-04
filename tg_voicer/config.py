"""
Configuration management for TG-Voicer.
Supports TOML (Python 3.11+), JSON, and environment variables.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Set, Union

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore


DEFAULT_CONFIG_TEMPLATE = """# ==============================================================================
# TG-VOICER Configuration
# Automated Telegram Premium speech-to-text transcriber for voice & video notes
# ==============================================================================

[general]
# Interface and display language: "en" (English - default) or "ru" (Russian)
language = "en"

[telegram]
# Obtain api_id and api_hash at https://my.telegram.org ('API development tools')
api_id = 0
api_hash = ""

# Session name (stored in data/session_name.session)
session_name = "tg_voicer"

# Authentication method on initial launch: "qr" (QR code scan in mobile app) or "phone"
auth_method = "qr"

# Transcribe voice audio messages (.ogg / .opus)
transcribe_voice = true

# Transcribe round video notes
transcribe_video_notes = true

# Transcribe your own outgoing voice messages (true = both, false = incoming only)
transcribe_outgoing = false


[filters]
# 1. Chat types to IGNORE.
# Allowed options:
#   "channels"    - broadcast channels
#   "groups"      - group chats and supergroups
#   "private"     - 1-on-1 direct messages
#   "bots"        - bot dialogs
# Example: ignore_types = ["channels", "bots"]
ignore_types = []

# 2. Specific chats, channels or groups to IGNORE.
# Can specify:
#   - Chat ID (integer, e.g. -1001234567890 or 12345678)
#   - Chat username (e.g. "@annoying_channel" or "news_chat")
#   - Chat title or substring (e.g. "Work Spam", "News")
# Example:
# ignored_chats = ["@some_channel", -100192837465, "Spam Group"]
ignored_chats = []

# 3. Specific users whose voice messages should be IGNORED.
# Can specify:
#   - User ID (integer, e.g. 123456789)
#   - Username (e.g. "@annoying_user")
#   - User's display name or substring (e.g. "John Doe")
# Example:
# ignored_users = ["@spammer", 123456789, "Unwanted Person"]
ignored_users = []

# 4. Chat Whitelist (Optional).
# If not empty, only voice notes in these specific chats will be processed.
# Leave empty [] to process all non-ignored chats.
allowed_chats = []

# 5. User Whitelist (Optional).
# If not empty, only voice notes from these specific users will be processed.
allowed_users = []

# Skip messages that already have a text caption
# If true: if a voice message already has caption text, no API call is made.
skip_if_already_has_text = true

# Filter by voice duration in seconds (0 = no limit)
min_duration_seconds = 0
max_duration_seconds = 0


[realtime]
# Intercept incoming messages in real time and transcribe immediately
enabled = true

# Wait for completion if Telegram returns pending status
wait_for_completion = true

# Timeout waiting for a single transcription in seconds
timeout_seconds = 30


[backfill]
# Process existing historical voice messages when no new live messages arrive
enabled = true

# Randomize pause between API requests (strongly recommended against FloodWait)
randomize_delay = true

# Delay interval for initial transcription (in seconds)
delay_min_seconds = 3.5
delay_max_seconds = 7.0

# Fixed delay (used only when randomize_delay = false)
delay_seconds = 4.5

# Delay for messages already cached in Telegram cloud (instant fetch)
cached_delay_min_seconds = 0.5
cached_delay_max_seconds = 1.5
cached_delay_seconds = 0.8

# Maximum messages to scan per chat (0 = unlimited, entire history)
max_messages_per_chat = 0

# Maximum number of chats to scan (0 = all available dialogs)
max_chats = 0

# Batch size when requesting message history chunks
batch_size = 100


[storage]
# Path to SQLite database for state, history, and metrics
db_path = "data/voicer.db"


[logging]
# Log level: "DEBUG", "INFO", "WARNING", "ERROR"
level = "INFO"

# Save logs to file
log_to_file = true
log_file_path = "data/voicer.log"
"""


@dataclass
class TelegramConfig:
    api_id: int = 0
    api_hash: str = ""
    session_name: str = "tg_voicer"
    auth_method: str = "qr"
    transcribe_voice: bool = True
    transcribe_video_notes: bool = True
    transcribe_outgoing: bool = False


@dataclass
class FiltersConfig:
    ignore_types: List[str] = field(default_factory=list)
    ignored_chats: List[Union[int, str]] = field(default_factory=list)
    ignored_users: List[Union[int, str]] = field(default_factory=list)
    allowed_chats: List[Union[int, str]] = field(default_factory=list)
    allowed_users: List[Union[int, str]] = field(default_factory=list)
    skip_if_already_has_text: bool = True
    min_duration_seconds: int = 0
    max_duration_seconds: int = 0


@dataclass
class RealtimeConfig:
    enabled: bool = True
    wait_for_completion: bool = True
    timeout_seconds: int = 30


@dataclass
class BackfillConfig:
    enabled: bool = True
    delay_seconds: float = 4.0
    cached_delay_seconds: float = 0.8
    randomize_delay: bool = True
    delay_min_seconds: float = 3.5
    delay_max_seconds: float = 7.0
    cached_delay_min_seconds: float = 0.5
    cached_delay_max_seconds: float = 1.5
    max_messages_per_chat: int = 0
    max_chats: int = 0
    batch_size: int = 100

    def get_delay(self, is_cached: bool = False) -> float:
        """Calculate sleep delay in seconds, supporting random intervals."""
        import random
        if is_cached:
            if self.randomize_delay and self.cached_delay_max_seconds > self.cached_delay_min_seconds:
                return round(random.uniform(self.cached_delay_min_seconds, self.cached_delay_max_seconds), 2)
            return self.cached_delay_seconds
        else:
            if self.randomize_delay and self.delay_max_seconds > self.delay_min_seconds:
                return round(random.uniform(self.delay_min_seconds, self.delay_max_seconds), 2)
            return self.delay_seconds


@dataclass
class StorageConfig:
    db_path: str = "data/voicer.db"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    log_to_file: bool = True
    log_file_path: str = "data/voicer.log"


@dataclass
class AppConfig:
    language: str = "en"
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    filters: FiltersConfig = field(default_factory=FiltersConfig)
    realtime: RealtimeConfig = field(default_factory=RealtimeConfig)
    backfill: BackfillConfig = field(default_factory=BackfillConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    config_path: Path | None = None

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> AppConfig:
        """
        Load configuration from TOML, JSON, or environment variables.
        """
        config = cls()

        target_path: Path | None = None
        if config_path:
            target_path = Path(config_path)
        else:
            # Check default candidate locations
            candidates = [
                Path("config.toml"),
                Path("config.json"),
                Path("data/config.toml"),
            ]
            for c in candidates:
                if c.exists():
                    target_path = c
                    break

        if target_path and target_path.exists():
            config.config_path = target_path
            raw_data: dict[str, Any] = {}
            if target_path.suffix.lower() == ".toml":
                with open(target_path, "rb") as f:
                    raw_data = tomllib.load(f)
            elif target_path.suffix.lower() == ".json":
                with open(target_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)

            config._apply_dict(raw_data)

        # Allow environment variables to override or populate secrets
        config._apply_env()

        # Synchronize global i18n language
        from .i18n import set_language
        set_language(config.language)

        return config

    def _apply_dict(self, data: dict[str, Any]) -> None:
        lang = (
            data.get("language")
            or data.get("general", {}).get("language")
            or data.get("app", {}).get("language")
        )
        if lang:
            self.language = str(lang).strip().lower()

        tg = data.get("telegram", {})
        if "api_id" in tg:
            try:
                self.telegram.api_id = int(tg["api_id"])
            except (ValueError, TypeError):
                pass
        if "api_hash" in tg:
            self.telegram.api_hash = str(tg["api_hash"]).strip()
        if "session_name" in tg:
            self.telegram.session_name = str(tg["session_name"]).strip()
        if "auth_method" in tg:
            self.telegram.auth_method = str(tg["auth_method"]).strip().lower()
        if "transcribe_voice" in tg:
            self.telegram.transcribe_voice = bool(tg["transcribe_voice"])
        if "transcribe_video_notes" in tg:
            self.telegram.transcribe_video_notes = bool(tg["transcribe_video_notes"])
        if "transcribe_outgoing" in tg:
            self.telegram.transcribe_outgoing = bool(tg["transcribe_outgoing"])

        fl = data.get("filters", {})
        if "ignore_types" in fl:
            self.filters.ignore_types = [str(x).strip().lower() for x in fl["ignore_types"]]
        if "ignored_chats" in fl:
            self.filters.ignored_chats = fl["ignored_chats"]
        if "ignored_users" in fl:
            self.filters.ignored_users = fl["ignored_users"]
        if "allowed_chats" in fl:
            self.filters.allowed_chats = fl["allowed_chats"]
        if "allowed_users" in fl:
            self.filters.allowed_users = fl["allowed_users"]
        if "skip_if_already_has_text" in fl:
            self.filters.skip_if_already_has_text = bool(fl["skip_if_already_has_text"])
        if "min_duration_seconds" in fl:
            self.filters.min_duration_seconds = int(fl["min_duration_seconds"])
        if "max_duration_seconds" in fl:
            self.filters.max_duration_seconds = int(fl["max_duration_seconds"])

        rt = data.get("realtime", {})
        if "enabled" in rt:
            self.realtime.enabled = bool(rt["enabled"])
        if "wait_for_completion" in rt:
            self.realtime.wait_for_completion = bool(rt["wait_for_completion"])
        if "timeout_seconds" in rt:
            self.realtime.timeout_seconds = int(rt["timeout_seconds"])

        bf = data.get("backfill", {})
        if "enabled" in bf:
            self.backfill.enabled = bool(bf["enabled"])
        if "delay_seconds" in bf:
            self.backfill.delay_seconds = float(bf["delay_seconds"])
        if "cached_delay_seconds" in bf:
            self.backfill.cached_delay_seconds = float(bf["cached_delay_seconds"])
        if "randomize_delay" in bf:
            self.backfill.randomize_delay = bool(bf["randomize_delay"])
        if "delay_min_seconds" in bf:
            self.backfill.delay_min_seconds = float(bf["delay_min_seconds"])
        if "delay_max_seconds" in bf:
            self.backfill.delay_max_seconds = float(bf["delay_max_seconds"])
        if "cached_delay_min_seconds" in bf:
            self.backfill.cached_delay_min_seconds = float(bf["cached_delay_min_seconds"])
        if "cached_delay_max_seconds" in bf:
            self.backfill.cached_delay_max_seconds = float(bf["cached_delay_max_seconds"])
        if "max_messages_per_chat" in bf:
            self.backfill.max_messages_per_chat = int(bf["max_messages_per_chat"])
        if "max_chats" in bf:
            self.backfill.max_chats = int(bf["max_chats"])
        if "batch_size" in bf:
            self.backfill.batch_size = int(bf["batch_size"])

        st = data.get("storage", {})
        if "db_path" in st:
            self.storage.db_path = str(st["db_path"])

        lg = data.get("logging", {})
        if "level" in lg:
            self.logging.level = str(lg["level"]).upper()
        if "log_to_file" in lg:
            self.logging.log_to_file = bool(lg["log_to_file"])
        if "log_file_path" in lg:
            self.logging.log_file_path = str(lg["log_file_path"])

    def _apply_env(self) -> None:
        lang_env = os.getenv("TG_VOICER_LANG") or os.getenv("LANGUAGE")
        if lang_env:
            self.language = lang_env.strip().lower()

        # Check standard TG env variables
        api_id_env = os.getenv("TG_API_ID") or os.getenv("API_ID")
        if api_id_env:
            try:
                self.telegram.api_id = int(api_id_env)
            except ValueError:
                pass

        api_hash_env = os.getenv("TG_API_HASH") or os.getenv("API_HASH")
        if api_hash_env:
            self.telegram.api_hash = api_hash_env.strip()

        session_env = os.getenv("TG_SESSION_NAME")
        if session_env:
            self.telegram.session_name = session_env.strip()

    @staticmethod
    def create_default_template(destination: str | Path = "config.toml") -> Path:
        """Create a default config.toml file if it does not already exist."""
        dest = Path(destination)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(DEFAULT_CONFIG_TEMPLATE)
        return dest
