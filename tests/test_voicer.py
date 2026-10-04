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
        self.db.close()
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


class TestUI(unittest.TestCase):
    def test_format_peer(self):
        from tg_voicer.i18n import set_language
        from tg_voicer.ui import format_peer

        # In English (default)
        set_language("en")
        self.assertIn("Alice", format_peer("Alice", "Alice"))
        self.assertNotIn("in", format_peer("Alice", "Alice"))
        res_en = format_peer("Alice", "Work Chat")
        self.assertIn("Alice", res_en)
        self.assertIn("Work Chat", res_en)
        self.assertIn("in", res_en)

        # In Russian
        set_language("ru")
        self.assertIn("Alice", format_peer("Alice", "Alice"))
        self.assertNotIn("в", format_peer("Alice", "Alice"))
        res_ru = format_peer("Alice", "Work Chat")
        self.assertIn("Alice", res_ru)
        self.assertIn("Work Chat", res_ru)
        self.assertIn("в", res_ru)

    def test_ui_render_functions(self):
        from tg_voicer.i18n import set_language
        from tg_voicer.ui import (
            print_banner,
            print_scan_chat,
            print_chat_completed,
            print_all_completed,
            print_voice_found,
            print_transcription_result,
            print_stats_table,
        )
        # Test in both English and Russian
        for lang in ("en", "ru"):
            set_language(lang)
            print_banner("1.0.0", "Tester", "@test", True, "Test Mode", "data/test.db", ["Filter 1"])
            print_scan_chat("Test Chat", "group", 123)
            print_chat_completed("Test Chat")
            print_all_completed()
            print_voice_found("BACKFILL", "voice", 15.0, "Alice", "Test Chat", 101)
            print_transcription_result("Test message", is_cached=False)
            print_transcription_result("Cached text", is_cached=True)
            print_transcription_result(None, status="failed", error="RPC Error")
            print_stats_table({"transcribed_done": 5}, [])

    def test_flood_wait_format(self):
        from tg_voicer.i18n import set_language
        from tg_voicer.ui import format_seconds, print_flood_wait

        # English
        set_language("en")
        self.assertEqual(format_seconds(30), "30 sec")
        self.assertEqual(format_seconds(125), "2 min 5 sec")
        self.assertEqual(format_seconds(3665), "1 h 1 min 5 sec")
        print_flood_wait(2525)

        # Russian
        set_language("ru")
        self.assertEqual(format_seconds(30), "30 сек")
        self.assertEqual(format_seconds(125), "2 мин 5 сек")
        self.assertEqual(format_seconds(3665), "1 ч 1 мин 5 сек")
        print_flood_wait(2525)

    def test_randomized_delay(self):
        from tg_voicer.config import BackfillConfig
        cfg = BackfillConfig(
            randomize_delay=True,
            delay_min_seconds=3.0,
            delay_max_seconds=5.0,
            cached_delay_min_seconds=0.5,
            cached_delay_max_seconds=1.0,
        )
        for _ in range(20):
            d = cfg.get_delay(is_cached=False)
            self.assertGreaterEqual(d, 3.0)
            self.assertLessEqual(d, 5.0)

            cd = cfg.get_delay(is_cached=True)
            self.assertGreaterEqual(cd, 0.5)
            self.assertLessEqual(cd, 1.0)

        # Fixed delay when randomize_delay is False
        cfg_fixed = BackfillConfig(
            randomize_delay=False,
            delay_seconds=4.2,
            cached_delay_seconds=0.7,
        )
        self.assertEqual(cfg_fixed.get_delay(is_cached=False), 4.2)
        self.assertEqual(cfg_fixed.get_delay(is_cached=True), 0.7)


