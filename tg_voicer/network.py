"""
Network connectivity monitoring and recovery for TG-Voicer.
Provides resilience against internet dropouts, connection resets, and Telegram server disconnects.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Callable, List, Optional, Tuple

from telethon import TelegramClient

from . import ui

logger = logging.getLogger("tg_voicer.network")

# Known reliable endpoints for connectivity checks:
# Cloudflare DNS, Google DNS, Telegram DC2, Telegram DC4
CONNECTIVITY_ENDPOINTS: List[Tuple[str, int]] = [
    ("1.1.1.1", 53),
    ("8.8.8.8", 53),
    ("149.154.167.50", 443),
    ("149.154.175.50", 443),
]


def is_network_error(exc: BaseException) -> bool:
    """
    Check if an exception is caused by network issues (disconnect, DNS failure, timeout, etc.)
    rather than a Telegram protocol or logic error.
    """
    if isinstance(exc, (OSError, ConnectionError, asyncio.TimeoutError)):
        return True

    # Check for Telethon network-related errors
    type_name = type(exc).__name__
    if any(
        kw in type_name
        for kw in ("Network", "Connection", "Timeout", "TimedOut", "Socket")
    ):
        return True

    # Check error message keywords
    msg = str(exc).lower()
    network_keywords = (
        "connection lost",
        "cannot send requests while disconnected",
        "connection reset",
        "network is unreachable",
        "no route to host",
        "nodename nor servname",
        "temporary failure in name resolution",
        "timed out",
        "socket",
        "broken pipe",
        "connection refused",
        "connection aborted",
        "host is down",
    )
    return any(kw in msg for kw in network_keywords)


async def check_internet(
    timeout: float = 3.0,
    endpoints: Optional[List[Tuple[str, int]]] = None,
) -> bool:
    """
    Test internet connectivity by attempting a fast TCP connection to well-known hosts.
    Returns True if at least one host is reachable.
    """
    hosts_to_try = endpoints or CONNECTIVITY_ENDPOINTS

    for host, port in hosts_to_try:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout,
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            continue

    return False


class NetworkManager:
    """
    Monitors internet connectivity and coordinates graceful pauses & reconnections
    across all TG-Voicer workers (realtime listener, backfill scanner, and transcriber).
    """

    def __init__(
        self,
        client: TelegramClient,
        check_interval: float = 5.0,
        probe_timeout: float = 3.0,
        internet_checker: Optional[Callable[[], asyncio.Future[bool]]] = None,
    ):
        self.client = client
        self.check_interval = check_interval
        self.probe_timeout = probe_timeout
        self._internet_checker = internet_checker or (
            lambda: check_internet(timeout=self.probe_timeout)
        )

        self._is_online = True
        self._reconnect_lock = asyncio.Lock()
        self._watchdog_task: Optional[asyncio.Task] = None
        self._stopped = False

    @property
    def is_online(self) -> bool:
        """Current online state flag."""
        return self._is_online

    async def check_connectivity(self) -> bool:
        """Perform an active connectivity test."""
        try:
            res = self._internet_checker()
            if asyncio.iscoroutine(res):
                return await res
            return bool(res)
        except Exception:
            return False

    async def wait_for_connection(self) -> None:
        """
        Suspend operations until internet connectivity is restored and TelegramClient
        is successfully reconnected. Multiple parallel calls are coalesced via a lock.
        """
        if self._stopped:
            return

        async with self._reconnect_lock:
            # If already reconnected while waiting for lock
            if self._is_online and self.client.is_connected():
                return

            # Transition to offline state and notify user
            if self._is_online:
                self._is_online = False
                ui.print_network_offline(int(self.check_interval))
                logger.warning(
                    f"⚠️ Потеряно соединение с интернетом или Telegram. "
                    f"Приостановка операций и ожидание сети (проверка каждые {self.check_interval:.0f}с)..."
                )

            # Polling loop until internet and Telegram are available
            while not self._stopped:
                has_internet = await self.check_connectivity()
                if not has_internet:
                    logger.debug("Internet probe failed. Sleeping...")
                    await asyncio.sleep(self.check_interval)
                    continue

                # Internet is back, now ensure TelegramClient is connected
                logger.debug("Internet is online. Ensuring TelegramClient connection...")
                try:
                    if not self.client.is_connected():
                        await self.client.connect()

                    if self.client.is_connected():
                        self._is_online = True
                        ui.print_network_restored()
                        logger.info(
                            "✅ Соединение с интернетом и Telegram успешно восстановлено! "
                            "Возобновление работы."
                        )
                        return
                except Exception as e:
                    if is_network_error(e):
                        logger.debug(f"Telegram client reconnection failed: {e}")
                    else:
                        logger.warning(f"Unexpected error during client reconnection: {e}")

                await asyncio.sleep(self.check_interval)

    async def watchdog(self) -> None:
        """
        Background supervisor that periodically checks if Telethon disconnected
        unexpectedly and initiates reconnection.
        """
        while not self._stopped:
            try:
                await asyncio.sleep(15.0)
                if self._stopped:
                    break

                if not self.client.is_connected():
                    logger.debug("Watchdog detected disconnected client. Initiating recovery...")
                    await self.wait_for_connection()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Network watchdog check exception: {e}")

    def start_watchdog(self) -> Optional[asyncio.Task]:
        """Start watchdog background task."""
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self.watchdog())
        return self._watchdog_task

    async def stop(self) -> None:
        """Stop network manager and watchdog task."""
        self._stopped = True
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            self._watchdog_task = None
