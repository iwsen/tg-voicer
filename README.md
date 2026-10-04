# TG Voicer

Automated speech-to-text transcriber for Telegram voice messages (`.ogg` / `.opus`) and video notes (round video messages) powered by native MTProto API and **Telegram Premium**.

Transcription runs directly on Telegram's cloud servers: recognized text attaches natively under the message and synchronizes across all official clients (iOS, Android, macOS, Windows, Web), exactly as if you clicked the **`->A`** button manually. No third-party AI services (Whisper, OpenAI) or API token fees required.

## 📌 Features

- **Real-Time Live Transcription**: Captures incoming voice notes and video messages as they arrive and requests transcription immediately
- **Chat History Backfill**: Scans past dialog history backwards from newest to oldest with SQLite checkpoints and scan cursors
- **Instant Cloud Cache Fetch**: Returns cached text within milliseconds without queue delays if a voice note was already transcribed
- **Smart Skip for Text Captions**: Detects existing transcripts and message captions (`skip_if_already_has_text`) to avoid unnecessary API calls
- **QR Code & Phone Login**: Terminal QR code authentication with auto-opening SVG on macOS, or phone number login with SMS/Telegram verification code
- **Interactive Terminal Dashboard**: Real-time stats, Premium subscription status, progress bars, and live activity feed
- **Analytics & Activity Heatmaps**: GitHub-style calendar heatmap, "weekday × hour" matrix (in local timezone), and "month × year" summary by original message date (`msg_date`)
- **Network Watchdog**: Continuous connectivity monitoring, graceful pause during outages, and automatic Telethon reconnection
- **FloodWait Protection**: Jittered delay intervals (separate for fresh requests vs instant cache) to keep your account safe
- **Background Daemon & Autostart**: Built-in process supervisor (`--daemon`, `--status`, `--logs`, `--stop`, `--restart`) and `./service.sh` manager with macOS LaunchAgent support
- **Granular Filtering**: Exclude chat types (channels, groups, direct messages, bots), blacklists/whitelists for chats and users, and audio duration limits
- **Bilingual Interface (EN / RU)**: Full localization for terminal output, UI banners, and logs

## 📂 Project Structure

```text
.
├── README.md               # Documentation and setup guide
├── config.example.toml     # Configuration template with all parameters
├── config.toml             # Local configuration file (gitignored)
├── requirements.txt        # Python dependencies
├── main.py                 # CLI entry point and argument parser
├── service.sh              # Daemon manager and macOS LaunchAgent script
├── tg_voicer/
│   ├── app.py              # Application lifecycle and authentication (QR / phone)
│   ├── transcriber.py      # MTProto transcription engine and cloud cache
│   ├── realtime.py         # Real-time incoming message event handler
│   ├── backfill.py         # Chat history backfill scanner and rate limiting
│   ├── database.py         # SQLite persistence, message records, and analytics
│   ├── network.py          # Network connectivity watchdog and auto-reconnect
│   ├── daemon.py           # Background daemon supervisor (double-fork) and signals
│   ├── ui.py               # Terminal dashboard, heatmaps, and rich banners
│   ├── filters.py          # Chat type, user, chat, and duration filters
│   ├── config.py           # TOML configuration loader and validation
│   ├── i18n.py             # Localization dictionaries (English / Russian)
│   └── utils.py            # Formatting, logging, and helper routines
└── tests/
    └── test_voicer.py      # Unit and integration test suite
```

## ⚙️ How It Works

- `VoiceTranscriber` sends `messages.transcribeAudio` requests via MTProto, resolves pending states, and retrieves cached cloud transcripts
- `RealtimeListener` captures live incoming voice and video notes via Telethon event handlers, filtering events before transcription
- `BackfillScanner` traverses chat history backwards, maintaining progress cursors in SQLite and applying jittered delays to prevent FloodWait
- `VoicerDatabase` tracks processed message IDs, chat checkpoints, and timestamps in SQLite (`data/voicer.db`)
- `NetworkWatchdog` periodically verifies network availability, pauses background processing during outages, and cleanly reconnects Telethon
- `DaemonManager` handles detached double-fork process execution, PID tracking, and log streaming
- `VoiceStats` and `TerminalHeatmap` aggregate voice messaging habits by original message dates into terminal activity matrices

