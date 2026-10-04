#!/usr/bin/env python3
"""
TG-Voicer: CLI entry point.
Automated Telegram Premium speech-to-text transcriber for voice messages and video notes.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path

from tg_voicer import __version__
from tg_voicer.app import VoicerApp
from tg_voicer.config import AppConfig, DEFAULT_CONFIG_TEMPLATE
from tg_voicer.database import Database
from tg_voicer.i18n import set_language, t
from tg_voicer.ui import console
from tg_voicer.utils import print_stats_table, print_voice_heatmap, setup_logging


def prompt_credentials_if_needed(config: AppConfig, config_path: Path) -> None:
    """Interactively prompt user for API credentials if they are not provided."""
    if config.telegram.api_id and config.telegram.api_hash:
        return

    print("\n" + "=" * 65)
    print(t("auth_header"))
    print("=" * 65)
    print(t("auth_desc"))

    while not config.telegram.api_id:
        val = input(t("auth_prompt_id")).strip()
        if val.isdigit():
            config.telegram.api_id = int(val)
        else:
            print(t("auth_err_id"))

    while not config.telegram.api_hash:
        val = input(t("auth_prompt_hash")).strip()
        if len(val) >= 10:
            config.telegram.api_hash = val
        else:
            print(t("auth_err_hash"))

    # Save credentials into config.toml
    if config_path.exists():
        content = config_path.read_text(encoding="utf-8")
        # Update api_id and api_hash in file
        import re
        content = re.sub(r'api_id\s*=\s*\d+', f'api_id = {config.telegram.api_id}', content)
        content = re.sub(r'api_hash\s*=\s*["\'].*?["\']', f'api_hash = "{config.telegram.api_hash}"', content)
        config_path.write_text(content, encoding="utf-8")
        print(t("auth_saved", path=config_path))
    else:
        # Create config.toml with credentials
        template = DEFAULT_CONFIG_TEMPLATE.replace(
            "api_id = 0", f"api_id = {config.telegram.api_id}"
        ).replace(
            'api_hash = ""', f'api_hash = "{config.telegram.api_hash}"'
        )
        config_path.write_text(template, encoding="utf-8")
        print(t("auth_created", path=config_path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tg-voicer",
        description="Automated Telegram Premium speech-to-text transcriber for voice notes & video notes.",
    )
    parser.add_argument(
        "-c", "--config",
        dest="config_path",
        default="config.toml",
        help="Path to configuration file (default: config.toml)",
    )
    parser.add_argument(
        "--lang", "--language",
        dest="language",
        choices=["en", "ru"],
        default=None,
        help="Interface and output language: 'en' (default) or 'ru'",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Generate default config.toml template and exit",
    )
    parser.add_argument(
        "--live-only",
        action="store_true",
        help="Listen only for new incoming voice notes (skip historical backfill)",
    )
    parser.add_argument(
        "--backfill-only",
        action="store_true",
        help="Process historical chat messages only and exit upon completion",
    )
    parser.add_argument(
        "--reset-backfill",
        action="store_true",
        help="Reset history scan cursors in database to re-scan all chats from start",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Display transcription statistics, activity heatmap, and exit",
    )
    parser.add_argument(
        "--heatmap",
        action="store_true",
        help="Display voice message recording date heatmap and activity metrics",
    )
    parser.add_argument(
        "--heatmap-year",
        type=int,
        metavar="YEAR",
        help="Filter activity calendar by specific year (e.g. 2024)",
    )
    parser.add_argument(
        "--heatmap-weeks",
        type=int,
        metavar="WEEKS",
        help="Number of weeks to display in activity calendar (default: adaptive)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run: search messages and evaluate filters without calling transcription API",
    )
    parser.add_argument(
        "--auth-qr",
        action="store_true",
        help="Authenticate using Telegram mobile QR code scan (default)",
    )
    parser.add_argument(
        "--auth-phone",
        action="store_true",
        help="Authenticate using phone number and SMS code instead of QR code",
    )
    parser.add_argument(
        "-d", "--daemon",
        action="store_true",
        help="Run TG-Voicer in background mode as a detached daemon",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop running TG-Voicer background daemon",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart TG-Voicer background daemon",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check status of background daemon and display metrics",
    )
    parser.add_argument(
        "--logs",
        action="store_true",
        help="View background daemon log file",
    )
    parser.add_argument(
        "-f", "--follow",
        action="store_true",
        help="Follow log stream in real time (for --logs)",
    )
    parser.add_argument(
        "-n", "--lines",
        type=int,
        default=50,
        help="Number of recent log lines to display (default: 50, for --logs)",
    )
    parser.add_argument(
        "--daemon-worker",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose DEBUG logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"tg-voicer {__version__}",
    )
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> None:
    config_file = Path(args.config_path)

    # Handle --init-config
    if args.init_config:
        if config_file.exists():
            print(f"⚠️ Configuration file already exists: {config_file}")
        else:
            AppConfig.create_default_template(config_file)
            print(f"✅ Default configuration template created: {config_file}")
        return

    # Create default config if missing
    if not config_file.exists():
        AppConfig.create_default_template(config_file)
        print(f"ℹ️ Created default configuration file: {config_file}")

    config = AppConfig.load(config_file)

    if args.language:
        config.language = args.language
        set_language(args.language)

    if args.auth_phone:
        config.telegram.auth_method = "phone"
    elif args.auth_qr:
        config.telegram.auth_method = "qr"

    if args.verbose:
        config.logging.level = "DEBUG"

    # Setup logging
    setup_logging(config.logging)

    # Handle --heatmap
    if args.heatmap or ((args.heatmap_year is not None or args.heatmap_weeks is not None) and not args.stats):
        db = Database(config.storage.db_path)
        voice_stats = db.get_voice_date_stats(year=args.heatmap_year)
        print_voice_heatmap(voice_stats, weeks=args.heatmap_weeks, target_year=args.heatmap_year)
        db.close()
        return

    # Handle --stats
    if args.stats:
        db = Database(config.storage.db_path)
        stats = db.get_stats()
        voice_stats = db.get_voice_date_stats(year=args.heatmap_year)
        recent = db.get_recent_transcriptions(limit=10)
        print_stats_table(
            stats,
            recent,
            voice_stats=voice_stats,
            heatmap_year=args.heatmap_year,
            heatmap_weeks=args.heatmap_weeks,
        )
        db.close()
        return

    # Handle --reset-backfill
    if args.reset_backfill:
        db = Database(config.storage.db_path)
        count = db.reset_all_cursors()
        console.print(f"[bold green]{t('cursors_reset_msg', count=count)}[/bold green]")
        db.close()
        return

    # Check credentials
    prompt_credentials_if_needed(config, config_file)

    # Initialize and run app
    app = VoicerApp(
        config=config,
        live_only=args.live_only,
        backfill_only=args.backfill_only,
        dry_run=args.dry_run,
    )

    loop = asyncio.get_running_loop()

    # Setup signal handlers for graceful exit
    def handle_signal():
        asyncio.create_task(app.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except (NotImplementedError, RuntimeError):
            pass

    try:
        await app.start()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await app.stop()


def main() -> None:
    args = parse_args()

    if args.language:
        set_language(args.language)

    # Handle daemon management commands before entering async loop:
    if args.stop:
        from tg_voicer.daemon import stop_daemon
        stop_daemon(config_path=args.config_path, language=args.language)
        sys.exit(0)

    if args.status:
        from tg_voicer.daemon import status_daemon
        status_daemon(config_path=args.config_path, language=args.language)
        sys.exit(0)

    if args.logs:
        from tg_voicer.daemon import view_logs
        view_logs(lines=args.lines, follow=args.follow, config_path=args.config_path, language=args.language)
        sys.exit(0)

    extra_worker_args = []
    if args.verbose:
        extra_worker_args.append("-v")
    if args.live_only:
        extra_worker_args.append("--live-only")
    if args.backfill_only:
        extra_worker_args.append("--backfill-only")
    if args.dry_run:
        extra_worker_args.append("--dry-run")
    if args.auth_phone:
        extra_worker_args.append("--auth-phone")
    if args.language:
        extra_worker_args.extend(["--lang", args.language])

    if args.restart:
        from tg_voicer.daemon import restart_daemon
        restart_daemon(config_path=args.config_path, extra_args=extra_worker_args, language=args.language)
        sys.exit(0)

    if args.daemon:
        from tg_voicer.daemon import start_daemon
        start_daemon(config_path=args.config_path, extra_args=extra_worker_args, language=args.language)
        sys.exit(0)

    # If running as the spawned background worker, manage PID file
    if args.daemon_worker:
        import atexit
        from tg_voicer.daemon import write_pid, remove_pid
        write_pid(os.getpid())
        atexit.register(remove_pid)

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        console.print(f"\n[dim]{t('app_stopped_user')}[/dim]")
        sys.exit(0)
    finally:
        if args.daemon_worker:
            from tg_voicer.daemon import remove_pid
            remove_pid()


if __name__ == "__main__":
    main()
