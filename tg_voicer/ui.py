"""
Terminal UI and rich output formatting for TG-Voicer.
Supports localized strings via tg_voicer.i18n.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .i18n import (
    format_duration,
    get_day_name,
    get_day_names,
    get_language,
    get_month_names,
    t,
)

console = Console(highlight=False)


def format_peer(sender_name: str, chat_title: str) -> str:
    """Format peer string cleanly, avoiding repeating name in direct messages."""
    sender_name = (sender_name or "").strip() or "Unknown"
    chat_title = (chat_title or "").strip()
    if not chat_title or chat_title == sender_name:
        return f"[bold white]{sender_name}[/bold white]"
    peer_in = t("peer_in")
    return f"[bold white]{sender_name}[/bold white] [dim]{peer_in}[/dim] [bold]{chat_title}[/bold]"


def print_banner(
    version: str,
    user_name: str,
    user_handle: str,
    is_premium: bool,
    mode_desc: str,
    db_path: str,
    filter_summaries: Optional[List[str]] = None,
) -> None:
    """Display startup banner with system configuration and user details."""
    body = Text()
    body.append("🎙️  TG-VOICER ", style="bold cyan")
    body.append(f"v{version}\n", style="dim cyan")

    body.append(t("banner_user"), style="dim")
    body.append(f"{user_name} ", style="bold white")
    body.append(f"({user_handle})    ", style="dim")

    body.append(t("banner_premium"), style="dim")
    if is_premium:
        body.append(t("banner_premium_active"), style="bold green")
    else:
        body.append(t("banner_premium_inactive"), style="bold red")

    body.append(t("banner_mode"), style="dim")
    body.append(f"{mode_desc}    ", style="white")

    body.append(t("banner_db"), style="dim")
    body.append(f"{db_path}\n", style="white")

    if filter_summaries:
        body.append(t("banner_filters"), style="dim")
        body.append("; ".join(filter_summaries), style="dim")

    panel = Panel(
        body,
        border_style="blue",
        title=f"[bold blue]{t('banner_title')}[/bold blue]",
        title_align="left",
    )
    console.print(panel)


def print_scan_chat(chat_title: str, chat_type: str, chat_id: int) -> None:
    """Print chat history scan start."""
    now_str = datetime.now().strftime("%H:%M:%S")
    type_badge = t("chat_type_dm") if chat_type == "user" else chat_type
    console.print(
        f"[dim]{now_str}[/dim] [blue]{t('source_backfill')}[/blue] 🔍 [cyan]{t('scan_history')}[/cyan] "
        f"[bold white]{chat_title}[/bold white] [dim]({type_badge} • id {chat_id})[/dim]"
    )


def print_chat_completed(chat_title: str) -> None:
    """Print chat history completion."""
    now_str = datetime.now().strftime("%H:%M:%S")
    console.print(
        f"[dim]{now_str}[/dim] [blue]{t('source_backfill')}[/blue] 🏁 [green]{t('chat_completed')}[/green] "
        f"[bold white]{chat_title}[/bold white]"
    )


def print_all_completed() -> None:
    """Print completion of all dialogs history scan."""
    now_str = datetime.now().strftime("%H:%M:%S")
    console.print(
        f"[dim]{now_str}[/dim] [blue]{t('source_backfill')}[/blue] 🎉 [bold green]{t('all_completed')}[/bold green]"
    )


def print_voice_found(
    source: str,
    media_type: str,
    duration: float,
    sender_name: str,
    chat_title: str,
    msg_id: int,
) -> None:
    """Print that a voice note or video note was detected and is being processed."""
    now_str = datetime.now().strftime("%H:%M:%S")
    src_badge = (
        f"[bold green]{t('source_live')}[/bold green]    "
        if source == "LIVE"
        else f"[blue]{t('source_backfill')}[/blue]"
    )
    icon = "🎤" if media_type == "voice" else "📹"
    media_name = t("media_voice") if media_type == "voice" else t("media_video_note")
    media_style = "bold cyan" if media_type == "voice" else "bold magenta"
    peer = format_peer(sender_name, chat_title)
    unit_s = "s" if get_language() == "en" else "с"

    console.print(
        f"[dim]{now_str}[/dim] {src_badge} [yellow]⏳[/yellow] {icon} [{media_style}]{media_name}[/{media_style}] "
        f"[dim]{duration:.1f}{unit_s}[/dim]  {peer} [dim]#{msg_id}[/dim]"
    )


def print_transcription_result(
    text: Optional[str],
    is_cached: bool = False,
    status: str = "done",
    error: Optional[str] = None,
) -> None:
    """Print the transcription result indented cleanly beneath the message header."""
    if status == "failed" or error:
        err_msg = Text()
        err_msg.append("✗ ", style="bold red")
        fallback_err = "Failed to transcribe" if get_language() == "en" else "Не удалось расшифровать"
        err_msg.append(t("transcription_error", error=error or fallback_err), style="red")
        console.print(Padding(err_msg, (0, 0, 0, 9)))
        console.print()
    elif status == "pending":
        pend_msg = Text()
        pend_msg.append("⏳ ", style="yellow")
        pend_msg.append(t("transcription_pending"), style="dim")
        console.print(Padding(pend_msg, (0, 0, 0, 9)))
        console.print()
    else:
        clean_text = (text or "").strip().replace("\r\n", " ").replace("\n", " ")
        if not clean_text:
            clean_text = t("empty_audio")

        msg_text = Text()
        if is_cached:
            msg_text.append("⚡ ", style="yellow")
            msg_text.append(t("cached_tag"), style="dim")
        else:
            msg_text.append("✓ ", style="bold green")

        msg_text.append(f'"{clean_text}"', style="italic white")
        console.print(Padding(msg_text, (0, 0, 0, 9)))
        console.print()


def format_seconds(seconds: int) -> str:
    """Format seconds into readable duration string."""
    return format_duration(seconds)


def print_flood_wait(seconds: int) -> None:
    """Print readable FloodWait notification with formatted duration and resume time."""
    now = datetime.now()
    resume_time = now + timedelta(seconds=seconds)
    dur_str = format_seconds(seconds)
    res_str = resume_time.strftime("%H:%M:%S")

    console.print(
        f"[dim]{now.strftime('%H:%M:%S')}[/dim] ⏳ [bold yellow]Telegram FloodWait:[/bold yellow] "
        f"[yellow]{t('flood_wait_notice')}[/yellow]\n"
        f"         [dim]{t('flood_wait_pause')}[/dim] [bold white]{dur_str}[/bold white] "
        f"[dim]{t('flood_wait_resume')}[/dim] [bold cyan]{res_str}[/bold cyan]"
    )
    console.print()


def get_heatmap_cell(cnt: int, show_number: bool = False) -> str:
    """Format single cell for heatmap based on message volume."""
    if cnt == 0:
        return "[dim]·[/dim]"
    num = str(cnt) if show_number else "■"
    if cnt <= 2:
        return f"[#2ea043]{num}[/]"
    elif cnt <= 5:
        return f"[#3fb950]{num}[/]"
    elif cnt <= 8:
        return f"[bold #d29922]{num}[/bold #d29922]"
    else:
        return f"[bold #f85149]{num}[/bold #f85149]"


def render_voice_metrics_table(voice_stats: Dict[str, Any]) -> Optional[Table]:
    """Render summary table of voice messaging habits based on recorded dates."""
    total = voice_stats.get("total_with_date", 0)
    if total <= 0:
        return None

    table = Table(
        title=t("metrics_title"),
        border_style="blue",
        header_style="bold cyan",
    )
    table.add_column(t("metric_col"), style="white", width=36)
    table.add_column(t("value_col"), justify="right", style="bold", width=44)

    earliest = voice_stats.get("earliest_date")
    latest = voice_stats.get("latest_date")
    span_days = voice_stats.get("total_span_days", 1)
    active_days = voice_stats.get("active_days_count", 1)
    avg_active = voice_stats.get("avg_per_active_day", 0.0)
    avg_span = voice_stats.get("avg_per_day_span", 0.0)
    peak_date = voice_stats.get("peak_day_date")
    peak_cnt = voice_stats.get("peak_day_count", 0)
    total_dur = voice_stats.get("total_duration_sec", 0.0)
    avg_dur = voice_stats.get("avg_duration_sec", 0.0)
    by_dow = voice_stats.get("by_dow", {})

    full_dow_names = get_day_names(full=True)
    peak_dow = max(range(7), key=lambda x: by_dow.get(x, 0)) if by_dow else 0
    peak_dow_cnt = by_dow.get(peak_dow, 0)

    table.add_row(t("metric_total_with_date"), f"[cyan]{total}[/cyan]")
    if earliest and latest:
        table.add_row(
            t("metric_period"),
            f"{earliest.strftime('%d.%m.%Y')} — {latest.strftime('%d.%m.%Y')} [dim]{t('metric_period_days', days=span_days)}[/dim]",
        )

    act_pct = (active_days / max(1, span_days)) * 100
    table.add_row(
        t("metric_active_days"),
        f"[yellow]{active_days}[/yellow] [dim]{t('metric_active_days_pct', pct=act_pct)}[/dim]",
    )
    table.add_row(
        t("metric_avg_active"),
        f"[bold green]{avg_active:.2f}[/bold green] {t('metric_avg_active_unit')}",
    )
    every_n = t("metric_every_n_days", days=int(1 / avg_span)) if 0 < avg_span < 1 else ""
    table.add_row(
        t("metric_avg_span"),
        f"[green]{avg_span:.3f}[/green] {t('metric_avg_active_unit')}[dim]{every_n}[/dim]",
    )

    recent_30d = voice_stats.get("recent_30d_count", 0)
    avg_30d = voice_stats.get("avg_recent_30d", 0.0)
    if span_days > 30 and recent_30d > 0:
        table.add_row(
            t("metric_recent_30d"),
            f"[cyan]{recent_30d}[/cyan] {t('metric_recent_unit')} [dim]({avg_30d:.2f} {t('metric_avg_active_unit')})[/dim]",
        )

    if peak_date and peak_cnt > 0:
        table.add_row(
            t("metric_peak_day"),
            f"[bold magenta]{peak_cnt}[/bold magenta] {t('metric_recent_unit')} [dim]({peak_date.strftime('%d.%m.%Y')})[/dim]",
        )

    if total_dur > 0:
        dur_mins = int(total_dur // 60)
        dur_secs = int(total_dur % 60)
        dur_fmt = t("metric_total_dur_fmt", mins=dur_mins, secs=dur_secs)
        table.add_row(
            t("metric_avg_dur"),
            f"{avg_dur:.1f} {t('metric_avg_dur_unit')} [dim]{dur_fmt}[/dim]",
        )

    if peak_dow_cnt > 0:
        pct = (peak_dow_cnt / total) * 100
        dow_str = full_dow_names[peak_dow] if peak_dow < len(full_dow_names) else str(peak_dow)
        table.add_row(
            t("metric_peak_dow"),
            f"{dow_str} [dim]({peak_dow_cnt} {t('metric_recent_unit')}, {pct:.0f}%)[/dim]",
        )

    return table


def render_dow_hour_heatmap(voice_stats: Dict[str, Any]) -> Optional[Table]:
    """Render Day of Week x 2-Hour timeslot heatmap."""
    total = voice_stats.get("total_with_date", 0)
    if total <= 0:
        return None

    dow_hour = voice_stats.get("by_dow_hour", {})
    dow_names = get_day_names(full=False)

    table = Table(
        title=t("heatmap_dow_hour_title"),
        border_style="blue",
        header_style="bold cyan",
    )
    table.add_column(t("heatmap_col_day"), style="bold white", width=3)
    for h in range(0, 24, 2):
        table.add_column(f"{h:02d}", justify="center", width=4)
    table.add_column(t("heatmap_col_total"), justify="right", style="bold yellow", width=6)

    for dow in range(7):
        name = dow_names[dow] if dow < len(dow_names) else str(dow)
        row = [name]
        tot = 0
        for h in range(0, 24, 2):
            cnt = dow_hour.get((dow, h), 0) + dow_hour.get((dow, h + 1), 0)
            tot += cnt
            row.append(get_heatmap_cell(cnt, show_number=True))
        row.append(str(tot))
        table.add_row(*row)

    return table


def render_month_year_heatmap(voice_stats: Dict[str, Any]) -> Optional[Table]:
    """Render Month x Year activity table if messages span across months."""
    by_ym = voice_stats.get("by_year_month", {})
    if len(by_ym) <= 1:
        return None

    dates_map = voice_stats.get("by_date", {})
    years = sorted(set(y for y, _ in by_ym.keys()))
    months_short = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]

    table = Table(
        title=t("heatmap_month_year_title"),
        border_style="blue",
        header_style="bold cyan",
        pad_edge=False,
        padding=(0, 0),
    )
    table.add_column(t("heatmap_col_year"), style="bold white")
    for m in months_short:
        table.add_column(f" {m}", justify="center")
    table.add_column(f"  {t('heatmap_col_total')} ", justify="right", style="bold yellow")
    table.add_column(t("heatmap_col_avg_day"), justify="right", style="bold green")

    for y in years:
        row = [f" {y}"]
        tot = 0
        active_days_y = sum(1 for d_date in dates_map if d_date.year == y)
        for m in range(1, 13):
            cnt = by_ym.get((y, m), 0)
            tot += cnt
            row.append(f" {get_heatmap_cell(cnt, show_number=True)}")
        row.append(f"   {tot}")
        avg_y = tot / max(1, active_days_y)
        row.append(f"   {avg_y:.1f}")
        table.add_row(*row)

    return table


def render_calendar_heatmap(
    voice_stats: Dict[str, Any],
    weeks: Optional[int] = None,
    target_year: Optional[int] = None,
) -> Optional[Panel]:
    """Render a GitHub-style weekly calendar heatmap."""
    total = voice_stats.get("total_with_date", 0)
    if total <= 0:
        return None

    day_counts = voice_stats.get("by_date", {})
    earliest = voice_stats.get("earliest_date")
    latest = voice_stats.get("latest_date")
    if not earliest or not latest:
        return None

    month_names = get_month_names()
    dow_labels = get_day_names(full=False)

    # Determine date range
    if target_year is not None:
        start_monday = date(target_year, 1, 1) - timedelta(days=date(target_year, 1, 1).weekday())
        end_sunday = date(target_year, 12, 31) + timedelta(days=(6 - date(target_year, 12, 31).weekday()))
        panel_title = f"[bold cyan]{t('heatmap_cal_title_year', year=target_year)}[/bold cyan]"
    else:
        max_d = latest.date()
        min_d = earliest.date()
        full_span_weeks = (max_d - min_d).days // 7 + 1

        if weeks is not None:
            calc_weeks = max(4, min(52, weeks))
        else:
            term_w = console.width or 80
            calc_weeks = max(12, min(52, (term_w - 12) // 2))
            if full_span_weeks <= 26:
                calc_weeks = max(full_span_weeks, 12)

        end_sunday = max_d + timedelta(days=(6 - max_d.weekday()))
        start_monday = end_sunday - timedelta(weeks=calc_weeks) + timedelta(days=1)
        panel_title = (
            f"[bold cyan]{t('heatmap_cal_title_range', start=start_monday.strftime('%d.%m.%Y'), end=end_sunday.strftime('%d.%m.%Y'))}[/bold cyan]"
        )

    total_weeks = (end_sunday - start_monday).days // 7 + 1

    # Split into blocks if weeks > 28 and terminal width is narrow
    term_w = console.width or 80
    blocks: List[Tuple[int, int, str]] = []
    if total_weeks > 28 and term_w < 115:
        mid = total_weeks // 2
        if target_year is not None:
            blocks = [(0, mid, t("heatmap_half1")), (mid, total_weeks, t("heatmap_half2"))]
        else:
            d_mid1 = start_monday + timedelta(weeks=mid) - timedelta(days=1)
            d_mid2 = start_monday + timedelta(weeks=mid)
            blocks = [
                (0, mid, f"▶ {start_monday.strftime('%d.%m.%Y')} — {d_mid1.strftime('%d.%m.%Y')}"),
                (mid, total_weeks, f"▶ {d_mid2.strftime('%d.%m.%Y')} — {end_sunday.strftime('%d.%m.%Y')}"),
            ]
    else:
        blocks = [(0, total_weeks, "")]

    lines: List[str] = []
    for start_w, end_w, block_title in blocks:
        if block_title:
            lines.append(f"[bold yellow]{block_title}[/bold yellow]")
        block_len = end_w - start_w
        block_dates = [start_monday + timedelta(weeks=w) for w in range(start_w, end_w)]

        # Month header
        m_header = ["     "]
        prev_m = None
        w = 0
        while w < block_len:
            w_d = block_dates[w]
            if w_d.month != prev_m and w <= block_len - 2:
                m_label = month_names.get(w_d.month, "")
                m_header.append(f"{m_label:<4}")
                prev_m = w_d.month
                w += 2
            else:
                m_header.append("  ")
                w += 1
        lines.append("".join(m_header))

        for dow in range(7):
            label = dow_labels[dow] if dow < len(dow_labels) else str(dow)
            row = [f"{label}   "]
            for w in range(start_w, end_w):
                d = start_monday + timedelta(weeks=w, days=dow)
                cnt = day_counts.get(d, 0)
                row.append(f"{get_heatmap_cell(cnt, show_number=False)} ")
            lines.append("".join(row))
        lines.append("")

    lines.append(t("heatmap_legend"))

    panel = Panel(
        Text.from_markup("\n".join(lines)),
        title=panel_title,
        border_style="blue",
    )
    return panel


def print_voice_heatmap(
    voice_stats: Dict[str, Any],
    weeks: Optional[int] = None,
    target_year: Optional[int] = None,
) -> None:
    """Print complete voice activity heatmap dashboards."""
    total = voice_stats.get("total_with_date", 0)
    if total <= 0:
        console.print()
        console.print(f"[dim]{t('heatmap_no_data')}[/dim]")
        console.print()
        return

    m_tbl = render_voice_metrics_table(voice_stats)
    if m_tbl:
        console.print()
        console.print(m_tbl)

    dow_tbl = render_dow_hour_heatmap(voice_stats)
    if dow_tbl:
        console.print()
        console.print(dow_tbl)

    ym_tbl = render_month_year_heatmap(voice_stats)
    if ym_tbl:
        console.print()
        console.print(ym_tbl)

    cal_panel = render_calendar_heatmap(voice_stats, weeks=weeks, target_year=target_year)
    if cal_panel:
        console.print()
        console.print(cal_panel)

    all_years = voice_stats.get("all_years", [])
    if len(all_years) > 1 and target_year is None:
        latest_yr = max(all_years)
        hint = t("heatmap_hint_year", start=min(all_years), end=latest_yr)
        console.print(
            f"[dim]{hint}[/dim]"
            f"[bold cyan]python3 main.py --heatmap-year {latest_yr}[/bold cyan]"
        )
    console.print()


def print_stats_table(
    stats: Dict[str, Any],
    recent: List[Dict[str, Any]],
    voice_stats: Optional[Dict[str, Any]] = None,
    heatmap_year: Optional[int] = None,
    heatmap_weeks: Optional[int] = None,
) -> None:
    """Print formatted statistics using rich tables, including voice recording heatmap."""
    table = Table(
        title=t("stats_title"),
        border_style="blue",
        header_style="bold cyan",
    )
    table.add_column(t("metric_col"), style="white")
    table.add_column(t("value_col"), justify="right", style="bold")

    table.add_row(t("stat_transcribed"), f"[green]{stats.get('transcribed_done', 0)}[/green]")
    table.add_row(t("stat_live"), f"[yellow]{stats.get('live_captured', 0)}[/yellow]")
    table.add_row(t("stat_pending"), str(stats.get("transcribed_pending", 0)))
    table.add_row(t("stat_skipped"), str(stats.get("skipped", 0)))
    failed = stats.get("failed", 0)
    table.add_row(t("stat_failed"), f"[red]{failed}[/red]" if failed > 0 else "0")
    table.add_row(t("stat_chats_total"), str(stats.get("chats_total", 0)))
    table.add_row(t("stat_chats_completed"), str(stats.get("chats_history_completed", 0)))

    console.print()
    console.print(table)

    v_stats = voice_stats if voice_stats is not None else stats.get("voice_date_stats")
    if v_stats and v_stats.get("total_with_date", 0) > 0:
        m_tbl = render_voice_metrics_table(v_stats)
        if m_tbl:
            console.print()
            console.print(m_tbl)

        dow_tbl = render_dow_hour_heatmap(v_stats)
        if dow_tbl:
            console.print()
            console.print(dow_tbl)

        ym_tbl = render_month_year_heatmap(v_stats)
        if ym_tbl:
            console.print()
            console.print(ym_tbl)

        cal_panel = render_calendar_heatmap(v_stats, weeks=heatmap_weeks, target_year=heatmap_year)
        if cal_panel:
            console.print()
            console.print(cal_panel)

        all_years = v_stats.get("all_years", [])
        if len(all_years) > 1 and heatmap_year is None:
            latest_yr = max(all_years)
            hint = t("heatmap_hint_year", start=min(all_years), end=latest_yr)
            console.print(
                f"[dim]{hint}[/dim]"
                f"[bold cyan]python3 main.py --stats --heatmap-year {latest_yr}[/bold cyan]"
            )

    if recent:
        rec_table = Table(
            title=t("recent_title"),
            border_style="dim",
            header_style="bold magenta",
        )
        rec_table.add_column(t("recent_col_num"), justify="right", style="dim", width=3)
        rec_table.add_column(t("recent_col_type"), width=12)
        rec_table.add_column(t("recent_col_peer"), style="bold white", width=24)
        rec_table.add_column(t("recent_col_dur"), justify="right", style="dim", width=6)
        rec_table.add_column(t("recent_col_text"), style="italic")

        unit_s = "s" if get_language() == "en" else "с"
        for i, item in enumerate(recent, 1):
            media_lbl = t("media_voice_short") if item.get("media_type") == "voice" else t("media_video_short")
            media_icon = "🎤" if item.get("media_type") == "voice" else "📹"
            media = f"{media_icon} {media_lbl}"
            live_tag = " [green][LIVE][/green]" if item.get("is_live") else ""
            sender = item.get("sender_name") or "Unknown"
            chat = item.get("chat_title")
            peer = sender
            if chat and chat != sender:
                peer = f"{sender} ({chat})"
            dur = f"{item.get('duration_sec', 0):.0f}{unit_s}"
            text = (item.get("text") or "").strip().replace("\n", " ")
            if len(text) > 90:
                text = text[:87] + "..."
            rec_table.add_row(str(i), media + live_tag, peer, dur, f'"{text}"')

        console.print()
        console.print(rec_table)
    console.print()


def print_network_offline(retry_seconds: int = 5) -> None:
    """Print network outage warning."""
    now_str = datetime.now().strftime("%H:%M:%S")
    console.print(
        f"[dim]{now_str}[/dim] ⚠️  [bold yellow]{t('net_offline_title')}[/bold yellow]\n"
        f"         [yellow]{t('net_offline_desc', sec=retry_seconds)}[/yellow]"
    )
    console.print()


def print_network_restored() -> None:
    """Print network restoration confirmation."""
    now_str = datetime.now().strftime("%H:%M:%S")
    console.print(
        f"[dim]{now_str}[/dim] ✅ [bold green]{t('net_restored_title')}[/bold green]\n"
        f"         [dim]{t('net_restored_desc')}[/dim]"
    )
    console.print()
