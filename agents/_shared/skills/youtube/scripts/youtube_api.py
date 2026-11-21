#!/usr/bin/env python3
"""Zero-dependency shared YouTube Data API v3 client library & CLI for Simon Managed Agents."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

DEFAULT_API_BASE = "https://www.googleapis.com/youtube/v3"

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
_ISO_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def extract_video_id(url_or_id: str) -> str:
    """Extract a canonical 11-char YouTube video ID from a URL or raw ID."""
    raw = (url_or_id or "").strip()
    if _VIDEO_ID_RE.match(raw):
        return raw

    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""

    if host in ("youtu.be", "www.youtu.be"):
        seg = path.strip("/").split("/")[0]
        if _VIDEO_ID_RE.match(seg):
            return seg

    if "youtube.com" in host or "youtube-nocookie.com" in host:
        qs = parse_qs(parsed.query)
        if "v" in qs and qs["v"]:
            cand = qs["v"][0].strip()
            if _VIDEO_ID_RE.match(cand):
                return cand
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[0] in ("shorts", "live", "embed", "v"):
            cand = parts[1].strip()
            if _VIDEO_ID_RE.match(cand):
                return cand

    raise ValueError(f"Could not extract a valid 11-character YouTube video ID from: {url_or_id!r}")


def extract_channel_ref(url_or_ref: str) -> Tuple[str, str]:
    """Return ('id', 'UC...') or ('forHandle', '@handle') from a channel URL, ID, or handle."""
    raw = (url_or_ref or "").strip()
    if not raw:
        raise ValueError("Channel reference must be non-empty.")

    if _CHANNEL_ID_RE.match(raw):
        return "id", raw
    if raw.startswith("@") and "/" not in raw:
        return "forHandle", raw

    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https") and "youtube.com" in (parsed.netloc or "").lower():
        parts = [p for p in (parsed.path or "").split("/") if p]
        if parts:
            if parts[0].startswith("@"):
                return "forHandle", parts[0]
            if len(parts) >= 2 and parts[0] == "channel" and _CHANNEL_ID_RE.match(parts[1]):
                return "id", parts[1]
            if len(parts) >= 2 and parts[0] == "user":
                return "forUsername", parts[1]

    # Bare handle without leading '@'
    if re.match(r"^[A-Za-z0-9._-]{3,60}$", raw):
        return "forHandle", f"@{raw}"

    raise ValueError(f"Could not parse YouTube channel ID or @handle from: {url_or_ref!r}")


def parse_iso8601_duration(iso_duration: Optional[str]) -> Optional[int]:
    """Convert YouTube ISO-8601 duration (e.g. 'PT4M12S') to total seconds."""
    if not iso_duration:
        return None
    match = _ISO_DURATION_RE.match(iso_duration.strip())
    if not match:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_video_item(item: Dict[str, Any]) -> Dict[str, Any]:
    vid = str(item.get("id") or "")
    snippet = item.get("snippet") or {}
    details = item.get("contentDetails") or {}
    stats = item.get("statistics") or {}
    duration_iso = details.get("duration")
    return {
        "video_id": vid,
        "url": f"https://www.youtube.com/watch?v={vid}" if vid else None,
        "title": snippet.get("title"),
        "channel_id": snippet.get("channelId"),
        "channel_title": snippet.get("channelTitle"),
        "published_at": snippet.get("publishedAt"),
        "description": snippet.get("description"),
        "tags": list(snippet.get("tags") or []),
        "category_id": snippet.get("categoryId"),
        "live_broadcast_content": snippet.get("liveBroadcastContent"),
        "duration_iso": duration_iso,
        "duration_seconds": parse_iso8601_duration(duration_iso),
        "view_count": _to_int(stats.get("viewCount")),
        "like_count": _to_int(stats.get("likeCount")),
        "comment_count": _to_int(stats.get("commentCount")),
    }


def _normalize_channel_item(item: Dict[str, Any]) -> Dict[str, Any]:
    cid = str(item.get("id") or "")
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    related = (item.get("contentDetails") or {}).get("relatedPlaylists") or {}
    custom_url = snippet.get("customUrl")
    canonical_url = (
        f"https://www.youtube.com/{custom_url}"
        if custom_url and custom_url.startswith("@")
        else (f"https://www.youtube.com/channel/{cid}" if cid else None)
    )
    return {
        "channel_id": cid,
        "url": canonical_url,
        "title": snippet.get("title"),
        "custom_url": custom_url,
        "description": snippet.get("description"),
        "published_at": snippet.get("publishedAt"),
        "country": snippet.get("country"),
        "subscriber_count": _to_int(stats.get("subscriberCount")),
        "hidden_subscriber_count": bool(stats.get("hiddenSubscriberCount", False)),
        "view_count": _to_int(stats.get("viewCount")),
        "video_count": _to_int(stats.get("videoCount")),
        "uploads_playlist_id": related.get("uploads"),
    }


def _default_http_get(
    url: str,
    headers: Dict[str, str],
    timeout: int,
) -> Tuple[int, Dict[str, Any]]:
    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8").strip()
            return resp.status, (json.loads(raw) if raw else {})
    except HTTPError as exc:
        with exc:
            raw = exc.read().decode("utf-8", errors="replace").strip()
            try:
                err_body = json.loads(raw) if raw else {}
            except ValueError:
                err_body = {"error": {"message": raw or str(exc.reason)}}
        return exc.code, err_body
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"YouTubeAPI network error on {url}: {exc}") from None


class YouTubeAPI:
    """Thin YouTube Data API v3 client using X-Goog-Api-Key header auth."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_API_BASE,
        timeout: int = 30,
        request_fn: Callable[[str, Dict[str, str], int], Tuple[int, Dict[str, Any]]] = _default_http_get,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        # In Managed Agent sandboxes, Google's egress proxy swaps the placeholder env var
        # inside X-Goog-Api-Key on the wire (credential: youtube-api-key).
        self.api_key = (api_key if api_key is not None else os.environ.get("YOUTUBE_API_KEY", "")).strip()
        self.timeout = timeout
        self._request_fn = request_fn

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        clean_params = {k: v for k, v in params.items() if v is not None and v != ""}
        url = f"{self.base_url}/{endpoint.lstrip('/')}?{urlencode(clean_params)}"
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-Goog-Api-Key"] = self.api_key
        status, body = self._request_fn(url, headers, self.timeout)
        if status >= 400:
            err = body.get("error") if isinstance(body, dict) else {}
            msg = err.get("message") if isinstance(err, dict) else str(body)
            reasons = [
                e.get("reason")
                for e in (err.get("errors") or [])
                if isinstance(e, dict) and e.get("reason")
            ] if isinstance(err, dict) else []
            reason_suffix = f" ({', '.join(reasons)})" if reasons else ""
            raise RuntimeError(f"YouTubeAPI HTTP {status} on /{endpoint}{reason_suffix}: {msg}")
        return body

    def videos(self, video_ids_or_urls: Iterable[str]) -> List[Dict[str, Any]]:
        """Fetch metadata, ISO duration, and statistics for 1..50 videos (1 quota unit per batch)."""
        ids = [extract_video_id(v) for v in video_ids_or_urls]
        if not ids:
            return []
        results: List[Dict[str, Any]] = []
        for i in range(0, len(ids), 50):
            batch = ids[i : i + 50]
            data = self._get(
                "videos",
                {
                    "part": "snippet,contentDetails,statistics",
                    "id": ",".join(batch),
                    "maxResults": len(batch),
                },
            )
            for item in data.get("items") or []:
                results.append(_normalize_video_item(item))
        return results

    def search(
        self,
        query: str,
        max_results: int = 10,
        order: str = "relevance",
        published_after: Optional[str] = None,
        channel_id: Optional[str] = None,
        video_duration: Optional[str] = None,
        region_code: Optional[str] = None,
        enrich: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search YouTube videos (100 quota units; +1 unit if enrich=True)."""
        limit = max(1, min(int(max_results), 50))
        params: Dict[str, Any] = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": limit,
            "order": order,
            "publishedAfter": published_after,
            "channelId": channel_id,
            "videoDuration": video_duration,
            "regionCode": region_code,
        }
        data = self._get("search", params)
        items = data.get("items") or []
        video_ids: List[str] = []
        rows: List[Dict[str, Any]] = []
        for item in items:
            vid = ((item.get("id") or {}).get("videoId") or "").strip()
            snippet = item.get("snippet") or {}
            if vid:
                video_ids.append(vid)
            rows.append(
                {
                    "video_id": vid,
                    "url": f"https://www.youtube.com/watch?v={vid}" if vid else None,
                    "title": snippet.get("title"),
                    "channel_id": snippet.get("channelId"),
                    "channel_title": snippet.get("channelTitle"),
                    "published_at": snippet.get("publishedAt"),
                    "description": snippet.get("description"),
                    "live_broadcast_content": snippet.get("liveBroadcastContent"),
                }
            )
        if enrich and video_ids:
            enriched_by_id = {v["video_id"]: v for v in self.videos(video_ids)}
            return [enriched_by_id.get(r["video_id"], r) for r in rows]
        return rows

    def channel(self, channel_ref: str) -> Optional[Dict[str, Any]]:
        """Resolve a channel by UC... ID, @handle, or URL (1 quota unit)."""
        param_key, param_val = extract_channel_ref(channel_ref)
        data = self._get(
            "channels",
            {
                "part": "snippet,statistics,contentDetails",
                param_key: param_val,
                "maxResults": 1,
            },
        )
        items = data.get("items") or []
        if not items:
            return None
        return _normalize_channel_item(items[0])

    def channel_videos(
        self,
        channel_ref: str,
        max_results: int = 15,
        enrich: bool = True,
    ) -> Dict[str, Any]:
        """List recent uploads for a channel via uploads playlist (3 quota units total, avoids 100-unit search)."""
        ch = self.channel(channel_ref)
        if not ch:
            return {"channel": None, "videos": []}
        uploads_id = ch.get("uploads_playlist_id")
        if not uploads_id:
            return {"channel": ch, "videos": []}

        limit = max(1, min(int(max_results), 50))
        pl_data = self._get(
            "playlistItems",
            {
                "part": "snippet,contentDetails",
                "playlistId": uploads_id,
                "maxResults": limit,
            },
        )
        video_ids: List[str] = []
        fallback_rows: List[Dict[str, Any]] = []
        for item in pl_data.get("items") or []:
            snippet = item.get("snippet") or {}
            details = item.get("contentDetails") or {}
            vid = (details.get("videoId") or (snippet.get("resourceId") or {}).get("videoId") or "").strip()
            if vid:
                video_ids.append(vid)
            fallback_rows.append(
                {
                    "video_id": vid,
                    "url": f"https://www.youtube.com/watch?v={vid}" if vid else None,
                    "title": snippet.get("title"),
                    "channel_id": snippet.get("channelId"),
                    "channel_title": snippet.get("channelTitle"),
                    "published_at": details.get("videoPublishedAt") or snippet.get("publishedAt"),
                    "description": snippet.get("description"),
                }
            )

        if enrich and video_ids:
            enriched_by_id = {v["video_id"]: v for v in self.videos(video_ids)}
            videos_out = [enriched_by_id.get(r["video_id"], r) for r in fallback_rows]
        else:
            videos_out = fallback_rows

        return {"channel": ch, "videos": videos_out}

    def comments(
        self,
        video_id_or_url: str,
        max_results: int = 50,
        order: str = "relevance",
    ) -> Dict[str, Any]:
        """Fetch up to 50 public top-level comments for a video (1 quota unit)."""
        vid = extract_video_id(video_id_or_url)
        limit = max(1, min(int(max_results), 100))
        try:
            data = self._get(
                "commentThreads",
                {
                    "part": "snippet",
                    "videoId": vid,
                    "maxResults": limit,
                    "order": order,
                    "textFormat": "plainText",
                },
            )
        except RuntimeError as exc:
            if "commentsDisabled" in str(exc):
                return {
                    "video_id": vid,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "comments_disabled": True,
                    "count": 0,
                    "comments": [],
                }
            raise

        comments_out: List[Dict[str, Any]] = []
        for item in data.get("items") or []:
            top = (item.get("snippet") or {}).get("topLevelComment") or {}
            snip = top.get("snippet") or {}
            comments_out.append(
                {
                    "comment_id": top.get("id") or item.get("id"),
                    "author": snip.get("authorDisplayName"),
                    "text": snip.get("textDisplay") or snip.get("textOriginal") or "",
                    "like_count": _to_int(snip.get("likeCount")) or 0,
                    "reply_count": _to_int((item.get("snippet") or {}).get("totalReplyCount")) or 0,
                    "published_at": snip.get("publishedAt"),
                }
            )
        return {
            "video_id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "comments_disabled": False,
            "count": len(comments_out),
            "comments": comments_out,
        }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Simon shared YouTube Data API v3 CLI.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search", help="Search YouTube videos (100 quota units).")
    p_search.add_argument("query")
    p_search.add_argument("--max-results", type=int, default=10)
    p_search.add_argument("--order", default="relevance", choices=["relevance", "date", "viewCount", "rating"])
    p_search.add_argument("--published-after", default=None, help="RFC 3339 timestamp, e.g. 2025-01-01T00:00:00Z")
    p_search.add_argument("--channel-id", default=None)
    p_search.add_argument("--duration", default=None, choices=["any", "short", "medium", "long"])
    p_search.add_argument("--region-code", default=None)
    p_search.add_argument("--enrich", action="store_true", help="Also fetch exact views/likes/duration (+1 unit).")

    p_video = sub.add_parser("video", help="Fetch metadata & stats for 1..50 video URLs or IDs (1 unit).")
    p_video.add_argument("videos", nargs="+")

    p_channel = sub.add_parser("channel", help="Fetch channel profile & stats by @handle, UC ID, or URL (1 unit).")
    p_channel.add_argument("channel_ref")

    p_ch_vids = sub.add_parser(
        "channel-videos",
        help="List recent uploads for a channel with stats (3 units total; avoids search quota).",
    )
    p_ch_vids.add_argument("channel_ref")
    p_ch_vids.add_argument("--max-results", type=int, default=15)
    p_ch_vids.add_argument("--no-enrich", action="store_true", help="Skip videos.list stats enrichment.")

    p_comments = sub.add_parser("comments", help="Fetch up to 50 public top-level comments for a video (1 unit).")
    p_comments.add_argument("video")
    p_comments.add_argument("--max-results", type=int, default=50)
    p_comments.add_argument("--order", default="relevance", choices=["relevance", "time"])

    args = parser.parse_args(argv)
    yt = YouTubeAPI()

    if args.cmd == "search":
        out: Any = yt.search(
            args.query,
            max_results=args.max_results,
            order=args.order,
            published_after=args.published_after,
            channel_id=args.channel_id,
            video_duration=args.duration,
            region_code=args.region_code,
            enrich=args.enrich,
        )
    elif args.cmd == "video":
        out = yt.videos(args.videos)
    elif args.cmd == "channel":
        out = yt.channel(args.channel_ref)
    elif args.cmd == "channel-videos":
        out = yt.channel_videos(
            args.channel_ref,
            max_results=args.max_results,
            enrich=not args.no_enrich,
        )
    else:
        out = yt.comments(
            args.video,
            max_results=args.max_results,
            order=args.order,
        )

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
