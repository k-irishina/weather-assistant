"""Periodic background jobs for polling and pushes"""
import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Awaitable, Callable

log = logging.getLogger(__name__)


def _seconds_until(at_time: time) -> float:
    now = datetime.now(at_time.tzinfo)
    target = now.replace(
        hour=at_time.hour, minute=at_time.minute, second=at_time.second, microsecond=0
    )
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _daily_loop(job: Callable[[], Awaitable[None]], at_time: time, name: str) -> None:
    while True:
        # recomputed each pass rather than incremented by 24h, so a slow job
        # or a DST change can't drift the schedule
        await asyncio.sleep(_seconds_until(at_time))
        try:
            await job()
        except Exception:
            log.exception("Scheduled job %s failed", name)


async def _repeating_loop(
    job: Callable[[], Awaitable[None]], interval_seconds: float, first_seconds: float, name: str
) -> None:
    await asyncio.sleep(first_seconds)
    while True:
        try:
            await job()
        except Exception:
            log.exception("Scheduled job %s failed", name)
        await asyncio.sleep(interval_seconds)


def run_daily(job: Callable[[], Awaitable[None]], at_time: time, name: str) -> asyncio.Task:
    return asyncio.create_task(_daily_loop(job, at_time, name), name=name)


def run_repeating(
    job: Callable[[], Awaitable[None]],
    interval_seconds: float,
    first_seconds: float,
    name: str,
) -> asyncio.Task:
    return asyncio.create_task(
        _repeating_loop(job, interval_seconds, first_seconds, name), name=name
    )
