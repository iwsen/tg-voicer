"""
Internationalization (i18n) module for TG-Voicer.
Supports English (en - default) and Russian (ru).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "ru")

_current_language = DEFAULT_LANGUAGE


TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        # App banner
        "banner_title": "Telegram Voice Transcriber",
        "banner_user": "👤 User: ",
        "banner_premium": "🌟 Telegram Premium: ",
        "banner_premium_active": "ACTIVE\n",
        "banner_premium_inactive": "NOT DETECTED (required for transcription!)\n",
        "banner_mode": "⚙️  Mode: ",
        "banner_db": "📁 Database: ",
        "banner_filters": "🎯 Filters: ",
        "mode_live_only": "New messages only (Realtime)",
        "mode_backfill_only": "Historical archive only (Backfill)",
        "mode_all": "History + New messages",
        "filter_ignore_types": "Ignore types: {types}",
        "filter_ignored_chats": "Ignored chats: {count}",
        "filter_ignored_users": "Ignored users: {count}",
        "filter_allowed_chats": "Allowed chats: {count}",
        "filter_allowed_users": "Allowed users: {count}",

        # Peer and badges
        "peer_in": "in",
        "chat_type_dm": "DM",
        "media_voice": "Voice note",
        "media_video_note": "Video note",
        "media_voice_short": "Voice",
        "media_video_short": "Video",
        "source_live": "LIVE",
        "source_backfill": "BACKFILL",

        # Transcribe & Scan
        "scan_history": "Scanning history:",
        "chat_completed": "Chat history completed:",
        "all_completed": "All available chat history has been fully processed!",
        "empty_audio": "[empty audio]",
        "cached_tag": "(cached) ",
        "transcription_error": "Error: {error}",
        "transcription_pending": "Request sent to Telegram. Server processing...",
        "flood_wait_notice": "server temporarily rate-limited transcription requests.",
        "flood_wait_pause": "Pause:",
        "flood_wait_resume": "• Auto-resuming at",
        "app_ready": "🚀 TG-Voicer started and ready. Press Ctrl+C to exit.\n",
        "app_stopped_user": "👋 Program terminated by user.",
        "app_stopping": "🛑 Stopping TG-Voicer services...",
        "app_session_safe": "👋 Telegram session safely closed.",
        "cursors_reset_msg": "✅ History cursors reset for {count} chats. History will be re-scanned on next launch.",

        # Network
        "net_offline_title": "Internet is unavailable or Telegram connection lost.",
        "net_offline_desc": "Operations paused. Waiting for connection recovery (checking every {sec}s)...",
        "net_restored_title": "Internet and Telegram connection successfully restored!",
        "net_restored_desc": "Resuming message processing...",

        # Voice metrics table
        "metrics_title": "📅 VOICE MESSAGE METRICS (by recording date)",
        "metric_col": "Metric",
        "value_col": "Value",
        "metric_total_with_date": "🎙️ Total voice notes with date",
        "metric_period": "📅 Recording period",
        "metric_period_days": "({days} days)",
        "metric_active_days": "🗓️ Active days with voice notes",
        "metric_active_days_pct": "({pct:.1f}% of period days)",
        "metric_avg_active": "⚡ Average on active days",
        "metric_avg_active_unit": "voices/day",
        "metric_avg_span": "📈 Average over whole period",
        "metric_every_n_days": " (~1 every {days} days)",
        "metric_recent_30d": "📆 In last 30 days",
        "metric_recent_unit": "pcs.",
        "metric_peak_day": "🏆 Single-day record (peak)",
        "metric_avg_dur": "⏱️ Average duration",
        "metric_avg_dur_unit": "sec",
        "metric_total_dur_fmt": "(total {mins} min {secs} sec)",
        "metric_peak_dow": "🔝 Most active day of week",

        # Heatmaps
        "heatmap_dow_hour_title": "🔥 Heatmap: Day of Week × Hour of Day (local time)",
        "heatmap_col_day": "Day",
        "heatmap_col_total": "Total",
        "heatmap_month_year_title": "📅 Heatmap: Activity by Month and Year",
        "heatmap_col_year": " Year ",
        "heatmap_col_avg_day": "  Avg/d ",
        "heatmap_cal_title_year": "📆 Daily Activity Calendar ({year})",
        "heatmap_cal_title_range": "📆 Daily Activity Calendar ({start} — {end})",
        "heatmap_half1": "▶ 1st Half (Jan — Jun)",
        "heatmap_half2": "▶ 2nd Half (Jul — Dec)",
        "heatmap_legend": "     Legend: [dim]·[/dim] 0   [#2ea043]■[/] 1-2   [#3fb950]■[/] 3-5   [bold #d29922]■[/] 6-8   [bold #f85149]■[/] 9+",
        "heatmap_no_data": "ℹ️ No voice message date records available to render heatmap.",
        "heatmap_hint_year": "💡 Records span {start}–{end}. For a detailed calendar of a specific year: ",

        # Stats table
        "stats_title": "📊 TG-VOICER STATISTICS",
        "stat_transcribed": "✅ Successfully transcribed",
        "stat_live": "⚡ Captured in realtime",
        "stat_pending": "⏳ Pending processing",
        "stat_skipped": "⏭️ Skipped by filters",
        "stat_failed": "⚠️ Errors",
        "stat_chats_total": "📁 Total chats processed",
        "stat_chats_completed": "🏁 Chats with completed history",
        "recent_title": "📝 Recent Transcriptions",
        "recent_col_num": "#",
        "recent_col_type": "Type",
        "recent_col_peer": "Chat / Author",
        "recent_col_dur": "Dur.",
        "recent_col_text": "Transcription",

        # Daemon
        "daemon_already_running": "⚠️ TG-Voicer is already running in background (PID: {pid}).",
        "daemon_status_hint": "Check status:  python3 main.py --status",
        "daemon_logs_hint": "View logs:     python3 main.py --logs -f",
        "daemon_stop_hint": "To stop:       python3 main.py --stop",
        "daemon_restart_hint": "To restart:    python3 main.py --restart",
        "daemon_no_session_title": "❌ Telegram authorization session not found!",
        "daemon_no_session_desc": (
            "For initial login (QR code scanning or phone code),\n"
            "run the script once in normal terminal:\n\n"
            "   python3 main.py\n\n"
            "After logging in, you can run TG-Voicer in the background without prompts."
        ),
        "daemon_start_failed": "❌ Error: background process exited immediately after start.",
        "daemon_check_logs": "Check error log in:",
        "daemon_panel_title": "TG-Voicer Background Mode",
        "daemon_started_header": "🚀 TG-Voicer successfully started in background!\n\n",
        "daemon_pid": "  • Process PID: ",
        "daemon_log": "  • Log file:    ",
        "daemon_ctrl_header": "Background service controls:\n",
        "daemon_ctrl_status": "— Check status and stats\n",
        "daemon_ctrl_logs": "— Follow logs in real-time\n",
        "daemon_ctrl_stop": "— Stop background process\n",
        "daemon_ctrl_restart": "— Restart background process\n",
        "daemon_not_running": "ℹ️ TG-Voicer is not currently running in background.",
        "daemon_stopping": "⏳ Stopping TG-Voicer background process (PID: {pid})...",
        "daemon_signal_failed": "Failed to send termination signal to process {pid}: {error}",
        "daemon_stopped_ok": "✅ TG-Voicer (PID: {pid}) successfully stopped.",
        "daemon_force_kill": "⚠️ Process did not terminate in time. Forcefully terminating (SIGKILL)...",
        "daemon_force_stopped": "✅ TG-Voicer (PID: {pid}) forcefully stopped.",
        "daemon_status_panel_title": "Service Status",
        "daemon_status_header": "🎙️  TG-VOICER DAEMON STATUS\n\n",
        "daemon_status_label": "• Service status: ",
        "daemon_status_active": "● ACTIVE (RUNNING IN BACKGROUND)\n",
        "daemon_status_pid_label": "• Process PID:    ",
        "daemon_status_inactive": "○ STOPPED (NOT RUNNING)\n",
        "daemon_status_start_hint": "  (Start with: python3 main.py --daemon)\n",
        "daemon_status_cfg_label": "• Configuration:  ",
        "daemon_status_log_label": "• Log file:       ",
        "daemon_status_db_label": "• Database:       ",
        "daemon_db_stats_failed": "Could not read database statistics: {error}",
        "daemon_log_not_found": "Log file has not been created yet: {path}",
        "daemon_logs_stream": "Streaming logs from {path} (Press Ctrl+C to exit)...\n",
        "daemon_logs_exit": "Exited log viewer.",
        "daemon_logs_read_failed": "Could not read log file: {error}",

        # Auth & Credentials
        "auth_header": "🔑 Setup Telegram API Credentials",
        "auth_desc": (
            "api_id and api_hash are required to run the Telegram Client.\n"
            "You can obtain them for free in 1 minute at:\n"
            " 👉 https://my.telegram.org ('API development tools')\n"
        ),
        "auth_prompt_id": "Enter your api_id (number): ",
        "auth_err_id": "❌ api_id must be an integer!",
        "auth_prompt_hash": "Enter your api_hash (32-character string): ",
        "auth_err_hash": "❌ api_hash cannot be empty!",
        "auth_saved": "✅ Credentials saved to {path}!\n",
        "auth_created": "✅ Created configuration file {path} with your credentials!\n",
        "qr_header": " 📱 Telegram QR Code Login",
        "qr_step1": " 1. Open Telegram on your phone",
        "qr_step2": " 2. Go to: Settings -> Devices -> Link Desktop Device",
        "qr_step3": " 3. Point camera at the QR code below:",
        "qr_saved_file": "🖼️ QR code also saved to file: {path}",
        "qr_waiting": "⏳ Waiting for QR code scan... (scan with Telegram camera)",
        "qr_scanned": "✅ QR code successfully scanned!",
        "qr_2fa_notice": "🔐 Two-Factor Authentication (2FA) is enabled on your account.",
        "qr_2fa_prompt": "Enter cloud password (2FA): ",
        "qr_2fa_accepted": "✅ 2FA password accepted!",
        "qr_timeout": "🔄 QR code expired (30s). Refreshing QR code...",
        "qr_error": "Error during QR code login: {error}",
        "login_phone_start": "Starting phone number login...",
    },
    "ru": {
        # App banner
        "banner_title": "Telegram Voice Transcriber",
        "banner_user": "👤 Пользователь: ",
        "banner_premium": "🌟 Telegram Premium: ",
        "banner_premium_active": "АКТИВЕН\n",
        "banner_premium_inactive": "НЕ ОБНАРУЖЕН (требуется для расшифровки!)\n",
        "banner_mode": "⚙️  Режим: ",
        "banner_db": "📁 База: ",
        "banner_filters": "🎯 Фильтры: ",
        "mode_live_only": "Только новые сообщения (Realtime)",
        "mode_backfill_only": "Только архивные сообщения (Backfill)",
        "mode_all": "История + Новые сообщения",
        "filter_ignore_types": "Игнор: {types}",
        "filter_ignored_chats": "Игнор чатов: {count}",
        "filter_ignored_users": "Игнор польз.: {count}",
        "filter_allowed_chats": "Белый список чатов: {count}",
        "filter_allowed_users": "Белый список польз.: {count}",

        # Peer and badges
        "peer_in": "в",
        "chat_type_dm": "ЛС",
        "media_voice": "Голосовое",
        "media_video_note": "Кружочек",
        "media_voice_short": "Голос",
        "media_video_short": "Кружок",
        "source_live": "LIVE",
        "source_backfill": "BACKFILL",

        # Transcribe & Scan
        "scan_history": "Сканирование истории:",
        "chat_completed": "История чата завершена:",
        "all_completed": "Вся доступная история чатов полностью обработана!",
        "empty_audio": "[пустая запись]",
        "cached_tag": "(из кеша) ",
        "transcription_error": "Ошибка: {error}",
        "transcription_pending": "Запрос отправлен в Telegram. Обработка на сервере...",
        "flood_wait_notice": "сервер временно ограничил запросы на расшифровку.",
        "flood_wait_pause": "Пауза:",
        "flood_wait_resume": "• Авто-возобновление в",
        "app_ready": "🚀 TG-Voicer запущен и готов к работе. Для выхода нажмите Ctrl+C.\n",
        "app_stopped_user": "👋 Программа завершена пользователем.",
        "app_stopping": "🛑 Остановка сервисов TG-Voicer...",
        "app_session_safe": "👋 Сессия Telegram безопасно завершена.",
        "cursors_reset_msg": "✅ Курсоры истории сброшены для {count} чатов. При следующем запуске история будет просканирована заново.",

        # Network
        "net_offline_title": "Интернет недоступен или соединение с Telegram потеряно.",
        "net_offline_desc": "Операции приостановлены. Ожидание восстановления сети (проверка каждые {sec}с)...",
        "net_restored_title": "Соединение с интернетом и Telegram успешно восстановлено!",
        "net_restored_desc": "Возобновление обработки сообщений...",

        # Voice metrics table
        "metrics_title": "📅 СРЕДНИЕ ПОКАЗАТЕЛИ ПО ГОЛОСОВЫМ (по дате записи)",
        "metric_col": "Метрика",
        "value_col": "Значение",
        "metric_total_with_date": "🎙️ Всего голосовых с датой",
        "metric_period": "📅 Период записей",
        "metric_period_days": "({days} дн.)",
        "metric_active_days": "🗓️ Дней с голосовыми (активных)",
        "metric_active_days_pct": "({pct:.1f}% дней периода)",
        "metric_avg_active": "⚡ В среднем в активный день",
        "metric_avg_active_unit": "голос./день",
        "metric_avg_span": "📈 В среднем за весь период",
        "metric_every_n_days": " (~1 каждые {days} дн.)",
        "metric_recent_30d": "📆 За последние 30 дней",
        "metric_recent_unit": "шт.",
        "metric_peak_day": "🏆 Рекорд за один день (пик)",
        "metric_avg_dur": "⏱️ Средняя длительность",
        "metric_avg_dur_unit": "сек",
        "metric_total_dur_fmt": "(всего {mins} мин {secs} сек)",
        "metric_peak_dow": "🔝 Самый активный день недели",

        # Heatmaps
        "heatmap_dow_hour_title": "🔥 Тепловая карта: День недели × Время суток (локальное время)",
        "heatmap_col_day": "Дн",
        "heatmap_col_total": "Всего",
        "heatmap_month_year_title": "📅 Тепловая карта: Активность по месяцам и годам",
        "heatmap_col_year": " Год ",
        "heatmap_col_avg_day": "  Ср/дн ",
        "heatmap_cal_title_year": "📆 Календарь активности по дням ({year} год)",
        "heatmap_cal_title_range": "📆 Календарь активности по дням ({start} — {end})",
        "heatmap_half1": "▶ I полугодие (Янв — Июн)",
        "heatmap_half2": "▶ II полугодие (Июл — Дек)",
        "heatmap_legend": "     Легенда: [dim]·[/dim] 0   [#2ea043]■[/] 1-2   [#3fb950]■[/] 3-5   [bold #d29922]■[/] 6-8   [bold #f85149]■[/] 9+",
        "heatmap_no_data": "ℹ️ Нет данных о датах записи голосовых сообщений для построения тепловой карты.",
        "heatmap_hint_year": "💡 Записи охватывают {start}–{end} гг. Для детального календаря за определенный год: ",

        # Stats table
        "stats_title": "📊 TG-VOICER СТАТИСТИКА",
        "stat_transcribed": "✅ Успешно расшифровано",
        "stat_live": "⚡ Перехвачено в реальном времени",
        "stat_pending": "⏳ В процессе обработки",
        "stat_skipped": "⏭️ Пропущено фильтрами",
        "stat_failed": "⚠️ Ошибок",
        "stat_chats_total": "📁 Всего обработано чатов",
        "stat_chats_completed": "🏁 Чатов с пройденной историей",
        "recent_title": "📝 Последние расшифровки",
        "recent_col_num": "#",
        "recent_col_type": "Тип",
        "recent_col_peer": "Чат / Автор",
        "recent_col_dur": "Длит.",
        "recent_col_text": "Расшифровка",

        # Daemon
        "daemon_already_running": "⚠️ TG-Voicer уже запущен в фоновом режиме (PID: {pid}).",
        "daemon_status_hint": "Для проверки статуса:  python3 main.py --status",
        "daemon_logs_hint": "Для просмотра логов:   python3 main.py --logs -f",
        "daemon_stop_hint": "Для остановки:         python3 main.py --stop",
        "daemon_restart_hint": "Для перезапуска:       python3 main.py --restart",
        "daemon_no_session_title": "❌ Файл авторизации Telegram не найден!",
        "daemon_no_session_desc": (
            "Для первой авторизации (сканирования QR-кода или ввода кода из SMS)\n"
            "запустите скрипт один раз в обычном терминале:\n\n"
            "   python3 main.py\n\n"
            "После успешного входа вы сможете запускать TG-Voicer в фоне без паролей."
        ),
        "daemon_start_failed": "❌ Ошибка: фоновый процесс завершился сразу после запуска.",
        "daemon_check_logs": "Проверьте журнал ошибок в:",
        "daemon_panel_title": "Фоновый режим TG-Voicer",
        "daemon_started_header": "🚀 TG-Voicer успешно запущен в фоновом режиме!\n\n",
        "daemon_pid": "  • PID процесса: ",
        "daemon_log": "  • Журнал логов: ",
        "daemon_ctrl_header": "Управление фоновым сервисом:\n",
        "daemon_ctrl_status": "— Проверить статус и статистику\n",
        "daemon_ctrl_logs": "— Отслеживать логи вживую\n",
        "daemon_ctrl_stop": "— Остановить процесс\n",
        "daemon_ctrl_restart": "— Перезапустить процесс\n",
        "daemon_not_running": "ℹ️ TG-Voicer в данный момент не запущен в фоновом режиме.",
        "daemon_stopping": "⏳ Завершение фонового процесса TG-Voicer (PID: {pid})...",
        "daemon_signal_failed": "Не удалось отправить сигнал процессу {pid}: {error}",
        "daemon_stopped_ok": "✅ TG-Voicer (PID: {pid}) успешно остановлен.",
        "daemon_force_kill": "⚠️ Процесс не завершился вовремя. Принудительное завершение (SIGKILL)...",
        "daemon_force_stopped": "✅ TG-Voicer (PID: {pid}) принудительно остановлен.",
        "daemon_status_panel_title": "Статус сервиса",
        "daemon_status_header": "🎙️  TG-VOICER DAEMON STATUS\n\n",
        "daemon_status_label": "• Статус сервиса: ",
        "daemon_status_active": "● АКТИВЕН (РАБОТАЕТ В ФОНЕ)\n",
        "daemon_status_pid_label": "• PID процесса:   ",
        "daemon_status_inactive": "○ ОСТАНОВЛЕН (НЕ ЗАПУЩЕН)\n",
        "daemon_status_start_hint": "  (Запустите: python3 main.py --daemon)\n",
        "daemon_status_cfg_label": "• Конфигурация:   ",
        "daemon_status_log_label": "• Файл логов:     ",
        "daemon_status_db_label": "• База данных:    ",
        "daemon_db_stats_failed": "Не удалось прочесть статистику базы данных: {error}",
        "daemon_log_not_found": "Файл логов ещё не создан: {path}",
        "daemon_logs_stream": "Streaming logs from {path} (Нажмите Ctrl+C для выхода)...\n",
        "daemon_logs_exit": "Выход из просмотра логов.",
        "daemon_logs_read_failed": "Не удалось прочитать файл логов: {error}",

        # Auth & Credentials
        "auth_header": "🔑 Настройка Telegram API Credentials",
        "auth_desc": (
            "Для работы Telegram Client требуются api_id и api_hash.\n"
            "Их можно получить бесплатно за 1 минуту на сайте:\n"
            " 👉 https://my.telegram.org (раздел 'API development tools')\n"
        ),
        "auth_prompt_id": "Введите ваш api_id (число): ",
        "auth_err_id": "❌ api_id должен быть целым числом!",
        "auth_prompt_hash": "Введите ваш api_hash (32-значная строка): ",
        "auth_err_hash": "❌ api_hash не может быть пустым!",
        "auth_saved": "✅ Данные успешно сохранены в {path}!\n",
        "auth_created": "✅ Создан конфигурационный файл {path} с вашими данными!\n",
        "qr_header": " 📱 Авторизация через QR-код Telegram",
        "qr_step1": " 1. Откройте Telegram на телефоне",
        "qr_step2": " 2. Перейдите: Настройки -> Устройства -> Подключить устройство",
        "qr_step3": " 3. Наведите камеру Telegram на QR-код ниже:",
        "qr_saved_file": "🖼️ QR-код также сохранен в файл: {path}",
        "qr_waiting": "⏳ Ожидание сканирования QR-кода... (наведите камеру из Telegram)",
        "qr_scanned": "✅ QR-код успешно отсканирован!",
        "qr_2fa_notice": "🔐 На вашем аккаунте включена двухфакторная аутентификация (2FA).",
        "qr_2fa_prompt": "Введите облачный пароль (2FA): ",
        "qr_2fa_accepted": "✅ 2FA пароль принят!",
        "qr_timeout": "🔄 Время действия QR-кода истекло (30с). Обновляем QR-код...",
        "qr_error": "Ошибка при авторизации по QR-коду: {error}",
        "login_phone_start": "Запуск авторизации по номеру телефона...",
    },
}

DAY_NAMES_FULL = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "ru": ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"],
}

DAY_NAMES_SHORT = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "ru": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
}

MONTH_NAMES_SHORT = {
    "en": {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
    },
    "ru": {
        1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр", 5: "Май", 6: "Июн",
        7: "Июл", 8: "Авг", 9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек",
    },
}


def get_language() -> str:
    """Return currently active language code ('en' or 'ru')."""
    return _current_language


def set_language(lang: Optional[str]) -> str:
    """Set the active language ('en' or 'ru'). Defaults to 'en'."""
    global _current_language
    if not lang:
        _current_language = DEFAULT_LANGUAGE
        return _current_language

    normalized = str(lang).strip().lower()
    if normalized.startswith("ru"):
        _current_language = "ru"
    else:
        _current_language = "en"
    return _current_language


def t(key: str, default: Optional[str] = None, **kwargs: Any) -> str:
    """
    Get translated string for key, formatting with kwargs if provided.
    Falls back to English and then to the key itself or default if missing.
    """
    lang = get_language()
    dict_lang = TRANSLATIONS.get(lang, {})
    val = dict_lang.get(key)
    if val is None:
        val = TRANSLATIONS.get(DEFAULT_LANGUAGE, {}).get(key, default or key)

    if kwargs:
        try:
            return val.format(**kwargs)
        except Exception:
            return val
    return val


def get_day_names(full: bool = True) -> List[str]:
    """Return list of 7 day of week names starting Monday."""
    lang = get_language()
    lookup = DAY_NAMES_FULL if full else DAY_NAMES_SHORT
    return lookup.get(lang, lookup[DEFAULT_LANGUAGE])


def get_day_name(dow: int, full: bool = True) -> str:
    """Return day of week name (0 = Monday, 6 = Sunday)."""
    days = get_day_names(full=full)
    if 0 <= dow < len(days):
        return days[dow]
    return str(dow)


def get_month_names() -> Dict[int, str]:
    """Return 1-indexed dictionary of short month names."""
    lang = get_language()
    return MONTH_NAMES_SHORT.get(lang, MONTH_NAMES_SHORT[DEFAULT_LANGUAGE])


def format_duration(seconds: int) -> str:
    """Format duration in seconds into localized human-readable string."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    lang = get_language()

    h_unit = "ч" if lang == "ru" else "h"
    m_unit = "мин" if lang == "ru" else "min"
    s_unit = "сек" if lang == "ru" else "sec"

    parts = []
    if hours > 0:
        parts.append(f"{hours} {h_unit}")
    if minutes > 0:
        parts.append(f"{minutes} {m_unit}")
    if secs > 0 or not parts:
        parts.append(f"{secs} {s_unit}")
    return " ".join(parts)
