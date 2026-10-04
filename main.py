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
from tg_voicer.utils import print_stats_table, setup_logging


def prompt_credentials_if_needed(config: AppConfig, config_path: Path) -> None:
    """Interactively prompt user for API credentials if they are not provided."""
    if config.telegram.api_id and config.telegram.api_hash:
        return

    print("\n" + "=" * 65)
    print("🔑 Настройка Telegram API Credentials")
    print("=" * 65)
    print("Для работы Telegram Client требуются api_id и api_hash.")
    print("Их можно получить бесплатно за 1 минуту на сайте:")
    print(" 👉 https://my.telegram.org (раздел 'API development tools')\n")

    while not config.telegram.api_id:
        val = input("Введите ваш api_id (число): ").strip()
        if val.isdigit():
            config.telegram.api_id = int(val)
        else:
            print("❌ api_id должен быть целым числом!")

    while not config.telegram.api_hash:
        val = input("Введите ваш api_hash (32-значная строка): ").strip()
        if len(val) >= 10:
            config.telegram.api_hash = val
        else:
            print("❌ api_hash не может быть пустым!")

    # Save credentials into config.toml
    if config_path.exists():
        content = config_path.read_text(encoding="utf-8")
        # Update api_id and api_hash in file
        import re
        content = re.sub(r'api_id\s*=\s*\d+', f'api_id = {config.telegram.api_id}', content)
        content = re.sub(r'api_hash\s*=\s*["\'].*?["\']', f'api_hash = "{config.telegram.api_hash}"', content)
        config_path.write_text(content, encoding="utf-8")
        print(f"✅ Данные успешно сохранены в {config_path}!\n")
    else:
        # Create config.toml with credentials
        template = DEFAULT_CONFIG_TEMPLATE.replace(
            "api_id = 0", f"api_id = {config.telegram.api_id}"
        ).replace(
            'api_hash = ""', f'api_hash = "{config.telegram.api_hash}"'
        )
        config_path.write_text(template, encoding="utf-8")
        print(f"✅ Создан конфигурационный файл {config_path} с вашими данными!\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tg-voicer",
        description="Автоматическая расшифровка голосовых и кружочков в Telegram через Telegram Premium.",
    )
    parser.add_argument(
        "-c", "--config",
        dest="config_path",
        default="config.toml",
        help="Путь к файлу конфигурации (по умолчанию: config.toml)",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Создать шаблон config.toml и выйти",
    )
    parser.add_argument(
        "--live-only",
        action="store_true",
        help="Работать только на отлов новых голосовых (без сканирования истории)",
    )
    parser.add_argument(
        "--backfill-only",
        action="store_true",
        help="Только пройтись по архивной истории и выйти по завершении",
    )
    parser.add_argument(
        "--reset-backfill",
        action="store_true",
        help="Сбросить курсоры истории в базе (для повторного полного сканирования)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Вывести статистику расшифровок из базы данных и выйти",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Тестовый прогон: поиск сообщений и проверка фильтров без вызова API расшифровки",
    )
    parser.add_argument(
        "--auth-qr",
        action="store_true",
        help="Авторизоваться через QR-код (по умолчанию)",
    )
    parser.add_argument(
        "--auth-phone",
        action="store_true",
        help="Авторизоваться по номеру телефона вместо QR-кода",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Включить подробный отладочный вывод (DEBUG)",
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
            print(f"⚠️ Файл конфигурации уже существует: {config_file}")
        else:
            AppConfig.create_default_template(config_file)
            print(f"✅ Шаблон конфигурации создан: {config_file}")
        return

    # Load configuration
    if not config_file.exists():
        AppConfig.create_default_template(config_file)
        print(f"ℹ️ Создан конфигурационный файл по умолчанию: {config_file}")

    config = AppConfig.load(config_file)

    if args.auth_phone:
        config.telegram.auth_method = "phone"
    elif args.auth_qr:
        config.telegram.auth_method = "qr"

    if args.verbose:
        config.logging.level = "DEBUG"

    # Setup logging
    setup_logging(config.logging)

    # Handle --stats
    if args.stats:
        db = Database(config.storage.db_path)
        stats = db.get_stats()
        recent = db.get_recent_transcriptions(limit=10)
        print_stats_table(stats, recent)
        return

    # Handle --reset-backfill
    if args.reset_backfill:
        db = Database(config.storage.db_path)
        count = db.reset_all_cursors()
        print(f"✅ Курсоры истории сброшены для {count} чатов. При следующем запуске история будет просканирована заново.")
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
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n👋 Программа завершена пользователем.")
        sys.exit(0)


if __name__ == "__main__":
    main()
