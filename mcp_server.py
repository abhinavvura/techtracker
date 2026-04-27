"""
mcp_server.py — TechTracker MCP Server

Only two tools live here — the ones that fetch LIVE external data:
  - fetch_gmail_newsletters  : pulls emails from Gmail API
  - fetch_youtube_content    : pulls transcripts from YouTube

All DB queries / searches stay in gmail_helpers.py and are called
directly from main.py without going through MCP.

Run with: python mcp_server.py
"""
import logging
from dotenv import load_dotenv
from fastmcp import FastMCP

import gmail_helpers as gmail
import youtube_helpers as yt

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────
logger = logging.getLogger("TechTracker.MCP")
logger.setLevel(logging.INFO)
_ch = logging.StreamHandler()
_ch.setFormatter(logging.Formatter("%(asctime)s │ MCP │ %(message)s"))
logger.addHandler(_ch)

mcp = FastMCP("TechTracker MCP 🚀")


# ════════════════════════════════════════════
# GMAIL TOOL  — live external fetch only
# ════════════════════════════════════════════

@mcp.tool
def fetch_gmail_newsletters(newsletter_names: str) -> str:
    """
    Fetches newsletters from the Gmail API and saves new ones to source.db.
    Input: comma-separated newsletter names or sender keywords.
    Optionally append '|date:YYYY-MM-DD' to scope the fetch to a specific day.
    Example: 'tldr,alphasignal|date:2026-04-09'
    Returns: sync summary (how many new emails were saved and from whom).
    """
    try:
        target_date = None
        if "|date:" in newsletter_names:
            newsletter_names, target_date = newsletter_names.split("|date:", 1)
            target_date = target_date.strip()
        return gmail.sync_newsletters(newsletter_names.strip(), target_date=target_date)
    except Exception as e:
        logger.error(f"[GMAIL] fetch_gmail_newsletters error: {e}")
        return f"Error fetching newsletters: {e}"


# ════════════════════════════════════════════
# YOUTUBE TOOL  — live external fetch only
# ════════════════════════════════════════════

@mcp.tool
def fetch_youtube_content(channel_urls: str) -> str:
    """
    Fetches the latest non-Shorts YouTube video transcript from one or more channels
    and stores them in source.db.
    Input: comma-separated YouTube channel URLs.
    Returns: channel name, video title, and transcript text for each channel.
    """
    urls = [u.strip() for u in channel_urls.split(",") if u.strip()]
    if not urls:
        return "No channel URLs provided."
    results = [yt.fetch_channel_content(url) for url in urls]
    return ("\n\n" + "─" * 60 + "\n\n").join(results)


# ════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════
if __name__ == "__main__":
    logger.info("Starting TechTracker MCP Server on http://localhost:8002")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8002)
