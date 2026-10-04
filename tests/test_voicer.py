"""
Unit tests for tg-voicer components.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from telethon.tl import types

from tg_voicer.config import AppConfig, FiltersConfig, TelegramConfig
from tg_voicer.database import Database
from tg_voicer.filters import FilterEngine, get_chat_type, match_entity, normalize_identifier


class TestFilters(unittest.TestCase):
    def setUp(self):
        self.tg_cfg = TelegramConfig(
            transcribe_voice=True,
            transcribe_video_notes=True,
            transcribe_outgoing=False,
        )
        self.filters_cfg = FiltersConfig(
            ignore_types=["channels", "bots"],
            ignored_chats=["@annoying_channel", -100123456789, "Рабочий Флуд"],
            ignored_users=["@spammer", 999888777, "Нежелательный Человек"],
            min_duration_seconds=2,
            max_duration_seconds=300,
        )
        self.engine = FilterEngine(self.filters_cfg, self.tg_cfg)

    def test_normalize_identifier(self):
        self.assertEqual(normalize_identifier(12345), 12345)
        self.assertEqual(normalize_identifier("12345"), 12345)
        self.assertEqual(normalize_identifier("-10012345"), -10012345)
        self.assertEqual(normalize_identifier("@Username"), "username")
        self.assertEqual(normalize_identifier("User_Name"), "user_name")

    def test_match_entity(self):
        patterns = ["@test_user", 123456, "Новости"]
        self.assertEqual(match_entity(123456, None, None, patterns), 123456)
        self.assertEqual(match_entity(999, "test_user", None, patterns), "@test_user")
        self.assertEqual(match_entity(999, "@TEST_USER", None, patterns), "@test_user")
        self.assertEqual(match_entity(999, None, "Главные Новости Дня", patterns), "Новости")
        self.assertIsNone(match_entity(888, "other_user", "Привет", patterns))

    def test_chat_type_ignore(self):
        self.assertTrue(self.engine.is_chat_type_ignored("channel"))
        self.assertTrue(self.engine.is_chat_type_ignored("bot"))
        self.assertFalse(self.engine.is_chat_type_ignored("private"))
        self.assertFalse(self.engine.is_chat_type_ignored("group"))

    def test_message_filtering_outgoing(self):
        msg = MagicMock()
        msg.out = True
        msg.voice = MagicMock()
        msg.raw_text = ""
        should_proc, reason, _, _, _ = self.engine.should_process_message(msg, None, None)
        self.assertFalse(should_proc)
        self.assertIn("Outgoing", reason)

    def test_message_filtering_voice_allowed(self):
        msg = MagicMock()
        msg.out = False
        msg.raw_text = ""
        msg.sender_id = 111222
        msg.chat_id = -222333
        attr = types.DocumentAttributeAudio(duration=15, voice=True)
        doc = types.Document(
            id=1, access_hash=2, file_reference=b"", date=None,
            mime_type="audio/ogg", size=100, dc_id=1, attributes=[attr]
        )
        msg.voice = doc
        msg.video_note = None

        chat = types.Chat(id=222333, title="Друзья", photo=None, participants_count=5, date=None, version=1)
        sender = types.User(id=111222, first_name="Алексей")

        should_proc, reason, media_type, duration, existing_text = self.engine.should_process_message(msg, chat, sender)
        self.assertTrue(should_proc)
        self.assertEqual(media_type, "voice")
        self.assertEqual(duration, 15.0)
        self.assertEqual(existing_text, "")

    def test_message_filtering_skip_if_already_has_text(self):
        msg = MagicMock()
        msg.out = False
        msg.raw_text = "Слушай внимательно, тут важное сообщение"
        msg.sender_id = 111222
        msg.chat_id = -222333
        attr = types.DocumentAttributeAudio(duration=15, voice=True)
        msg.voice = MagicMock(attributes=[attr])
        msg.video_note = None

        chat = types.Chat(id=222333, title="Друзья", photo=None, participants_count=5, date=None, version=1)
        sender = types.User(id=111222, first_name="Алексей")

        should_proc, reason, media_type, duration, existing_text = self.engine.should_process_message(msg, chat, sender)
        self.assertFalse(should_proc)
        self.assertIn("already has text", reason)
        self.assertEqual(existing_text, "Слушай внимательно, тут важное сообщение")

    def test_message_filtering_ignored_user(self):
        msg = MagicMock()
        msg.out = False
        msg.raw_text = ""
        msg.sender_id = 999888777  # Ignored user ID
        msg.chat_id = -222333
        attr = types.DocumentAttributeAudio(duration=10, voice=True)
        msg.voice = MagicMock(attributes=[attr])
        msg.video_note = None

        chat = types.Chat(id=222333, title="Друзья", photo=None, participants_count=5, date=None, version=1)
        sender = types.User(id=999888777, first_name="Спамер")

        should_proc, reason, _, _, _ = self.engine.should_process_message(msg, chat, sender)
        self.assertFalse(should_proc)
        self.assertIn("ignored_users", reason)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_voicer.db"
        self.db = Database(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_retrieve_message(self):
        self.assertFalse(self.db.is_message_processed(100, 1))

        self.db.save_message(
            chat_id=100,
            msg_id=1,
            media_type="voice",
            sender_id=200,
            sender_name="Alice",
            chat_title="My Chat",
            status="pending",
            duration_sec=12.5,
        )

        msg = self.db.get_message(100, 1)
        self.assertIsNotNone(msg)
        self.assertEqual(msg["sender_name"], "Alice")
        self.assertEqual(msg["status"], "pending")

        # Update transcription
        self.db.update_transcription(100, 1, transcription_id=555, text="Привет мир!", status="done")
        self.assertTrue(self.db.is_message_processed(100, 1))

        msg_updated = self.db.get_message(100, 1)
        self.assertEqual(msg_updated["text"], "Привет мир!")
        self.assertEqual(msg_updated["status"], "done")

    def test_cursors_and_stats(self):
        self.db.update_chat_cursor(
            chat_id=100,
            chat_title="My Chat",
            chat_type="group",
            oldest_scanned_id=50,
            newest_scanned_id=100,
            history_completed=False,
            increment_scanned=10,
        )

        cursor = self.db.get_chat_cursor(100)
        self.assertEqual(cursor["oldest_scanned_id"], 50)
        self.assertEqual(cursor["total_scanned"], 10)
        self.assertEqual(cursor["history_completed"], 0)

        # Mark completed
        self.db.update_chat_cursor(chat_id=100, history_completed=True)
        cursor2 = self.db.get_chat_cursor(100)
        self.assertEqual(cursor2["history_completed"], 1)

        stats = self.db.get_stats()
        self.assertEqual(stats["chats_history_completed"], 1)

        # Reset cursors
        self.db.reset_all_cursors()
        cursor3 = self.db.get_chat_cursor(100)
        self.assertEqual(cursor3["history_completed"], 0)
        self.assertIsNone(cursor3["oldest_scanned_id"])


if __name__ == "__main__":
    unittest.main()
