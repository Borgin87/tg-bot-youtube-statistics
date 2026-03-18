import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db import get_all_channel_keys, save_snapshot
from youtube_api import fetch_channel_stats, YouTubeApiError


async def collect_snapshots_once() -> None:
    """
    Один проход сбора снапшотов по всем каналам из БД.
    """
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        logging.warning("YOUTUBE_API_KEY not found, snapshots collection skipped.")
        return

    channels = await get_all_channel_keys()
    if not channels:
        logging.info("No channels in DB. Snapshot collection skipped.")
        return

    logging.info("Snapshot collection started. Channels: %s", len(channels))

    success_count = 0
    error_count = 0

    for channel_id in channels:
        try:
            stats = await fetch_channel_stats(api_key, channel_id)
            await save_snapshot(
                channel_key=channel_id,
                subscribers=stats["subscribers"],
                views=stats["views"],
                videos=stats["videos"],
            )
            success_count += 1
        except YouTubeApiError as e:
            error_count += 1
            logging.warning("YouTube API error for %s: %s", channel_id, e)
        except Exception as e:
            error_count += 1
            logging.exception("Unexpected error while collecting snapshot for %s: %s", channel_id, e)

    logging.info(
        "Snapshot collection finished. Success: %s, Errors: %s",
        success_count,
        error_count,
    )


def build_scheduler() -> AsyncIOScheduler:
    """
    Создаёт и настраивает планировщик.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(
        collect_snapshots_once,
        trigger="interval",
        hours=6,                 # каждые 6 часов
        id="snapshot_collector",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    return scheduler