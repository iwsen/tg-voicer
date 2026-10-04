"""
Daemon process management for TG-Voicer.
Provides background execution, status checking, graceful stop/restart, and log viewing.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from rich.panel import Panel
from rich.text import Text

from .config import AppConfig
from .database import Database
from .i18n import t
from .ui import console, print_stats_table

DEFAULT_PID_FILE = Path("data/tg_voicer.pid")
DEFAULT_LOG_FILE = Path("data/voicer.log")


def is_pid_running(pid: int) -> bool:
    """Check if process with given PID is currently active."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_pid(pid_file: Path = DEFAULT_PID_FILE) -> Optional[int]:
    """Read PID integer from PID file."""
    if not pid_file.exists():
        return None
    try:
        content = pid_file.read_text(encoding="utf-8").strip()
        if content.isdigit():
            return int(content)
    except Exception:
        pass
    return None


def write_pid(pid: int, pid_file: Path = DEFAULT_PID_FILE) -> None:
    """Write PID to file."""
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(pid), encoding="utf-8")


def remove_pid(pid_file: Path = DEFAULT_PID_FILE) -> None:
    """Safely remove PID file."""
    try:
        if pid_file.exists():
            pid_file.unlink()
    except Exception:
        pass


def get_daemon_status(pid_file: Path = DEFAULT_PID_FILE) -> Tuple[bool, Optional[int]]:
    """
    Check if daemon is currently running.
    Cleans up stale PID file if the process is no longer active.
    """
    pid = read_pid(pid_file)
    if pid is None:
        return False, None

    if is_pid_running(pid):
        return True, pid

    # Stale PID file left after abrupt reboot or kill
    remove_pid(pid_file)
    return False, None


def start_daemon(
    config_path: str = "config.toml",
    extra_args: Optional[List[str]] = None,
    pid_file: Path = DEFAULT_PID_FILE,
    log_file: Optional[Path] = None,
    language: Optional[str] = None,
) -> bool:
    """Start tg-voicer in background as a detached daemon process."""
    from .i18n import set_language
    config_p = Path(config_path)
    cfg = AppConfig.load(config_p) if config_p.exists() else AppConfig()
    if language:
        cfg.language = language
        set_language(language)

    is_running, existing_pid = get_daemon_status(pid_file)
    if is_running:
        console.print(
            f"[bold yellow]{t('daemon_already_running', pid=existing_pid)}[/bold yellow]\n"
            f"[dim]{t('daemon_status_hint')}[/dim]\n"
            f"[dim]{t('daemon_logs_hint')}[/dim]\n"
            f"[dim]{t('daemon_stop_hint')}[/dim]\n"
            f"[dim]{t('daemon_restart_hint')}[/dim]"
        )
        return False

    # Verify session exists before detaching to avoid silent prompt hanging
    session_name = cfg.telegram.session_name or "tg_voicer"
    session_file = Path("data") / f"{session_name}.session"
    if not session_file.exists() or session_file.stat().st_size == 0:
        console.print(f"[bold red]{t('daemon_no_session_title')}[/bold red]")
        console.print(t("daemon_no_session_desc"))
        return False

    target_log = log_file or Path(cfg.logging.log_file_path or DEFAULT_LOG_FILE)
    target_log.parent.mkdir(parents=True, exist_ok=True)

    script_path = Path(sys.argv[0]).resolve()
    cmd = [
        sys.executable,
        str(script_path),
        "--daemon-worker",
        "-c",
        config_path,
    ]
    if extra_args:
        cmd.extend(extra_args)

    with open(target_log, "a", encoding="utf-8") as log_out:
        log_out.write(
            f"\n\n--- TG-VOICER DAEMON STARTED: {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n"
        )
        log_out.flush()
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=log_out,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # Complete process detachment on POSIX / Mac
            close_fds=True,
        )

    write_pid(proc.pid, pid_file)

    # Short sanity delay to ensure it didn't immediately crash
    time.sleep(1.5)

    if not is_pid_running(proc.pid):
        remove_pid(pid_file)
        console.print(f"[bold red]{t('daemon_start_failed')}[/bold red]")
        console.print(f"[dim]{t('daemon_check_logs')}[/dim] {target_log.absolute()}\n")
        _print_recent_log_lines(target_log, 15)
        return False

    panel_text = Text()
    panel_text.append(t("daemon_started_header"), style="bold green")
    panel_text.append(t("daemon_pid"), style="dim")
    panel_text.append(f"{proc.pid}\n", style="bold white")
    panel_text.append(t("daemon_log"), style="dim")
    panel_text.append(f"{target_log}\n\n", style="bold white")
    panel_text.append(t("daemon_ctrl_header"), style="bold cyan")
    panel_text.append("  python3 main.py --status    ", style="bold white")
    panel_text.append(t("daemon_ctrl_status"), style="dim")
    panel_text.append("  python3 main.py --logs -f   ", style="bold white")
    panel_text.append(t("daemon_ctrl_logs"), style="dim")
    panel_text.append("  python3 main.py --stop      ", style="bold white")
    panel_text.append(t("daemon_ctrl_stop"), style="dim")
    panel_text.append("  python3 main.py --restart   ", style="bold white")
    panel_text.append(t("daemon_ctrl_restart"), style="dim")

    console.print(
        Panel(
            panel_text,
            border_style="green",
            title=f"[bold green]{t('daemon_panel_title')}[/bold green]",
            title_align="left",
        )
    )
    return True