## 🧮 Configuration

All settings are managed via `config.toml`. Copy `config.example.toml` or let the interactive setup wizard create it on first launch:

| Section | Parameter | Default | Description |
|---|---|---|---|
| `[general]` | `language` | `"en"` | Interface and log language (`"en"` or `"ru"`) |
| `[telegram]` | `api_id` | Required | Telegram API ID from my.telegram.org |
| `[telegram]` | `api_hash` | Required | Telegram API Hash from my.telegram.org |
| `[telegram]` | `session_name` | `"tg_voicer"` | Session file prefix stored in `data/` |
| `[telegram]` | `auth_method` | `"qr"` | Initial authentication method (`"qr"` or `"phone"`) |
| `[telegram]` | `transcribe_voice` | `true` | Transcribe voice audio messages (`.ogg` / `.opus`) |
| `[telegram]` | `transcribe_video_notes` | `true` | Transcribe round video messages |
| `[telegram]` | `transcribe_outgoing` | `false` | Transcribe own sent messages (`false` = incoming only) |
| `[filters]` | `ignore_types` | `[]` | Ignored chat types: `channels`, `groups`, `private`, `bots` |
| `[filters]` | `ignored_chats` | `[]` | Specific chats/channels to ignore (by ID, username, or title) |
| `[filters]` | `ignored_users` | `[]` | Specific users to ignore (by ID, username, or name) |
| `[filters]` | `allowed_chats` | `[]` | Whitelist of chats to process (empty = process all) |
| `[filters]` | `allowed_users` | `[]` | Whitelist of users to process (empty = process all) |
| `[filters]` | `skip_if_already_has_text` | `true` | Skip messages that already have text or caption |
| `[filters]` | `min_duration_seconds` | `0` | Minimum voice duration in seconds (0 = no limit) |
| `[filters]` | `max_duration_seconds` | `0` | Maximum voice duration in seconds (0 = no limit) |
| `[realtime]` | `enabled` | `true` | Listen for new incoming voice notes in real time |
| `[realtime]` | `wait_for_completion` | `true` | Wait if Telegram returns a pending transcription state |
| `[realtime]` | `timeout_seconds` | `30` | Maximum wait timeout for pending requests |
| `[backfill]` | `enabled` | `true` | Enable historical chat history backfill scanner |
| `[backfill]` | `randomize_delay` | `true` | Jitter delays between requests to prevent FloodWait |
| `[backfill]` | `delay_min_seconds` | `3.5` | Minimum delay between fresh transcription requests |
| `[backfill]` | `delay_max_seconds` | `7.0` | Maximum delay between fresh transcription requests |
| `[backfill]` | `cached_delay_min_seconds` | `0.5` | Minimum delay for instant cloud-cached messages |
| `[backfill]` | `cached_delay_max_seconds` | `1.5` | Maximum delay for instant cloud-cached messages |
| `[backfill]` | `max_messages_per_chat` | `0` | Max messages per chat (0 = unlimited history) |
| `[backfill]` | `max_chats` | `0` | Max chats to scan (0 = all available) |
| `[storage]` | `db_path` | `"data/voicer.db"` | Path to SQLite database file |
| `[logging]` | `level` | `"INFO"` | Log level (`"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`) |

## 🛠️ CLI Commands