class TestNetwork(unittest.IsolatedAsyncioTestCase):
    def test_is_network_error(self):
        import asyncio
        import socket
        from tg_voicer.network import is_network_error

        # Direct OS/network exceptions
        self.assertTrue(is_network_error(ConnectionError("Connection reset by peer")))
        self.assertTrue(is_network_error(ConnectionResetError()))
        self.assertTrue(is_network_error(socket.gaierror("Name or service not known")))
        self.assertTrue(is_network_error(OSError(51, "Network is unreachable")))
        self.assertTrue(is_network_error(asyncio.TimeoutError()))
        self.assertTrue(is_network_error(Exception("Cannot send requests while disconnected")))
        self.assertTrue(is_network_error(Exception("Server connection lost")))

        # Non-network exceptions
        self.assertFalse(is_network_error(ValueError("Invalid argument")))
        self.assertFalse(is_network_error(KeyError("missing_key")))
        self.assertFalse(is_network_error(TypeError("bad type")))

    async def test_network_manager_recovery(self):
        from tg_voicer.network import NetworkManager

        mock_client = MagicMock()
        mock_client.is_connected.return_value = False

        connect_called = 0

        async def mock_connect():
            nonlocal connect_called
            connect_called += 1
            mock_client.is_connected.return_value = True

        mock_client.connect = mock_connect

        # Sequence: offline first, then online
        checks = [False, True]

        async def mock_checker():
            if checks:
                return checks.pop(0)
            return True

        mgr = NetworkManager(
            client=mock_client,
            check_interval=0.01,
            internet_checker=mock_checker,
        )

        await mgr.wait_for_connection()
        self.assertTrue(mgr.is_online)
        self.assertEqual(connect_called, 1)


