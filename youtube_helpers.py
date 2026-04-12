"""
youtube_helpers.py — YouTube channel, video, and transcript utilities for TechTracker MCP.
"""
import re
import logging
import time
from datetime import datetime
from typing import Optional

import feedparser
import requests
from youtube_transcript_api import YouTubeTranscriptApi

from gmail_helpers import get_credential
from database import NewsletterSessionLocal
from models import Email

logger = logging.getLogger("TechTracker.MCP")


def channel_label(url: str) -> str:
    """Extract a readable channel name from a YouTube URL."""
    m = re.search(r"youtube\.com/(?:@|channel/|user/)([^/?&]+)", url)
    return m.group(1) if m else url.split("/")[-1] or url


def get_channel_id(channel_url: str) -> str:
    """Resolve a YouTube channel URL to its UC... channel ID."""
    m = re.search(r"/channel/(UC[\w-]+)", channel_url)
    if m:
        return m.group(1)
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(channel_url, headers=headers, timeout=10)
    html = resp.text
    m = re.search(r'"externalId":"(UC[\w-]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'channelId":"(UC[\w-]+)"', html)
    if m:
        return m.group(1)
    raise ValueError(f"Channel ID not found for: {channel_url}")


def get_latest_video_id(channel_id: str) -> Optional[str]:
    """
    Return the latest non-Shorts video ID for a channel.
    Tries the YouTube Data API first (if api_key is stored), then falls back to RSS.
    """
    api_key = get_credential("youtube", "api_key")
    if api_key:
        try:
            url = (
                f"https://www.googleapis.com/youtube/v3/search"
                f"?key={api_key}&channelId={channel_id}&part=snippet,id"
                f"&order=date&maxResults=5&type=video"
            )
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    vid_id = item.get("id", {}).get("videoId")
                    if vid_id:
                        return vid_id
        except Exception as e:
            logger.warning(f"[YOUTUBE] API search failed: {e}")

    # RSS fallback
    feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
    for entry in feed.entries:
        vid_id = getattr(entry, "yt_videoid", None)
        link   = getattr(entry, "link", "")
        if vid_id and "shorts" not in link.lower():
            return vid_id
    return None


def get_video_title(channel_id: str, video_id: str) -> str:
    """Look up a video title from the channel RSS feed."""
    feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
    return next(
        (e.title for e in feed.entries if getattr(e, "yt_videoid", "") == video_id),
        f"YouTube video {video_id}",
    )


def get_transcript(video_id: str, max_chars: int = 8000) -> str:
    """Fetch and return a timestamped transcript for a YouTube video."""
    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)
    transcript = list(transcript_list)[0]
    data = transcript.fetch()
    lines = [f"{t.start:.0f}s: {t.text}" for t in data]
    return "\n".join(lines)[:max_chars]


def fetch_channel_content(channel_url: str) -> str:
    """
    Full pipeline for one channel: resolve ID → latest video → transcript → store in DB.
    Returns a formatted string with channel name, video title, URL, and transcript.
    """
    t0 = time.time()
    label = channel_label(channel_url)
    logger.info(f"[YOUTUBE] Processing: {label}")

    t_id = time.time()
    channel_id = get_channel_id(channel_url)
    logger.info(f"[YOUTUBE] Resolved channel ID: {channel_id} | {time.time()-t_id:.2f}s")

    t_vid = time.time()
    video_id = get_latest_video_id(channel_id)
    logger.info(f"[YOUTUBE] Latest video ID: {video_id} | {time.time()-t_vid:.2f}s")

    if not video_id:
        return f"{label}: No suitable video found."

    db = NewsletterSessionLocal()
    existing = db.query(Email).filter_by(message_id=f"yt:{video_id}").first()
    if existing:
        db.close()
        logger.info(f"[YOUTUBE] {label}: transcript from DB cache | {time.time()-t0:.2f}s")
        return (
            f"Channel: {label}\nVideo: {existing.subject}\n\n"
            f"{(existing.clean_text or '')[:3000]}"
        )

    t_tr = time.time()
    transcript_text = get_transcript(video_id)
    logger.info(f"[YOUTUBE] Transcript fetched: {len(transcript_text)} chars | {time.time()-t_tr:.2f}s")

    video_url = f"https://www.youtube.com/watch?v={video_id}"
    title     = get_video_title(channel_id, video_id)
    clean     = (
        f"[YouTube Transcript]\nChannel: {label}\n"
        f"Video: {title}\nURL: {video_url}\n\n{transcript_text}"
    )

    db.add(Email(
        message_id=f"yt:{video_id}", subject=title,
        sender=f"YouTube: {label}", received_date=datetime.utcnow(),
        raw_html=None, clean_text=clean, summary=None, processed=True,
    ))
    db.commit()
    db.close()

    logger.info(f"[YOUTUBE] {label}: done | total {time.time()-t0:.2f}s")
    return f"Channel: {label}\nVideo: {title}\nURL: {video_url}\n\n{transcript_text[:4000]}"