def stop_daemon(
    pid_file: Path = DEFAULT_PID_FILE,
    timeout: float = 12.0,
    config_path: str = "config.toml",
    language: Optional[str] = None,
) -> bool:
    """Gracefully terminate running daemon process."""
    from .i18n import set_language
    config_p = Path(config_path)
    if config_p.exists():
        AppConfig.load(config_p)
    if language:
        set_language(language)

    is_running, pid = get_daemon_status(pid_file)
    if not is_running or pid is None:
        console.print(f"[dim]{t('daemon_not_running')}[/dim]")
        remove_pid(pid_file)
        return True

    console.print(f"[dim]{t('daemon_stopping', pid=pid)}[/dim]")
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        console.print(f"[red]{t('daemon_signal_failed', pid=pid, error=e)}[/red]")
        remove_pid(pid_file)
        return False

    start_wait = time.time()
    while time.time() - start_wait < timeout:
        if not is_pid_running(pid):
            remove_pid(pid_file)
            console.print(f"[bold green]{t('daemon_stopped_ok', pid=pid)}[/bold green]")
            return True
        time.sleep(0.5)

    # Force kill if graceful termination timed out
    console.print(f"[yellow]{t('daemon_force_kill')}[/yellow]")
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass

    remove_pid(pid_file)
    console.print(f"[bold green]{t('daemon_force_stopped', pid=pid)}[/bold green]")
    return True


def restart_daemon(
    config_path: str = "config.toml",
    extra_args: Optional[List[str]] = None,
    pid_file: Path = DEFAULT_PID_FILE,
    log_file: Optional[Path] = None,
    language: Optional[str] = None,
) -> bool:
    """Restart background daemon."""
    stop_daemon(pid_file=pid_file, config_path=config_path, language=language)
    time.sleep(1.0)
    return start_daemon(
        config_path=config_path,
        extra_args=extra_args,
        pid_file=pid_file,
        log_file=log_file,
        language=language,
    )


def status_daemon(
    config_path: str = "config.toml",
    pid_file: Path = DEFAULT_PID_FILE,
    language: Optional[str] = None,
) -> None:
    """Display daemon runtime status and database transcription metrics."""
    from .i18n import set_language
    is_running, pid = get_daemon_status(pid_file)

    config_p = Path(config_path)
    cfg = AppConfig.load(config_p) if config_p.exists() else AppConfig()
    if language:
        cfg.language = language
        set_language(language)

    log_path = Path(cfg.logging.log_file_path or DEFAULT_LOG_FILE)

    body = Text()
    body.append(t("daemon_status_header"), style="bold cyan")
    body.append(t("daemon_status_label"), style="dim")
    if is_running and pid:
        body.append(t("daemon_status_active"), style="bold green")
        body.append(t("daemon_status_pid_label"), style="dim")
        body.append(f"{pid}\n", style="bold white")
    else:
        body.append(t("daemon_status_inactive"), style="bold yellow")
        body.append(t("daemon_status_start_hint"), style="dim")

    body.append(t("daemon_status_cfg_label"), style="dim")
    body.append(f"{config_path}\n", style="white")
    body.append(t("daemon_status_log_label"), style="dim")
    body.append(f"{log_path}\n", style="white")
    body.append(t("daemon_status_db_label"), style="dim")
    body.append(f"{cfg.storage.db_path}\n", style="white")

    panel = Panel(
        body,
        border_style="green" if is_running else "blue",
        title=f"[bold blue]{t('daemon_status_panel_title')}[/bold blue]",
        title_align="left",
    )
    console.print(panel)

    # Show database stats table
    db_file = Path(cfg.storage.db_path)
    if db_file.exists():
        try:
            db = Database(db_file)
            stats = db.get_stats()
            recent = db.get_recent_transcriptions(limit=5)
            print_stats_table(stats, recent)
            db.close()
        except Exception as e:
            console.print(f"[dim]{t('daemon_db_stats_failed', error=e)}[/dim]")


def view_logs(
    log_file: Optional[Path] = None,
    lines: int = 50,
    follow: bool = False,
    config_path: str = "config.toml",
    language: Optional[str] = None,
) -> None:
    """View daemon logs in terminal or stream live with follow mode."""
    from .i18n import set_language
    target_log = log_file
    if target_log is None:
        config_p = Path(config_path)
        cfg = AppConfig.load(config_p) if config_p.exists() else AppConfig()
        if language:
            set_language(language)
        target_log = Path(cfg.logging.log_file_path or DEFAULT_LOG_FILE)

    if not target_log.exists():
        console.print(f"[yellow]{t('daemon_log_not_found', path=target_log)}[/yellow]")
        return

    if follow:
        console.print(f"[dim]{t('daemon_logs_stream', path=target_log)}[/dim]")
        try:
            subprocess.run(["tail", "-f", str(target_log)])
        except KeyboardInterrupt:
            console.print(f"\n[dim]{t('daemon_logs_exit')}[/dim]")
    else:
        _print_recent_log_lines(target_log, lines)


def _print_recent_log_lines(log_file: Path, lines: int) -> None:
    """Print the last N lines of a log file."""
    try:
        res = subprocess.run(
            ["tail", f"-n{lines}", str(log_file)],
            capture_output=True,
            text=True,
            check=True,
        )
        console.print(res.stdout)
    except Exception:
        # Fallback in pure Python
        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
                for line in all_lines[-lines:]:
                    sys.stdout.write(line)
        except Exception as e:
            console.print(f"[red]{t('daemon_logs_read_failed', error=e)}[/red]")