| Command / Flag | Description |
|---|---|
| `python3 main.py` | Standard run: Real-time listener + background history backfill |
| `python3 main.py --lang ru` | Force interface language to Russian (or `--lang en`) |
| `python3 main.py -d` (`--daemon`) | Launch in background as a detached daemon process |
| `python3 main.py --status` | Check status of running daemon and display statistics |
| `python3 main.py --logs` (`-f`) | View daemon logs (`-f` follows in real time, `-n 100` limits line count) |
| `python3 main.py --stop` | Stop running background daemon process |
| `python3 main.py --restart` | Restart background daemon process |
| `python3 main.py --live-only` | Process incoming messages only (skip history backfill) |
| `python3 main.py --backfill-only` | Process archive history only and exit when complete |
| `python3 main.py --stats` | Display statistics summary, visual heatmaps, and recent transcripts |
| `python3 main.py --heatmap` | Display voice activity heatmap and metrics by recording date |
| `python3 main.py --heatmap-year 2024` | Detailed activity calendar for a specific year (half-year split) |
| `python3 main.py --heatmap-weeks 26` | Activity calendar for the last N weeks |
| `python3 main.py --reset-backfill` | Reset history scan checkpoints to re-scan all chats from start |
| `python3 main.py --dry-run` | Discover messages and evaluate filters without calling Telegram API |
| `python3 main.py --auth-qr` | Authenticate using Telegram QR code (default) |
| `python3 main.py --auth-phone` | Authenticate using phone number and SMS/Telegram code |
| `python3 main.py -v` (`--verbose`) | Enable verbose debug logging (`DEBUG`) |
| `python3 main.py -c /path/config.toml` | Use custom configuration file path |

## ⚙️ Installation

### 1. Clone repository

```bash
git clone https://github.com/iwsen/tg-voicer.git
cd tg-voicer
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Get Telegram API credentials

Go to [my.telegram.org](https://my.telegram.org), log in with your phone number, and open **API development tools**. Create an application and copy your `api_id` and `api_hash`.

### 4. Configure application

Copy the configuration template:

```bash
cp config.example.toml config.toml
```

Or simply run `main.py` without an existing file — the interactive setup wizard will prompt for `api_id` and `api_hash` and save them automatically to `config.toml`.

## ▶️ Usage

```bash
python3 main.py
```

### Authentication:
- QR code login is enabled by default (`auth_method = "qr"`).
- A QR code is rendered directly in the terminal, and on macOS an SVG vector file is generated and opened automatically.
- Open Telegram on your smartphone: **Settings -> Devices -> Link Desktop Device** and scan the code.
- Your session is saved securely in `data/tg_voicer.session`. Subsequent runs authenticate automatically without prompts.

## 📊 Analytics & Heatmap Dashboard

All statistics and visual calendars are calculated using the **original message recording date** (`msg_date`) rather than the processing time:

- Average voice notes per active day and across all-time history
- Weekday × Hour activity heatmap (2-hour slots in your local timezone)
- Month × Year summary matrix
- GitHub-style daily activity calendar with intensity gradations

```bash
# Full statistics and visual dashboards:
python3 main.py --stats

# Voice activity heatmap only:
python3 main.py --heatmap

# Calendar for a specific year:
python3 main.py --heatmap-year 2024
```

## 🚀 Background Daemon & Autostart

A helper script `./service.sh` is provided for daemon control and system autostart:

```bash
./service.sh start       # Start daemon in background
./service.sh status      # Check daemon status and metrics
./service.sh logs        # Follow logs in real time (tail -f)
./service.sh stop        # Stop daemon
./service.sh restart     # Restart daemon

# Setup macOS autostart on login (LaunchAgent):
./service.sh install-macos
./service.sh uninstall-macos
```

## 💻 Requirements

- Python `3.10+` (Python `3.11+` recommended)
- Telegram account with an active **Telegram Premium** subscription
- Telegram `api_id` and `api_hash` from [my.telegram.org](https://my.telegram.org)

## 🔒 Security & Privacy

- **100% Local Processing**: Session files (`data/*.session`), database (`data/voicer.db`), and `config.toml` remain solely on your machine and are excluded via `.gitignore`.
- **No Third-Party AI Services**: Audio is never transmitted to OpenAI, Whisper, or external servers. All recognition runs through Telegram's official servers under your Premium subscription.
- **FloodWait Protection**: Polite jittered delays keep your account safe from temporary rate limits.

## 🧪 Testing

```bash
python3 -m unittest discover -s tests
```