class TestDaemon(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pid_file = Path(self.temp_dir.name) / "test.pid"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_pid_lifecycle(self):
        import os
        from tg_voicer.daemon import (
            read_pid,
            write_pid,
            remove_pid,
            is_pid_running,
            get_daemon_status,
        )

        self.assertIsNone(read_pid(self.pid_file))
        is_running, pid = get_daemon_status(self.pid_file)
        self.assertFalse(is_running)
        self.assertIsNone(pid)

        # Write current process PID (which is guaranteed running)
        curr_pid = os.getpid()
        write_pid(curr_pid, self.pid_file)
        self.assertEqual(read_pid(self.pid_file), curr_pid)
        self.assertTrue(is_pid_running(curr_pid))

        is_running, pid = get_daemon_status(self.pid_file)
        self.assertTrue(is_running)
        self.assertEqual(pid, curr_pid)

        # Test stale PID (PID 9999999 unlikely to exist)
        stale_pid = 9999999
        write_pid(stale_pid, self.pid_file)
        is_running, pid = get_daemon_status(self.pid_file)
        self.assertFalse(is_running)
        # Stale PID file should have been cleaned up automatically
        self.assertFalse(self.pid_file.exists())


class TestVoiceDateStats(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_stats.db"
        self.db = Database(self.db_path)

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_empty_voice_stats(self):
        stats = self.db.get_voice_date_stats()
        self.assertEqual(stats["total_with_date"], 0)

    def test_voice_stats_calculation(self):
        from datetime import datetime, timezone

        # 2 messages on 2024-03-01
        self.db.save_message(
            chat_id=1,
            msg_id=10,
            media_type="voice",
            duration_sec=10.0,
            msg_date=datetime(2024, 3, 1, 10, 0, tzinfo=timezone.utc),
        )
        self.db.save_message(
            chat_id=1,
            msg_id=11,
            media_type="video_note",
            duration_sec=20.0,
            msg_date=datetime(2024, 3, 1, 14, 0, tzinfo=timezone.utc),
        )
        # 1 message on 2024-03-02
        self.db.save_message(
            chat_id=1,
            msg_id=12,
            media_type="voice",
            duration_sec=30.0,
            msg_date=datetime(2024, 3, 2, 11, 0, tzinfo=timezone.utc),
        )
        # 1 message on 2024-03-05
        self.db.save_message(
            chat_id=2,
            msg_id=20,
            media_type="voice",
            duration_sec=40.0,
            msg_date=datetime(2024, 3, 5, 18, 0, tzinfo=timezone.utc),
        )
        # 1 message in 2023
        self.db.save_message(
            chat_id=2,
            msg_id=21,
            media_type="voice",
            duration_sec=50.0,
            msg_date=datetime(2023, 5, 10, 12, 0, tzinfo=timezone.utc),
        )

        stats = self.db.get_voice_date_stats()
        self.assertEqual(stats["total_with_date"], 5)
        self.assertEqual(stats["active_days_count"], 4)
        self.assertAlmostEqual(stats["avg_per_active_day"], 5 / 4)
        self.assertEqual(stats["peak_day_count"], 2)
        self.assertEqual(stats["total_duration_sec"], 150.0)
        self.assertAlmostEqual(stats["avg_duration_sec"], 30.0)
        self.assertEqual(stats["all_years"], [2023, 2024])

        # Filter by year 2024
        stats_2024 = self.db.get_voice_date_stats(year=2024)
        self.assertEqual(stats_2024["total_with_date"], 4)
        self.assertEqual(stats_2024["all_years"], [2024])

        # Filter by year 2023
        stats_2023 = self.db.get_voice_date_stats(year=2023)
        self.assertEqual(stats_2023["total_with_date"], 1)

        # Check integrated get_stats()
        full_stats = self.db.get_stats()
        self.assertIn("voice_date_stats", full_stats)
        self.assertEqual(full_stats["voice_date_stats"]["total_with_date"], 5)

    def test_mark_message_skipped_with_msg_date(self):
        from datetime import datetime, timezone

        self.db.mark_message_skipped(
            chat_id=5,
            msg_id=50,
            reason="Outgoing message",
            media_type="voice",
            msg_date=datetime(2025, 1, 15, 9, 30, tzinfo=timezone.utc),
            duration_sec=18.0,
        )
        msg = self.db.get_message(5, 50)
        self.assertIsNotNone(msg)
        self.assertEqual(msg["status"], "skipped")
        self.assertIsNotNone(msg["msg_date"])

        stats = self.db.get_voice_date_stats()
        self.assertEqual(stats["total_with_date"], 1)


class TestHeatmapUI(unittest.TestCase):
    def test_get_heatmap_cell(self):
        from tg_voicer.ui import get_heatmap_cell

        self.assertIn("·", get_heatmap_cell(0))
        self.assertIn("■", get_heatmap_cell(1))
        self.assertIn("■", get_heatmap_cell(4))
        self.assertIn("■", get_heatmap_cell(7))
        self.assertIn("■", get_heatmap_cell(12))

        # Show number
        self.assertIn("5", get_heatmap_cell(5, show_number=True))
        self.assertIn("15", get_heatmap_cell(15, show_number=True))

    def test_heatmap_renderers(self):
        from datetime import datetime, timezone
        from tg_voicer.ui import (
            render_voice_metrics_table,
            render_dow_hour_heatmap,
            render_month_year_heatmap,
            render_calendar_heatmap,
            print_voice_heatmap,
            print_stats_table,
        )

        # Empty data handling
        self.assertIsNone(render_voice_metrics_table({"total_with_date": 0}))
        self.assertIsNone(render_dow_hour_heatmap({"total_with_date": 0}))
        self.assertIsNone(render_month_year_heatmap({"total_with_date": 0}))
        self.assertIsNone(render_calendar_heatmap({"total_with_date": 0}))

        # Mock voice stats
        now = datetime(2024, 6, 15, 14, 0, tzinfo=timezone.utc)
        mock_stats = {
            "total_with_date": 10,
            "earliest_date": datetime(2024, 1, 10, 10, 0, tzinfo=timezone.utc),
            "latest_date": now,
            "total_span_days": 157,
            "active_days_count": 8,
            "avg_per_active_day": 1.25,
            "avg_per_day_span": 0.064,
            "peak_day_date": now.date(),
            "peak_day_count": 3,
            "total_duration_sec": 240.0,
            "avg_duration_sec": 24.0,
            "by_date": {now.date(): 3, datetime(2024, 1, 10).date(): 2},
            "by_dow": {0: 2, 1: 3, 5: 5},
            "by_hour": {10: 2, 14: 8},
            "by_dow_hour": {(1, 14): 3, (5, 10): 2},
            "by_year_month": {(2024, 1): 2, (2024, 6): 8},
            "all_years": [2024],
            "recent_30d_count": 3,
            "avg_recent_30d": 0.1,
        }

        # Verify render functions return rich components
        m_tbl = render_voice_metrics_table(mock_stats)
        self.assertIsNotNone(m_tbl)

        dow_tbl = render_dow_hour_heatmap(mock_stats)
        self.assertIsNotNone(dow_tbl)

        ym_tbl = render_month_year_heatmap(mock_stats)
        self.assertIsNotNone(ym_tbl)

        cal_panel = render_calendar_heatmap(mock_stats, weeks=12)
        self.assertIsNotNone(cal_panel)

        cal_panel_yr = render_calendar_heatmap(mock_stats, target_year=2024)
        self.assertIsNotNone(cal_panel_yr)

        # Print functions shouldn't raise exceptions
        print_voice_heatmap(mock_stats)
        print_voice_heatmap({"total_with_date": 0})
        print_stats_table({"transcribed_done": 10}, [], voice_stats=mock_stats)


class TestCLIArgs(unittest.TestCase):
    def test_heatmap_args(self):
        import argparse
        import sys

        # Re-parse arguments using main.py parser structure
        from main import main

        # Create test parser matching main.py
        parser = argparse.ArgumentParser()
        parser.add_argument("--stats", action="store_true")
        parser.add_argument("--heatmap", action="store_true")
        parser.add_argument("--heatmap-year", type=int)
        parser.add_argument("--heatmap-weeks", type=int)

        args = parser.parse_args(["--heatmap"])
        self.assertTrue(args.heatmap)

        args_yr = parser.parse_args(["--heatmap-year", "2024"])
        self.assertEqual(args_yr.heatmap_year, 2024)

        args_w = parser.parse_args(["--heatmap-weeks", "30"])
        self.assertEqual(args_w.heatmap_weeks, 30)

    def test_lang_args(self):
        from main import parse_args
        import sys

        old_argv = sys.argv
        try:
            sys.argv = ["main.py", "--lang", "ru"]
            args = parse_args()
            self.assertEqual(args.language, "ru")

            sys.argv = ["main.py", "--lang", "en"]
            args_en = parse_args()
            self.assertEqual(args_en.language, "en")
        finally:
            sys.argv = old_argv


class TestI18n(unittest.TestCase):
    def test_default_language_and_switch(self):
        from tg_voicer.i18n import get_language, set_language, t

        set_language("en")
        self.assertEqual(get_language(), "en")
        self.assertEqual(t("media_voice"), "Voice note")

        set_language("ru")
        self.assertEqual(get_language(), "ru")
        self.assertEqual(t("media_voice"), "Голосовое")

        # Fallback to English for unknown language
        set_language("fr")
        self.assertEqual(get_language(), "en")
        self.assertEqual(t("media_voice"), "Voice note")

    def test_day_and_month_names(self):
        from tg_voicer.i18n import get_day_names, get_month_names, set_language

        set_language("en")
        en_days = get_day_names(full=True)
        self.assertEqual(en_days[0], "Monday")
        self.assertEqual(en_days[6], "Sunday")
        en_months = get_month_names()
        self.assertEqual(en_months[1], "Jan")

        set_language("ru")
        ru_days = get_day_names(full=True)
        self.assertEqual(ru_days[0], "Понедельник")
        self.assertEqual(ru_days[6], "Воскресенье")
        ru_months = get_month_names()
        self.assertEqual(ru_months[1], "Янв")

    def test_config_language_setting(self):
        from tg_voicer.config import AppConfig

        # Default
        cfg = AppConfig()
        self.assertEqual(cfg.language, "en")

        # Dict override
        cfg._apply_dict({"general": {"language": "ru"}})
        self.assertEqual(cfg.language, "ru")

        cfg._apply_dict({"language": "en"})
        self.assertEqual(cfg.language, "en")


if __name__ == "__main__":
    unittest.main()


