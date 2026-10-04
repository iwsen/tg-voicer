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
# Автоматическая расшифровка голосовых сообщений и кружочков через Telegram Premium
# ==============================================================================

[telegram]
# Получите api_id и api_hash на сайте https://my.telegram.org (пункт API development tools)
api_id = 0
api_hash = ""

# Название сессии (сохраняется в data/session_name.session)
session_name = "tg_voicer"

# Расшифровывать голосовые сообщения (.ogg / .opus)
transcribe_voice = true

# Расшифровывать видеосообщения (кружочки)
transcribe_video_notes = true

# Расшифровывать собственные отправленные голосовые (true - да, false - только входящие)
transcribe_outgoing = false


[filters]
# 1. Типы чатов, которые нужно ИГНОРИРОВАТЬ.
# Допустимые значения:
#   "channels"    - каналы (broadcast channels)
#   "groups"      - группы и супергруппы
#   "private"     - личные сообщения (директ 1-на-1)
#   "bots"        - диалоги с ботами
# Пример: ignore_types = ["channels", "bots"]
ignore_types = []

# 2. Конкретные чаты/группы/каналы, которые нужно ИГНОРИРОВАТЬ.
# Можно указывать:
#   - ID чата (число, например -1001234567890 или 12345678)
#   - Username чата (например "@annoying_channel" или "news_chat")
#   - Название чата или его часть (например "Рабочий флуд", "Новости")
# Пример:
# ignored_chats = ["@some_channel", -100192837465, "Флудилка"]
ignored_chats = []

# 3. Конкретные пользователи (люди), чьи голосовые нужно ИГНОРИРОВАТЬ.
# Можно указывать:
#   - ID пользователя (число, например 123456789)
#   - Username пользователя (например "@annoying_user")
#   - Имя/фамилия пользователя (например "Иван Иванов")
# Пример:
# ignored_users = ["@spammer", 123456789, "Нежелательный Человек"]
ignored_users = []

# 4. БЕЛЫЙ СПИСОК ЧАТОВ (Опционально).
# Если этот список НЕ пустой, скрипт будет обрабатывать ТОЛЬКО эти чаты.
# Оставьте пустым [], чтобы обрабатывать все (кроме ignored_chats).
allowed_chats = []

# 5. БЕЛЫЙ СПИСОК ПОЛЬЗОВАТЕЛЕЙ (Опционально).
# Если этот список НЕ пустой, скрипт будет обрабатывать голосовые ТОЛЬКО от этих людей.
allowed_users = []

# Фильтр длительности голосовых в секундах (0 = без ограничений)
min_duration_seconds = 0
max_duration_seconds = 0


[realtime]
# Отслеживать новые сообщения в реальном времени и сразу нажимать кнопку
enabled = true

# Ожидать завершения расшифровки, если Telegram вернул "в обработке" (pending)
wait_for_completion = true

# Таймаут ожидания распознавания одного сообщения (секунды)
timeout_seconds = 30


[backfill]
# Обрабатывать уже существующие (архивные) голосовые сообщения, когда нет новых
enabled = true

# Пауза между запросами расшифровки старых сообщений (в секундах).
# ВАЖНО: Telegram лимитирует частые запросы (FloodWait). Рекомендуется от 1.5 до 3.0 сек.
delay_seconds = 2.0

# Максимальное количество сообщений для сканирования на один чат (0 = без лимита, вся история)
max_messages_per_chat = 0

# Максимальное количество чатов для сканирования (0 = все доступные)
max_chats = 0

# Размер пачки сообщений при запросе истории
batch_size = 100


[storage]
# Путь к SQLite базе данных для хранения статуса и кеша
db_path = "data/voicer.db"


[logging]
# Уровень логирования: "DEBUG", "INFO", "WARNING", "ERROR"
level = "INFO"

# Сохранять лог в файл
log_to_file = true
log_file_path = "data/voicer.log"
"""


@dataclass
class TelegramConfig:
    api_id: int = 0
    api_hash: str = ""
    session_name: str = "tg_voicer"
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
    delay_seconds: float = 2.0
    max_messages_per_chat: int = 0
    max_chats: int = 0
    batch_size: int = 100


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
        return config

    def _apply_dict(self, data: dict[str, Any]) -> None:
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
