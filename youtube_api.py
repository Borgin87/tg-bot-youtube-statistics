import aiohttp
from urllib.parse import urlparse, parse_qs
from typing import Any, Dict, Optional, Tuple


YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


class YouTubeApiError(Exception):
    pass


def extract_channel_id_from_url(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")

        if len(path_parts) >= 2 and path_parts[0] == "channel":
            channel_id = path_parts[1]
            if channel_id.startswith("UC"):
                return channel_id
    except Exception:
        return None

    return None


def extract_handle_from_url(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
        path = parsed.path.strip("/")

        if path.startswith("@"):
            return path.split("/")[0][1:]
    except Exception:
        return None

    return None


def extract_video_id(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)

        if "youtu.be" in parsed.netloc:
            return parsed.path.strip("/")

        if "youtube.com" in parsed.netloc and parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            return qs.get("v", [None])[0]
    except Exception:
        return None

    return None


async def _fetch_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as response:
            data = await response.json()

            if response.status != 200:
                raise YouTubeApiError(f"HTTP {response.status}: {data}")

            return data


async def resolve_channel_id(api_key: str, user_input: str) -> Tuple[str, Optional[str]]:
    value = user_input.strip()

    if value.startswith("UC"):
        data = await _fetch_json(
            YOUTUBE_CHANNELS_URL,
            {
                "part": "snippet",
                "id": value,
                "key": api_key,
            },
        )

        items = data.get("items", [])
        if not items:
            raise YouTubeApiError("Канал с таким UC не найден.")

        title = items[0].get("snippet", {}).get("title")
        return value, title

    if value.startswith("@"):
        handle = value[1:]

        data = await _fetch_json(
            YOUTUBE_CHANNELS_URL,
            {
                "part": "id,snippet",
                "forHandle": handle,
                "key": api_key,
            },
        )

        items = data.get("items", [])
        if not items:
            raise YouTubeApiError("Канал по handle не найден.")

        channel_id = items[0]["id"]
        title = items[0].get("snippet", {}).get("title")
        return channel_id, title

    if value.startswith("http://") or value.startswith("https://"):
        channel_id = extract_channel_id_from_url(value)
        if channel_id:
            data = await _fetch_json(
                YOUTUBE_CHANNELS_URL,
                {
                    "part": "snippet",
                    "id": channel_id,
                    "key": api_key,
                },
            )

            items = data.get("items", [])
            if not items:
                raise YouTubeApiError("Канал по ссылке не найден.")

            title = items[0].get("snippet", {}).get("title")
            return channel_id, title

        handle = extract_handle_from_url(value)
        if handle:
            data = await _fetch_json(
                YOUTUBE_CHANNELS_URL,
                {
                    "part": "id,snippet",
                    "forHandle": handle,
                    "key": api_key,
                },
            )

            items = data.get("items", [])
            if not items:
                raise YouTubeApiError("Канал по ссылке @handle не найден.")

            channel_id = items[0]["id"]
            title = items[0].get("snippet", {}).get("title")
            return channel_id, title

        video_id = extract_video_id(value)
        if video_id:
            data = await _fetch_json(
                YOUTUBE_VIDEOS_URL,
                {
                    "part": "snippet",
                    "id": video_id,
                    "key": api_key,
                },
            )

            items = data.get("items", [])
            if not items:
                raise YouTubeApiError("Видео по ссылке не найдено.")

            snippet = items[0].get("snippet", {})
            channel_id = snippet.get("channelId")
            title = snippet.get("channelTitle")

            if not channel_id:
                raise YouTubeApiError("Не удалось определить канал по видео.")

            return channel_id, title

        raise YouTubeApiError(
            "Ссылка не распознана. Пришли ссылку вида "
            "https://www.youtube.com/@handle или https://www.youtube.com/channel/UC..."
        )

    data = await _fetch_json(
        YOUTUBE_SEARCH_URL,
        {
            "part": "snippet",
            "type": "channel",
            "q": value,
            "maxResults": 1,
            "key": api_key,
        },
    )

    items = data.get("items", [])
    if not items:
        raise YouTubeApiError("Канал по названию не найден.")

    item = items[0]
    channel_id = item.get("id", {}).get("channelId")
    title = item.get("snippet", {}).get("channelTitle")

    if not channel_id:
        raise YouTubeApiError("Не удалось получить UC канала из поиска.")

    return channel_id, title


async def fetch_channel_stats(api_key: str, channel_id: str) -> dict:
    data = await _fetch_json(
        YOUTUBE_CHANNELS_URL,
        {
            "part": "snippet,statistics",
            "id": channel_id,
            "key": api_key,
        },
    )

    items = data.get("items", [])
    if not items:
        raise YouTubeApiError("Канал не найден.")

    item = items[0]
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})

    return {
        "title": snippet.get("title", "Unknown"),
        "channel_id": channel_id,
        "subscribers": int(stats.get("subscriberCount", 0)),
        "views": int(stats.get("viewCount", 0)),
        "videos": int(stats.get("videoCount", 0)),
        "hidden_subs": bool(stats.get("hiddenSubscriberCount", False)),
    }