import aiohttp
from typing import Any, Dict, List, Optional

YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/channels"


class YouTubeApiError(Exception):
    pass


async def fetch_channel_stats(api_key: str, channel_id: str) -> Dict[str, Any]:
    """
    Возвращает статистику канала по channel_id (UC...).
    """
    params = {
        "part": "snippet,statistics",
        "id": channel_id,
        "key": api_key,
    }

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(YOUTUBE_API_URL, params=params) as resp:
            data = await resp.json()

            if resp.status != 200:
                raise YouTubeApiError(f"HTTP {resp.status}: {data}")

            items = data.get("items", [])
            if not items:
                raise YouTubeApiError("Channel not found or no access.")

            ch = items[0]
            snippet = ch.get("snippet", {})
            stats = ch.get("statistics", {})

            return {
                "title": snippet.get("title", "Unknown"),
                "channel_id": channel_id,
                "subscribers": int(stats.get("subscriberCount", 0)),
                "views": int(stats.get("viewCount", 0)),
                "videos": int(stats.get("videoCount", 0)),
                "hidden_subs": bool(stats.get("hiddenSubscriberCount", False)),
            }