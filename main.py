"""
TechTracker — main.py
Sections:
  A. Imports & Logging
  B. App setup & config
  C. Content helpers
  D. Agent callback handler (structured logs)
  E. LangChain Tools  (backed by MCP server via fastmcp.Client)
  F. Agents (Updates + Chat with memory)
  G. Routes
"""
# ════════════════════════════════════════════
# A. IMPORTS & LOGGING
# ════════════════════════════════════════════
import os
import re
import time
import asyncio
import json as json_module
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastmcp import Client as MCPClient

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import google.generativeai as genai
import logging

from sqlalchemy import func as sql_func
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tools import tool
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_classic.agents import AgentExecutor, create_react_agent

# Optional Tavily (graceful degradation if key missing)
try:
    from tavily import TavilyClient
    _TAVILY_AVAILABLE = True
except ImportError:
    _TAVILY_AVAILABLE = False

# WebBaseLoader for URL context extraction
try:
    from langchain_community.document_loaders import WebBaseLoader
    _WEBLOADER_AVAILABLE = True
except ImportError:
    _WEBLOADER_AVAILABLE = False

# Local modules
from database import (
    SourceSessionLocal, ChatSessionLocal, DailySessionLocal, UserDataSessionLocal,
    source_engine, chat_engine, daily_engine, user_data_engine
)
from models import Newsletter, YouTubeTranscript, ChatMessage, DailyUpdate, ConnectorCredential, LinkedInPost, Base
from lnkdn import fetch_posts as fetch_linkedin_posts

# ── Logging setup ────────────────────────────────────────────────
_log_fmt = "%(asctime)s │ %(levelname)-5s │ %(message)s"
logger = logging.getLogger("TechTracker")
logger.setLevel(logging.INFO)
logger.propagate = False

_fh = logging.FileHandler("techtracker.log", encoding="utf-8")
_fh.setFormatter(logging.Formatter(_log_fmt))
logger.addHandler(_fh)

_ch = logging.StreamHandler()
_ch.setFormatter(logging.Formatter(_log_fmt))
logger.addHandler(_ch)

logger.info("━" * 60)
logger.info("  TechTracker backend started")
logger.info("━" * 60)


# ════════════════════════════════════════════
# B. APP SETUP & CONFIG
# ════════════════════════════════════════════
load_dotenv()

Base.metadata.create_all(bind=source_engine)
Base.metadata.create_all(bind=chat_engine)
Base.metadata.create_all(bind=daily_engine)
Base.metadata.create_all(bind=user_data_engine)
logger.info("[STARTUP] All DB tables verified / created.")
logger.info("[STARTUP] Databases: data/source.db | data/chat_history.db | data/daily_updates.db | data/user_data.db")

# ── Token & Cost Tracking ──────────────────────────────────────────
# Approx prices for Gemini 1.5 Flash
INPUT_COST_PER_1K = 0.000075 
OUTPUT_COST_PER_1K = 0.00030

# In-memory session tracking for tokens/cost
session_stats = defaultdict(lambda: {"in_tokens": 0, "out_tokens": 0, "cost": 0.0})

def log_tokens(req_id: str, in_t: int, out_t: int):
    cost = (in_t / 1000 * INPUT_COST_PER_1K) + (out_t / 1000 * OUTPUT_COST_PER_1K)
    session_stats[req_id]["in_tokens"] += in_t
    session_stats[req_id]["out_tokens"] += out_t
    session_stats[req_id]["cost"] += cost
    logger.info(f"  [LLM-METRICS]  Input Tokens: {in_t:<6} | Output Tokens: {out_t:<6} | Call Cost: ${cost:.6f}")

app = FastAPI(title="TechTracker – AI Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gemini setup
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    llm          = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GEMINI_API_KEY, temperature=0)
    direct_model = genai.GenerativeModel("gemini-2.5-flash")
    logger.info("[STARTUP] ✓ Gemini LLM configured (gemini-2.5-flash)")
else:
    logger.error("[STARTUP] ✗ GEMINI_API_KEY not found in .env")

# Tavily setup
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
_tavily_client = None
if TAVILY_API_KEY and _TAVILY_AVAILABLE:
    _tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
    logger.info("[STARTUP] ✓ Tavily search enabled")
else:
    logger.info("[STARTUP] ⚠ Tavily disabled (add TAVILY_API_KEY to .env to enable)")

# ── MCP Server config ─────────────────────────────────────────────
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8002/mcp")
logger.info(f"[STARTUP] MCP server URL: {MCP_SERVER_URL}")


def _call_mcp_tool(tool_name: str, arguments: dict) -> str:
    """Synchronous wrapper that calls a tool on the MCP server.
    Always runs in a dedicated thread with its own event loop to avoid
    conflicts with FastAPI's AnyIO event loop."""
    import concurrent.futures

    async def _run():
        async with MCPClient(MCP_SERVER_URL) as client:
            result = await client.call_tool(name=tool_name, arguments=arguments)
            if isinstance(result, list):
                return "\n".join(
                    getattr(block, "text", str(block)) for block in result
                )
            return str(result)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _run())
            return future.result(timeout=60)
    except Exception as e:
        logger.error(f"[MCP] Tool '{tool_name}' failed: {e}")
        return f"MCP tool error ({tool_name}): {e}"


# In-memory chat session store  {session_id: [(user_msg, ai_msg), ...]}
chat_sessions: dict = defaultdict(list)
MAX_HISTORY_TURNS = 8   # keep last 8 turns per session


# ════════════════════════════════════════════
# C. CONTENT HELPERS
# ════════════════════════════════════════════
def extract_urls_from_text(text: str) -> list:
    raw = re.findall(r"https?://[^\s\]\[\)\(,;<>]+", text or "")
    seen, result = set(), []
    for u in raw:
        u = u.rstrip(".,;:)'\"")
        if u not in seen:
            seen.add(u)
            result.append(u)
        if len(result) >= 5:
            break
    return result


def fetch_url_content_helper(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TechTracker/1.0)"}
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return f"HTTP {resp.status_code}"
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = re.sub(r"\n\s*\n", "\n\n", soup.get_text(separator="\n")).strip()
        return text[:3000]
    except Exception as e:
        return f"Error: {e}"


def query_emails_for_nl(db_session, nl_list: list, extra_filter=None, limit_each: int = 5) -> list:
    """Query newsletters matching any newsletter name, with optional extra SQL filter."""
    all_emails, seen_ids = [], set()
    for nl in nl_list:
        q = db_session.query(Newsletter).filter(
            Newsletter.sender.ilike(f"%{nl}%") | Newsletter.subject.ilike(f"%{nl}%")
        )
        if extra_filter is not None:
            q = q.filter(extra_filter)
        for e in q.order_by(Newsletter.received_date.desc()).limit(limit_each).all():
            if e.message_id not in seen_ids:
                all_emails.append(e)
                seen_ids.add(e.message_id)
    return all_emails


def extract_headlines(content: str, newsletters: str, req_id: str = "global") -> list:
    """Call Gemini to parse newsletter content into structured headlines list."""
    if not GEMINI_API_KEY or not content.strip():
        return []
    prompt = (
        "You are TechTracker AI. Extract EVERY individual distinct news item from the tech newsletter content below.\n\n"
        "Do NOT skip any news. Even if there are 20+ items, extract them all.\n"
        "For each item provide:\n"
        '- "title": A punchy headline under 12 words.\n'
        '- "description": 2-3 sentences — what it is, why it matters, key detail.\n'
        f'- "source": The name of the newsletter or YouTube channel it came from (pick closest from: {newsletters}).\n'
        '  For YouTube content, use "YouTube: [ChannelName]" as the source.\n\n'
        "Return ONLY a raw JSON array. No markdown fences, no extra text:\n"
        '[{"title":"...","description":"...","source":"..."},...]\n\n'
        "Rules:\n"
        "- Extract EVERY news item - DO NOT AGGREGATE OR SKIP.\n"
        "- Do NOT merge items — each story = one bullet\n"
        "- Skip ads, unsubscribe text, job listings, sponsorships, disclaimers\n"
                "- Only real tech / AI / startup / product / research news\n"
        "- For AlphaSignal: extract ALL individual model releases, papers, tool launches separately\n"
        "- For YouTube transcripts: extract the key insights, arguments, and announcements discussed\n\n"
        f"Content:\n{content[:100000]}"
    )
    req_id = datetime.utcnow().strftime("%H%M%S") # Temp ID for tracking if not passed
    try:
        response = direct_model.generate_content(prompt)
        
        # Log tokens for direct genai call
        try:
            usage = response.usage_metadata
            in_t  = getattr(usage, "prompt_token_count", 0) or getattr(usage, "input_token_count", 0) or 0
            out_t = getattr(usage, "candidates_token_count", 0) or getattr(usage, "output_token_count", 0) or 0
            if in_t or out_t:
                log_tokens(req_id, in_t, out_t)
        except Exception:
            pass


        text = re.sub(r"^```(?:json)?\s*\n?", "", response.text.strip())
        text = re.sub(r"\n?```\s*$", "", text).strip()
        parsed = json_module.loads(text)
        return parsed if isinstance(parsed, list) else []
    except Exception as e:
        logger.error(f"[extract_headlines] parse error: {e}")
        return []


def summarize_text(text: str) -> str:
    if not GEMINI_API_KEY or not text:
        return "Summary not available"
    prompt = (
        "Summarize this technology newsletter in clean, structured markdown.\n"
        "## 📰 Newsletter Summary\n\n### 🔑 Key Highlights\n"
        "- **[Topic]**: Brief crisp description\n\n"
        "### 🛠️ Tools & Technologies\n- **Tool**: What it does\n\n"
        "### 💡 Key Takeaway\n> One bottom-line insight\n\n"
        f"{text[:8000]}"
    )
    try:
        return direct_model.generate_content(prompt).text
    except Exception as e:
        logger.error(f"[summarize_text] error: {e}")
        return "Error generating summary."


def format_chat_history(session_id: str) -> str:
    """Format previous turns as context for the agent."""
    turns = chat_sessions.get(session_id, [])
    if not turns:
        return ""
    lines = ["=== Previous conversation ==="]
    for user_msg, ai_msg in turns[-MAX_HISTORY_TURNS:]:
        lines.append(f"User: {user_msg}")
        lines.append(f"Assistant: {ai_msg[:500]}...")  # truncate long answers
    lines.append("=== End of history ===\n")
    return "\n".join(lines)


def save_to_history(session_id: str, user_msg: str, ai_msg: str):
    """Append a turn to the in-memory session store."""
    chat_sessions[session_id].append((user_msg, ai_msg))
    # Keep only last MAX_HISTORY_TURNS
    chat_sessions[session_id] = chat_sessions[session_id][-MAX_HISTORY_TURNS:]


# ════════════════════════════════════════════
# E. AGENT CALLBACK HANDLER  (structured logs)
# ════════════════════════════════════════════
class TechTrackerCallbackHandler(BaseCallbackHandler):
    """
    Prints a clean, structured log for every agent step.
    Format:
        [AGENT]  ┌ Thought: ...
        [AGENT]  └ → Tool: 'name' | Input: '...'
        [TOOL ►] name | started
        [TOOL ◄] name | ✓ ok  3 results | 0.12s
        [LLM  ►] prompt 2400 chars
        [LLM  ◄] done | 1.8s
    """

    def __init__(self, request_id: str = ""):
        self._tool_times: dict = {}
        self._llm_start: float = 0.0
        self._step = 0
        self._rid = f"[{request_id}] " if request_id else ""

    def on_agent_action(self, action, **kwargs):
        self._step += 1
        thought = action.log.split("Action:")[0].replace("Thought:", "").strip()
        if thought:
            logger.info(f"{self._rid}[AGENT]  ┌ Step {self._step} Thought: {thought[:150]}")
        logger.info(f"{self._rid}[AGENT]  └ → Tool: '{action.tool}' | Input: '{str(action.tool_input)[:100]}'")

    def on_tool_start(self, serialized, input_str: str, **kwargs):
        name = serialized.get("name", "unknown")
        self._tool_times[name] = time.time()
        logger.info(f"{self._rid}[TOOL ►] {name} | started")

    def on_tool_end(self, output: str, **kwargs):
        name, elapsed = "unknown", 0.0
        if self._tool_times:
            name = list(self._tool_times.keys())[-1]
            elapsed = time.time() - self._tool_times.pop(name, time.time())
        
        o_str = str(output)
        no_result = any(kw in o_str for kw in ["No relevant", "No newsletters", "not found", "0 results"])
        count = len(o_str)
        est = count // 4
        # icon = "✗ empty" if no_result else f"✓ ok | {count} chars (~{est} tokens)"
        status = "EMPTY" if no_result else "SUCCESS"
        logger.info(f"{self._rid}[TOOL-DONE] Tool: {name:<12} | Status: {status:<7} | Data: {count:<6} chars | {elapsed:.2f}s")

    def on_tool_error(self, error, **kwargs):
        logger.error(f"{self._rid}[TOOL ✗] ERROR: {str(error)[:150]}")

    def on_llm_start(self, serialized, prompts, **kwargs):
        self._llm_start = time.time()
        total_chars = sum(len(p) for p in prompts)
        logger.info(f"{self._rid}[LLM  ►] Gemini call | prompt {total_chars} chars")

    def on_llm_end(self, response, **kwargs):
        elapsed = time.time() - self._llm_start if self._llm_start else 0.0
        self._llm_start = 0.0
        in_t, out_t = 0, 0
        try:
            if response.generations:
                gen = response.generations[0][0]

                # Modern langchain-google-genai: usage_metadata on the message
                if hasattr(gen, "message") and hasattr(gen.message, "usage_metadata"):
                    um = gen.message.usage_metadata or {}
                    in_t  = um.get("input_tokens") or um.get("prompt_tokens") or 0
                    out_t = um.get("output_tokens") or um.get("completion_tokens") or 0

                # Fallback: generation_info dict
                if in_t == 0 and hasattr(gen, "generation_info") and gen.generation_info:
                    um = gen.generation_info.get("usage_metadata", {})
                    in_t  = um.get("prompt_token_count") or um.get("input_token_count") or 0
                    out_t = um.get("candidates_token_count") or um.get("output_token_count") or 0

            # Fallback: top-level llm_output
            if in_t == 0 and response.llm_output:
                tu = response.llm_output.get("token_usage", {})
                in_t  = tu.get("prompt_tokens") or tu.get("input_tokens") or 0
                out_t = tu.get("completion_tokens") or tu.get("output_tokens") or 0

            rid_key = self._rid.strip("[] ") or "global"
            if in_t > 0 or out_t > 0:
                log_tokens(rid_key, in_t, out_t)
            else:
                logger.debug(f"{self._rid}[LLM] Could not extract token counts from response")

        except Exception as e:
            logger.debug(f"Could not parse token usage: {e}")

        logger.info(f"{self._rid}[LLM  ◄] Done | {elapsed:.2f}s")

    def on_llm_error(self, error, **kwargs):
        logger.error(f"{self._rid}[LLM  ✗] ERROR: {str(error)[:150]}")

    def on_agent_finish(self, finish, **kwargs):
        logger.info(f"{self._rid}[AGENT]  ✓ Finished after {self._step} step(s)")


def _log_step(tag: str, msg: str):
    """Helper for clean route-level structured logs."""
    logger.info(f"  {tag:<14} {msg}")


# ════════════════════════════════════════════
# F. LANGCHAIN TOOLS
# MCP: fetch_gmail_newsletters, fetch_youtube_content  (live external fetches)
# Direct: search_newsletters_db, search_gmail_db_for_context, summarize_newsletter (local DB)
# ════════════════════════════════════════════

import gmail_helpers as gmail_db  # local DB searches called directly

# ── Tools shared / for Updates Agent ─────────────────────────────
@tool
def fetch_and_sync_newsletters(newsletter_names: str) -> str:
    """
    Fetches the latest newsletters from Gmail API via MCP and saves them to source.db.
    Input: comma-separated newsletter names or topics.
    """
    logger.info(f"  [MCP→GMAIL]    fetch_gmail_newsletters: {newsletter_names[:80]}")
    return _call_mcp_tool("fetch_gmail_newsletters", {"newsletter_names": newsletter_names})


@tool
def search_newsletters_db(query: str) -> str:
    """Searches the local Gmail DB for newsletters matching query (subject/summary/sender)."""
    return gmail_db.search_newsletters_db(query)


@tool
def summarize_newsletter(message_id: str) -> str:
    """Summarizes a specific newsletter by its message ID."""
    logger.info(f"  [MCP→GMAIL]    summarize_newsletter: {message_id[:20]}")
    db = SourceSessionLocal()
    email = db.query(Newsletter).filter_by(message_id=message_id).first()
    if not email:
        db.close()
        return "Newsletter not found."
    if email.summary and "Error" not in email.summary:
        db.close()
        return f"Existing Summary: {email.summary}"
    summary = summarize_text(email.clean_text)
    email.summary = summary
    db.commit()
    db.close()
    return f"Summary: {summary}"


@tool
def search_source_db_for_context(query: str) -> str:
    """
    Searches source.db for content related to the user's highlighted text.
    This unified search covers ALL sources: newsletters (Gmail), YouTube transcripts, and LinkedIn posts.
    Searches across all content fields and returns rich snippets with source attribution.
    Always call this FIRST before using any web search tool.
    Input: the user's highlighted news text or question.
    """
    logger.info(f"  [SOURCE-DB]    search_source_db_for_context: {query[:80]}")
    keywords = [k for k in re.split(r"[\s,\.]+", query) if len(k) > 3][:10]
    if not keywords:
        keywords = [query[:50]]

    db = SourceSessionLocal()
    blocks = []
    seen = set()

    # 1. Search newsletters
    for kw in keywords[:6]:
        for r in db.query(Newsletter).filter(
            Newsletter.clean_text.ilike(f"%{kw}%") |
            Newsletter.subject.ilike(f"%{kw}%") |
            Newsletter.summary.ilike(f"%{kw}%")
        ).order_by(Newsletter.received_date.desc()).limit(4).all():
            if r.message_id not in seen:
                seen.add(r.message_id)
                raw_urls = re.findall(r"https?://[^\s\]\[\)\(,;<>]+", r.clean_text or "")
                urls = list(dict.fromkeys(u.rstrip(".,;:)'\"") for u in raw_urls))[:5]
                url_list = "\n".join(f"  - {u}" for u in urls) if urls else "  None found"
                blocks.append(
                    f"[SOURCE: Newsletter]\n"
                    f"NEWSLETTER: {r.sender}\n"
                    f"REFERENCE:  {r.sender} | {r.subject} ({r.received_date.strftime('%Y-%m-%d')})\n"
                    f"SUBJECT:    {r.subject}\n"
                    f"URLS IN EMAIL:\n{url_list}\n\n"
                    f"CONTENT Snippet ({len(r.clean_text or '')} chars):\n{(r.clean_text or '')[:4000]}"
                )

    # 2. Search YouTube transcripts
    for kw in keywords[:6]:
        for r in db.query(YouTubeTranscript).filter(
            YouTubeTranscript.transcript.ilike(f"%{kw}%") |
            YouTubeTranscript.title.ilike(f"%{kw}%") |
            YouTubeTranscript.channel.ilike(f"%{kw}%")
        ).order_by(YouTubeTranscript.published_at.desc()).limit(4).all():
            if r.video_id not in seen:
                seen.add(r.video_id)
                blocks.append(
                    f"[SOURCE: YouTube]\n"
                    f"YOUTUBE CHANNEL: {r.channel}\n"
                    f"VIDEO TITLE: {r.title}\n"
                    f"URL: https://youtube.com/watch?v={r.video_id}\n\n"
                    f"TRANSCRIPT:\n{(r.transcript or '')[:4000]}"
                )

    # 3. Search LinkedIn posts
    for kw in keywords[:6]:
        for r in db.query(LinkedInPost).filter(
            LinkedInPost.text.ilike(f"%{kw}%") |
            LinkedInPost.username.ilike(f"%{kw}%")
        ).order_by(LinkedInPost.posted_at.desc()).limit(4).all():
            if r.url not in seen:
                seen.add(r.url)
                blocks.append(
                    f"[SOURCE: LinkedIn]\n"
                    f"LINKEDIN POST BY: {r.username}\n"
                    f"DATE: {r.posted_at}\n"
                    f"METRICS: {r.likes} Likes, {r.comments} Comments\n"
                    f"URL: {r.url}\n\n"
                    f"CONTENT:\n{(r.text or '')[:4000]}"
                )

    db.close()

    if not blocks:
        return "No relevant content found in source.db for this query."

    logger.info(f"  [SOURCE-DB]    search_source_db_for_context: {len(blocks)} source(s) found")
    return "\n\n" + ("\n" + "─" * 40 + "\n").join(blocks[:8])


@tool
def tavily_search(query: str) -> str:
    """
    Uses Tavily web search to fetch live content from a URL or search the web.
    Use this AFTER search_gmail_db_for_context when:
      - You found a URL inside the newsletter content, OR
      - You need more up-to-date information from the web.
    Input: a URL (preferred) or a search query string.
    """
    if not _tavily_client:
        logger.info("  [TAVILY]       Disabled — falling back to direct fetch")
        # Graceful fallback: if input looks like a URL, fetch it directly
        if query.startswith("http"):
            result = fetch_url_content_helper(query)
            return result if not result.startswith(("HTTP", "Error")) else f"Could not fetch: {query}"
        return "Tavily search is not configured. Add TAVILY_API_KEY to .env to enable web search."

    logger.info(f"  [TAVILY]       Searching: {query[:100]}")
    t0 = time.time()
    try:
        # If it's a URL, use extract; otherwise use search
        if query.startswith("http"):
            result = _tavily_client.extract(urls=[query])
            content = result.get("results", [{}])[0].get("raw_content", "No content extracted.")
        else:
            result = _tavily_client.search(query=query, max_results=3, include_raw_content=False)
            parts = []
            for r in result.get("results", []):
                parts.append(f"**{r.get('title','No title')}**\n{r.get('content','')}\nURL: {r.get('url','')}")
            content = "\n\n".join(parts) if parts else "No results found."

        logger.info(f"  [TAVILY]       Got {len(content)} chars | {time.time()-t0:.2f}s")
        return content
    except Exception as e:
        logger.error(f"  [TAVILY] ✗ Error: {e}")
        return f"Search failed: {e}"


@tool
def get_url_context(url: str) -> str:
    """
    Loads the full text content of a webpage using WebBaseLoader.
    Use this when you find a URL inside the newsletter content and want to retrieve
    the full article or page content to enrich your answer.
    Input: a complete URL starting with http or https.
    Returns: the extracted text content from the page.
    """
    if not url.startswith("http"):
        return "Input must be a URL starting with http or https."

    logger.info(f"  [WEB-LOAD]     Loading URL: {url[:100]}")
    t0 = time.time()

    if _WEBLOADER_AVAILABLE:
        try:
            loader = WebBaseLoader(url)
            loader.requests_kwargs = {"timeout": 10}
            docs = loader.load()
            content = "\n\n".join(d.page_content for d in docs).strip()
            # Trim to reasonable size
            content = re.sub(r"\n{3,}", "\n\n", content)[:4000]
            logger.info(f"  [WEB-LOAD]     Loaded {len(content)} chars via WebBaseLoader | {time.time()-t0:.2f}s")
            return content if content else "No content extracted from URL."
        except Exception as e:
            logger.warning(f"  [WEB-LOAD]     WebBaseLoader failed ({e}), falling back to direct fetch")

    # Fallback to direct fetch
    result = fetch_url_content_helper(url)
    status = "error" if result.startswith(("HTTP", "Error")) else f"{len(result)} chars"
    logger.info(f"  [WEB-LOAD]     Direct fetch {status} | {time.time()-t0:.2f}s")
    return result


@tool
def fetch_youtube_content(channel_urls: str) -> str:
    """
    Fetches the latest non-Shorts YouTube video transcript from one or more channels.
    Part of the TechUpdates Agent — use this alongside newsletter tools to enrich the briefing
    with insights from YouTube tech channels the user follows.

    Input: comma-separated YouTube channel URLs.
    Returns: channel name, video title (from RSS), and the full transcript text.
    Each result is stored in source.db so the Chat Agent can later look it up.
    """
    logger.info(f"  [MCP→YOUTUBE]  fetch_youtube_content: {channel_urls[:80]}")
    return _call_mcp_tool("fetch_youtube_content", {"channel_urls": channel_urls})


# ════════════════════════════════════════════
# G. AGENTS
# ════════════════════════════════════════════

# ── Agent 1: TechUpdates Agent (newsletters + YouTube) ────────────
_TECHUPDATES_PROMPT = """You are TechTracker, an AI assistant that curates tech briefings from newsletters AND YouTube channels.

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (repeat as needed)
Thought: I now know the final answer
Final Answer: your summarized briefing

CRITICAL RULES:
1. Every 'Thought:' MUST be followed by an 'Action:' or 'Final Answer:'. 
2. Once you output 'Action Input:', STOP. Do NOT write 'Observation:'.
3. Format your Final Answer EXACTLY like this:

## 📡 TechTracker Briefing

### 📰 Newsletter Highlights
- **[Topic]**: Crisp one-line description
- **[Topic]**: Crisp one-line description

### ▶️ YouTube Insights  *(omit section if no YouTube content)*
- **[Channel — Topic]**: Crisp one-line insight from the transcript

### 🔥 Most Notable
> Highlight the single most important item across all sources in 1-2 sentences.

### 💡 Key Takeaway
> One bottom-line insight the user should walk away with.

---
*Sources: [newsletter name(s) + YouTube channel(s)] · Powered by TechTracker AI*

Rules:
- Bold important terms, tool names, and company names
- Do NOT include raw IDs or technical junk
- If no YouTube channels are given in the question, skip the YouTube Insights section
- If no relevant data found anywhere, say so clearly

Begin!

Question: {input}
Thought:{agent_scratchpad}"""

_techupdates_agent_prompt  = PromptTemplate.from_template(_TECHUPDATES_PROMPT)
_techupdates_agent_tools   = [search_newsletters_db, fetch_and_sync_newsletters, summarize_newsletter, fetch_youtube_content]
_techupdates_agent_executor   = create_react_agent(llm, _techupdates_agent_tools, _techupdates_agent_prompt)
techupdates_agent_executor  = AgentExecutor(
    agent=_techupdates_agent_executor, tools=_techupdates_agent_tools,
    verbose=False, handle_parsing_errors=True, max_iterations=12
)

# ── Agent 2: Chat Agent (with memory + Tavily) ────────────────────
_CHAT_PROMPT = """You are TechTracker AI, a friendly tech-news assistant with deep knowledge of AI, startups, and software.

{tools}

Use the following format:

Question: the input question
Thought: your strategy
Action: the tool to use (MUST be EXACTLY one of [{tool_names}])
Action Input: the tool's input string
Observation: the tool's output
... (repeat Thought/Action/Action Input/Observation as needed)
Thought: I have the answer
Final Answer: your briefing

---
EXAMPLE FLOW:
Question: "Tell me about GPT-4o"
Thought: I need to check my local source database for GPT-4o content.
Action: search_source_db_for_context
Action Input: GPT-4o
Observation: Found result...
Thought: I have enough info.
Final Answer: GPT-4o is...
---

CRITICAL EXECUTION RULES:
1. NO MARKDOWN: Do NOT wrap tools or formatting in ``` code blocks. 
2. NO SKIPPING: Every 'Thought:' MUST be followed by an 'Action:' OR 'Final Answer:'.
3. NO PREDICTIONS: STOP after writing 'Action Input:'. Do NOT write 'Observation:'.
4. STEP SEQUENCE:
   - Step 1: ALWAYS call 'search_source_db_for_context' first — it searches newsletters, YouTube transcripts, AND LinkedIn posts in one go.
   - Step 2: If the result contains URLs, use 'get_url_context' for each relevant one.
   - Step 3: Only use 'tavily_search' if you still lack key details.
5. CITATION: Your Final Answer MUST end with a '### 🔗 References' section citing sources.
6. STYLE: Lead with '## 🔍 Deep Dive: [Topic]'.

Begin!

Question: {input}
Thought:{agent_scratchpad}"""

_chat_prompt   = PromptTemplate.from_template(_CHAT_PROMPT)
_chat_tools    = [search_source_db_for_context, get_url_context, tavily_search]
_chat_agent    = create_react_agent(llm, _chat_tools, _chat_prompt)
chat_executor  = AgentExecutor(
    agent=_chat_agent, tools=_chat_tools,
    verbose=False, handle_parsing_errors=True, max_iterations=15
)


# ════════════════════════════════════════════
# H. ROUTES
# ════════════════════════════════════════════

GREETINGS = {
    "hi", "hello", "hey", "hiya", "howdy", "greetings",
    "good morning", "good afternoon", "good evening",
    "how are you", "what can you do", "help", "who are you",
    "what do you do", "what are you", "sup", "yo",
}


@app.get("/")
def root():
    return {
        "service": "TechTracker AI",
        "agents": ["updates_agent", "chat_agent"],
        "databases": ["data/source.db", "data/chat_history.db", "data/daily_updates.db", "data/user_data.db"],
        "endpoints": ["/get_updates", "/today_updates", "/calendar_updates",
                      "/chat_summarise", "/chat_history", "/available_dates"],
    }


# ── GET /get_updates ─────────────────────────────────────────────
@app.get("/get_updates")
def get_updates(
    query:       str = Query(...),
    newsletters: str = Query(...),
    yt_channels: str = Query(default="", description="Comma-separated YouTube channel URLs"),
):
    req_id = datetime.utcnow().strftime("%H%M%S")
    logger.info("─" * 55)
    logger.info(f"  [REQUEST]      GET /get_updates  [{req_id}]")
    logger.info(f"  [INPUT]        query='{query[:60]}' | nl={newsletters} | yt={'yes' if yt_channels else 'no'}")
    t0 = time.time()
    try:
        yt_part = f" YouTube channels to fetch: {yt_channels}." if yt_channels else ""
        agent_input = (
            f"User Query: {query}. "
            f"The user follows these newsletters: {newsletters}.{yt_part} "
            "Search the newsletter DB first; sync Gmail if needed; "
            "also fetch the latest YouTube transcript for any provided channel URLs."
        )
        response     = techupdates_agent_executor.invoke(
            {"input": agent_input},
            config={"callbacks": [TechTrackerCallbackHandler(req_id)]}
        )
        final_answer = response["output"]

        chat_db = ChatSessionLocal()
        chat_db.add(ChatMessage(user_query=query, newsletters_followed=newsletters, agent_response=final_answer))
        chat_db.commit()
        chat_db.close()

        stats = session_stats.get(req_id, {"in_tokens": 0, "out_tokens": 0, "cost": 0.0})
        logger.info(f"  [SESSION]      Total Tokens: {stats['in_tokens']+stats['out_tokens']} | Total Cost: ${stats['cost']:.6f}")
        logger.info(f"  [LATENCY]      /get_updates done | {time.time()-t0:.2f}s")
        logger.info("─" * 55)
        return {"query": query, "newsletters_followed": newsletters, "response": final_answer, "usage": stats}
    except Exception as e:
        logger.error(f"  [ERROR]        /get_updates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /today_updates ───────────────────────────────────────────
@app.get("/today_updates")
def today_updates(
    newsletters: str = Query(default=""),
    days:        int  = Query(default=7),
    force:       bool = Query(default=False, description="Skip cache & DB, go straight to Gmail"),
    yt_channels: str  = Query(default="", description="Comma-separated YouTube channel URLs"),
    linkedin_profiles: str = Query(default="", description="Comma-separated LinkedIn profile handles"),
):
    req_id    = datetime.utcnow().strftime("%H%M%S")
    today_str = datetime.utcnow().date().isoformat()
    nl_key    = ",".join(sorted(n.strip().lower() for n in newsletters.split(",") if n.strip()))

    logger.info("─" * 55)
    logger.info(f"  [REQUEST]      GET /today_updates  [{req_id}] force={force}")
    logger.info(f"  [INPUT]        date={today_str} | newsletters={nl_key}")
    t0 = time.time()

    try:
        nl_list = [n for n in nl_key.split(",") if n]
        all_emails = []
        is_today = True
        fallback_msg = None

        if nl_list:
            if force:
                # ── Force-refresh: skip cache & DB, go directly to Gmail ──
                _log_step("[FORCE]", "Skipping cache & DB — syncing Gmail directly")
                t_sync = time.time()
                fetch_and_sync_newsletters.invoke({"newsletter_names": newsletters})
                _log_step("", f"Gmail sync done | {time.time()-t_sync:.2f}s")
    
                today_filter  = sql_func.date(Newsletter.received_date) == today_str
                db_f = SourceSessionLocal()
                all_emails = query_emails_for_nl(db_f, nl_list, extra_filter=today_filter)
                db_f.close()
                _log_step("", f"Post-sync: {len(all_emails)} today emails in source.db")
    
                if not all_emails:
                    # Fallback within force mode — take recent
                    cutoff = datetime.utcnow() - timedelta(days=days)
                    db_fb = SourceSessionLocal()
                    all_emails = query_emails_for_nl(db_fb, nl_list,
                                                     extra_filter=Newsletter.received_date >= cutoff,
                                                     limit_each=3)
                    db_fb.close()
    
                is_today = True
                fallback_msg = None
    
            else:
                # ── Normal waterfall (cache → DB → Gmail → fallback) ─────

                # Step 1: DailyUpdates cache
                _log_step("[STEP 1/5]", f"Check daily_updates.db cache for {today_str}")
                t1 = time.time()
                daily_db = DailySessionLocal()
                cached = daily_db.query(DailyUpdate).filter(
                    DailyUpdate.date == today_str,
                    DailyUpdate.newsletters == nl_key,
                ).order_by(DailyUpdate.created_at.desc()).first()
                daily_db.close()
                _log_step("", f"Cache {'HIT ✓' if cached else 'MISS'} | {time.time()-t1:.2f}s")
    
                if cached:
                    headlines = json_module.loads(cached.headlines_json)
                    logger.info(f"  [LATENCY]      Cache served {len(headlines)} headlines | {time.time()-t0:.2f}s")
                    logger.info("─" * 55)
                    return {"headlines": headlines, "newsletters": nl_key.split(","),
                            "count": len(headlines), "is_today": True,
                            "source": "cache", "message": None,
                            "generated_at": cached.created_at.isoformat()}

                # Step 2: Check source.db for today
                today_filter = sql_func.date(Newsletter.received_date) == today_str
                _log_step("[STEP 2/5]", "Check source.db for today's emails")
                t2 = time.time()
                db = SourceSessionLocal()
                today_emails = query_emails_for_nl(db, nl_list, extra_filter=today_filter)
                db.close()
                _log_step("", f"Found {len(today_emails)} emails | {time.time()-t2:.2f}s")
    
                # Step 3: Gmail sync if needed
                if not today_emails:
                    _log_step("[STEP 3/5]", "No today emails → syncing Gmail")
                    t3 = time.time()
                    fetch_and_sync_newsletters.invoke({"newsletter_names": newsletters})
                    _log_step("", f"Gmail sync done | {time.time()-t3:.2f}s")
                    db2 = SourceSessionLocal()
                    today_emails = query_emails_for_nl(db2, nl_list, extra_filter=today_filter)
                    db2.close()
                    _log_step("", f"Post-sync: {len(today_emails)} emails in source.db")
                else:
                    _log_step("[STEP 3/5]", "Skipped (emails already in source.db)")

                # Step 4: Fallback to recent emails
                is_today     = len(today_emails) > 0
                fallback_msg = None
                all_emails   = today_emails
    
                if not all_emails:
                    _log_step("[STEP 4/5]", f"Fallback → querying last {days} days")
                    t4 = time.time()
                    fallback_msg = "📅 No new newsletters today. Showing the latest we have."
                    cutoff = datetime.utcnow() - timedelta(days=days)
                    db3 = SourceSessionLocal()
                    all_emails = query_emails_for_nl(db3, nl_list,
                                                     extra_filter=Newsletter.received_date >= cutoff,
                                                     limit_each=3)
                    db3.close()
                    _log_step("", f"Fallback found {len(all_emails)} emails | {time.time()-t4:.2f}s")
                else:
                    _log_step("[STEP 4/5]", "Skipped (today emails found)")

        # ── Shared: extract headlines via Gemini ──────────────────
        if not all_emails and not yt_channels and not linkedin_profiles:
            logger.warning("  [RESULT]       No sources found — check config")
            logger.info("─" * 55)
            return {"headlines": [], "newsletters": nl_list, "count": 0,
                    "is_today": False, "source": "none",
                    "message": "No sources found. Check your configuration.",
                    "generated_at": datetime.utcnow().isoformat()}

        _log_step("[STEP 5/5]", f"Gemini extract_headlines on DB content")

        t5 = time.time()
        combined = "\n\n---\n\n".join(
            f"Newsletter: {e.sender}\nSubject: {e.subject}\nDate: {e.received_date}\n\n{e.clean_text[:5000] or ''}"
            for e in all_emails[:8]
        )

        # ── Append YouTube transcripts — DB first, API fallback ──────
        if yt_channels:
            yt_urls = [u.strip() for u in yt_channels.split(",") if u.strip()]
            _log_step("[YT]", f"Checking source.db for today's transcripts ({len(yt_urls)} channel(s))")
            t_yt = time.time()
            yt_db = SourceSessionLocal()
            cached_yt = yt_db.query(YouTubeTranscript).filter(
                sql_func.date(YouTubeTranscript.published_at) == today_str
            ).all()
            yt_db.close()
            if cached_yt:
                _log_step("", f"source.db HIT ✓ — {len(cached_yt)} transcript(s) from DB | {time.time()-t_yt:.2f}s")
                yt_content = "\n\n---\n\n".join(
                    f"Channel: {r.channel}\nVideo: {r.title}\nURL: https://youtube.com/watch?v={r.video_id}\n\n{(r.transcript or '')[:4000]}"
                    for r in cached_yt
                )
                combined += "\n\n---\n\n" + yt_content
            else:
                _log_step("", f"source.db MISS — calling API | {time.time()-t_yt:.2f}s")
                yt_content = _call_mcp_tool("fetch_youtube_content", {"channel_urls": yt_channels})
                if yt_content and "Error" not in yt_content and "No YouTube" not in yt_content:
                    combined += "\n\n---\n\n" + yt_content
                    _log_step("", f"YouTube content added via API | {time.time()-t_yt:.2f}s")
                else:
                    _log_step("", f"No YouTube transcripts fetched | {time.time()-t_yt:.2f}s")

        # ── Append LinkedIn posts — DB first, API fallback ────────────
        if linkedin_profiles:
            handles = [h.strip() for h in linkedin_profiles.split(",") if h.strip()]
            _log_step("[LI]", f"Checking source.db for today's posts ({len(handles)} profile(s))")
            t_li = time.time()
            lnkn_db = SourceSessionLocal()
            li_content = []
            for handle in handles:
                cached_li = lnkn_db.query(LinkedInPost).filter(
                    LinkedInPost.username == handle,
                    LinkedInPost.posted_at.like(f"{today_str}%")
                ).all()
                if cached_li:
                    _log_step("", f"source.db HIT ✓ — {len(cached_li)} post(s) for @{handle}")
                    for r in cached_li:
                        li_content.append(f"LinkedIn Profile: {handle}\nDate: {r.posted_at}\nLikes: {r.likes} Comments: {r.comments}\n\n{r.text}")
                else:
                    _log_step("", f"source.db MISS — calling API for @{handle}")
                    posts = fetch_linkedin_posts(handle)
                    for p in posts:
                        posted_str = p.get('posted', {}).get('fullDate') if isinstance(p.get('posted'), dict) else str(p.get('posted', ''))
                        exists = lnkn_db.query(LinkedInPost).filter(LinkedInPost.url == p['url']).first()
                        if not exists:
                            lnkn_db.add(LinkedInPost(
                                username=p['username'], url=p['url'], text=p['text'],
                                likes=p['likes'], comments=p['comments'], posted_at=posted_str
                            ))
                        li_content.append(f"LinkedIn Profile: {handle}\nDate: {posted_str}\nLikes: {p['likes']} Comments: {p['comments']}\n\n{p['text']}")
            lnkn_db.commit()
            lnkn_db.close()
            if li_content:
                combined += "\n\n---\n\n" + "\n\n---\n\n".join(li_content)
                _log_step("", f"LinkedIn content added ({len(li_content)} posts) | {time.time()-t_li:.2f}s")
            else:
                _log_step("", f"No LinkedIn posts fetched | {time.time()-t_li:.2f}s")

        all_sources = newsletters + ("," + yt_channels if yt_channels else "") + ("," + linkedin_profiles if linkedin_profiles else "")
        headlines = extract_headlines(combined, all_sources, req_id=req_id)
        _log_step("", f"Extracted {len(headlines)} headlines | {time.time()-t5:.2f}s")

        # Cache if today
        if is_today and headlines:
            daily_db2 = DailySessionLocal()
            daily_db2.add(DailyUpdate(
                date=today_str, newsletters=nl_key,
                headlines_json=json_module.dumps(headlines),
                email_count=len(all_emails),
            ))
            daily_db2.commit()
            daily_db2.close()
            _log_step("[CACHE]", f"Saved {len(headlines)} headlines to daily_updates.db")

        # Report final stats for this request
        stats = session_stats.get(req_id, {"in_tokens": 0, "out_tokens": 0, "cost": 0.0})
        logger.info(f"  [SESSION]      Total Tokens: {stats['in_tokens']+stats['out_tokens']} | Total Cost: ${stats['cost']:.6f}")
        
        logger.info(f"  [LATENCY]      /today_updates done | is_today={is_today} | total={time.time()-t0:.2f}s")
        logger.info("─" * 55)
        return {"headlines": headlines, "newsletters": nl_list,
                "count": len(headlines), "is_today": is_today,
                "source": "fresh", "message": fallback_msg,
                "generated_at": datetime.utcnow().isoformat(),
                "usage": stats}
    except Exception as e:
        logger.error(f"  [ERROR]        /today_updates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /available_dates ─────────────────────────────────────────
@app.get("/available_dates")
def available_dates(newsletters: str = Query(...)):
    nl_key = ",".join(sorted(n.strip().lower() for n in newsletters.split(",") if n.strip()))
    daily_db = DailySessionLocal()
    rows = daily_db.query(DailyUpdate.date).filter(DailyUpdate.newsletters == nl_key).distinct().all()
    daily_db.close()
    dates = sorted({r.date for r in rows}, reverse=True)
    logger.info(f"  [DAILY-DB]     available_dates: {len(dates)} dates for {nl_key}")
    return {"dates": dates, "count": len(dates)}


# ── GET /calendar_updates ────────────────────────────────────────
@app.get("/calendar_updates")
def calendar_updates(
    date:        str = Query(...),
    newsletters: str = Query(default=""),
    yt_channels: str = Query(default="", description="Comma-separated YouTube channel URLs"),
    linkedin_profiles: str = Query(default="", description="Comma-separated LinkedIn profile handles"),
):
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date. Use YYYY-MM-DD.")

    req_id  = datetime.utcnow().strftime("%H%M%S")
    nl_key  = ",".join(sorted(n.strip().lower() for n in newsletters.split(",") if n.strip()))
    nl_list = [n for n in nl_key.split(",") if n]

    logger.info("─" * 55)
    logger.info(f"  [REQUEST]      GET /calendar_updates  [{req_id}]")
    logger.info(f"  [INPUT]        date={date} | newsletters={nl_key}")
    t0 = time.time()

    # ── Step 1: DailyUpdates cache ────────────────────────────────
    _log_step("[STEP 1/4]", "Check daily_updates.db cache")
    t1 = time.time()
    daily_db = DailySessionLocal()
    cached = daily_db.query(DailyUpdate).filter(
        DailyUpdate.date == date,
        DailyUpdate.newsletters == nl_key,
    ).order_by(DailyUpdate.created_at.desc()).first()
    daily_db.close()

    if cached:
        headlines = json_module.loads(cached.headlines_json)
        _log_step("", f"Cache HIT ✓ | {len(headlines)} headlines | {time.time()-t1:.2f}s")
        logger.info(f"  [LATENCY]      /calendar_updates done | {time.time()-t0:.2f}s")
        logger.info("─" * 55)
        return {"headlines": headlines, "date": date, "newsletters": nl_list,
                "count": len(headlines), "source": "cache"}
    _log_step("", f"Cache MISS | {time.time()-t1:.2f}s")

    # ── Step 2: Check source.db ────────────────────────────────────────
    date_filter = sql_func.date(Newsletter.received_date) == target_date.isoformat()
    _log_step("[STEP 2/4]", f"Check source.db for {date}")
    t2 = time.time()
    db = SourceSessionLocal()
    all_emails = query_emails_for_nl(db, nl_list, extra_filter=date_filter, limit_each=5) if nl_list else []
    db.close()
    _log_step("", f"Found {len(all_emails)} emails | {time.time()-t2:.2f}s")

    # ── Step 3: Gmail sync if recent ─────────────────────────────
    if nl_list and not all_emails and target_date >= (datetime.utcnow().date() - timedelta(days=30)):
        _log_step("[STEP 3/4]", f"No emails → syncing Gmail for {date}")
        t3 = time.time()
        _call_mcp_tool("fetch_gmail_newsletters", {"newsletter_names": f"{nl_key}|date:{date}"})
        _log_step("", f"Gmail sync done | {time.time()-t3:.2f}s")
        db2 = SourceSessionLocal()
        all_emails = query_emails_for_nl(db2, nl_list, extra_filter=date_filter, limit_each=5)
        db2.close()
        _log_step("", f"Post-sync: {len(all_emails)} emails")
    else:
        _log_step("[STEP 3/4]", "Skipped" if all_emails else "Skipped (no newsletters or date too old)")

    if not all_emails and not yt_channels and not linkedin_profiles:
        logger.info(f"  [RESULT]       No sources for {date}")
        logger.info("─" * 55)
        return {"headlines": [], "date": date, "newsletters": nl_list,
                "count": 0, "source": "none", "message": f"No sources found for {date}."}

    # ── Step 4: Extract headlines ─────────────────────────────────
    _log_step("[STEP 4/4]", f"Gemini extract_headlines on {len(all_emails)} emails")
    t4 = time.time()
    parts = [
        f"Newsletter: {e.sender}\nSubject: {e.subject}\n\n{e.clean_text[:5000] or ''}"
        for e in all_emails[:8]
    ]
    combined_cal = "\n\n---\n\n".join(parts)

    # ── Append YouTube transcripts — DB first, API fallback ──
    if yt_channels:
        yt_urls = [u.strip() for u in yt_channels.split(",") if u.strip()]
        _log_step("[YT]", f"Checking source.db for {date} ({len(yt_urls)} channel(s))")
        t_yt = time.time()
        yt_db = SourceSessionLocal()
        cached_yt = yt_db.query(YouTubeTranscript).filter(
            sql_func.date(YouTubeTranscript.published_at) == date
        ).all()
        yt_db.close()
        if cached_yt:
            _log_step("", f"source.db HIT ✓ — {len(cached_yt)} transcript(s) | {time.time()-t_yt:.2f}s")
            yt_content = "\n\n---\n\n".join(
                f"Channel: {r.channel}\nVideo: {r.title}\nURL: https://youtube.com/watch?v={r.video_id}\n\n{(r.transcript or '')[:4000]}"
                for r in cached_yt
            )
            combined_cal += "\n\n---\n\n" + yt_content
        else:
            _log_step("", f"source.db MISS — calling API | {time.time()-t_yt:.2f}s")
            yt_content = _call_mcp_tool("fetch_youtube_content", {"channel_urls": yt_channels})
            if yt_content and "Error" not in yt_content and "No YouTube" not in yt_content:
                combined_cal += "\n\n---\n\n" + yt_content
                _log_step("", f"YouTube content added via API | {time.time()-t_yt:.2f}s")

    # ── Append LinkedIn posts — DB first, API fallback ──
    if linkedin_profiles:
        handles = [h.strip() for h in linkedin_profiles.split(",") if h.strip()]
        _log_step("[LI]", f"Checking source.db for {date} posts ({len(handles)} profile(s))")
        t_li = time.time()
        lnkn_db = SourceSessionLocal()
        li_content = []
        for handle in handles:
            cached_li = lnkn_db.query(LinkedInPost).filter(
                LinkedInPost.username == handle,
                LinkedInPost.posted_at.like(f"{date}%")
            ).all()
            if cached_li:
                _log_step("", f"source.db HIT ✓ — {len(cached_li)} post(s) for @{handle}")
                for r in cached_li:
                    li_content.append(f"LinkedIn Profile: {handle}\nDate: {r.posted_at}\nLikes: {r.likes} Comments: {r.comments}\n\n{r.text}")
            else:
                _log_step("", f"source.db MISS — calling API for @{handle}")
                posts = fetch_linkedin_posts(handle)
                for p in posts:
                    posted_str = p.get('posted', {}).get('fullDate') if isinstance(p.get('posted'), dict) else str(p.get('posted', ''))
                    exists = lnkn_db.query(LinkedInPost).filter(LinkedInPost.url == p['url']).first()
                    if not exists:
                        lnkn_db.add(LinkedInPost(
                            username=p['username'], url=p['url'], text=p['text'],
                            likes=p['likes'], comments=p['comments'], posted_at=posted_str
                        ))
                    li_content.append(f"LinkedIn Profile: {handle}\nDate: {posted_str}\nLikes: {p['likes']} Comments: {p['comments']}\n\n{p['text']}")
        lnkn_db.commit()
        lnkn_db.close()
        if li_content:
            combined_cal += "\n\n---\n\n" + "\n\n---\n\n".join(li_content)
            _log_step("", f"LinkedIn content added ({len(li_content)} posts) | {time.time()-t_li:.2f}s")
        else:
            _log_step("", f"No LinkedIn posts fetched | {time.time()-t_li:.2f}s")

    all_sources_cal = newsletters + ("," + yt_channels if yt_channels else "") + ("," + linkedin_profiles if linkedin_profiles else "")
    headlines = extract_headlines(combined_cal, all_sources_cal, req_id=req_id)
    _log_step("", f"Extracted {len(headlines)} headlines | {time.time()-t4:.2f}s")

    if headlines:
        daily_db2 = DailySessionLocal()
        daily_db2.add(DailyUpdate(
            date=date, newsletters=nl_key,
            headlines_json=json_module.dumps(headlines),
            email_count=len(all_emails),
        ))
        daily_db2.commit()
        daily_db2.close()
        _log_step("[CACHE]", f"Saved {len(headlines)} headlines to daily_updates.db")

    stats = session_stats.get(req_id, {"in_tokens": 0, "out_tokens": 0, "cost": 0.0})
    logger.info(f"  [SESSION]      Total Tokens: {stats['in_tokens']+stats['out_tokens']} | Total Cost: ${stats['cost']:.6f}")
    logger.info(f"  [LATENCY]      /calendar_updates done | {time.time()-t0:.2f}s")
    logger.info("─" * 55)
    return {"headlines": headlines, "date": date, "newsletters": nl_list,
            "count": len(headlines), "source": "fresh", "usage": stats}


# ── GET /chat_summarise ──────────────────────────────────────────
@app.get("/chat_summarise")
def chat_summarise(
    text:        str = Query(..., description="User question or highlighted text"),
    newsletters: str = Query(..., description="Comma-separated newsletter names"),
    session_id:  str = Query(default="default", description="Chat session ID for memory"),
):
    """
    Chat Agent: deep-dive on highlighted text or answer any question.
    Maintains per-session conversation memory.
    """
    req_id = datetime.utcnow().strftime("%H%M%S")
    logger.info("─" * 55)
    logger.info(f"  [REQUEST]      GET /chat_summarise  [{req_id}]")
    logger.info(f"  [INPUT]        session={session_id} | text_len={len(text)}")
    t0 = time.time()

    # ── Fast-path: greetings ──────────────────────────────────────
    clean_input = text.lower().strip().rstrip("!?.")
    if clean_input in GREETINGS or (len(text.split()) <= 3 and any(g in clean_input for g in GREETINGS)):
        reply = (
            "👋 Hey! I'm **TechTracker AI** — your personal tech-news assistant.\n\n"
            "Here's what I can do:\n"
            "- 🔍 **Deep dive** any tech news — hover a headline and click *✨ AI Summarise*\n"
            "- 💬 **Answer follow-up questions** about anything in the briefing\n"
            "- 🔗 **Fetch articles** from URLs inside newsletter content\n"
            "- 🌐 **Search the web** via Tavily for extra context on any topic\n\n"
            "Just highlight any news item or ask me anything!"
        )
        logger.info(f"  [LATENCY]      Greeting fast-path | {time.time()-t0:.2f}s")
        logger.info("─" * 55)
        save_to_history(session_id, text, reply)
        return {"user_text": text, "summary": reply, "sources_count": 0, "urls_fetched": 0}

    try:
        # ── Build input with conversation history ─────────────────
        history = format_chat_history(session_id)
        history_turns = len(chat_sessions.get(session_id, []))
        if history_turns:
            logger.info(f"  [MEMORY]       Session '{session_id}' has {history_turns} prior turn(s)")

        agent_input = (
            f"{history}"
            f"The user is reading newsletters: {newsletters}.\n"
            f"User's question/highlighted text: {text}"
        )

        # ── Run Chat Agent ────────────────────────────────────────
        _log_step("[AGENT]", f"Querying agent with context ({len(agent_input)} chars)")
        response = chat_executor.invoke(
            {"input": agent_input},
            config={"callbacks": [TechTrackerCallbackHandler(req_id)]}
        )
        summary = response["output"]

        # ── Save to memory + chat_history.db ─────────────────────
        save_to_history(session_id, text, summary)
        chat_db = ChatSessionLocal()
        chat_db.add(ChatMessage(
            user_query=f"[Chat:{session_id}] {text[:200]}",
            newsletters_followed=newsletters,
            agent_response=summary,
        ))
        chat_db.commit()
        chat_db.close()

        urls_in_response = len(extract_urls_from_text(summary))
        stats = session_stats.get(req_id, {"in_tokens": 0, "out_tokens": 0, "cost": 0.0})
        logger.info(f"  [SESSION]      Total Tokens: {stats['in_tokens']+stats['out_tokens']} | Total Cost: ${stats['cost']:.6f}")
        logger.info(f"  [LATENCY]      /chat_summarise done | {time.time()-t0:.2f}s")
        logger.info("─" * 55)
        return {"user_text": text, "summary": summary,
                "sources_count": 1, "urls_fetched": urls_in_response, "usage": stats}
    except Exception as e:
        logger.error(f"  [ERROR]        /chat_summarise: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /chat_history ────────────────────────────────────────────
@app.get("/chat_history")
def get_chat_history(limit: int = Query(default=20)):
    db = ChatSessionLocal()
    try:
        msgs = db.query(ChatMessage).order_by(ChatMessage.created_at.desc()).limit(limit).all()
        return [
            {"id": m.id, "user_query": m.user_query,
             "newsletters_followed": m.newsletters_followed,
             "agent_response": m.agent_response,
             "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in msgs
        ]
    finally:
        db.close()
@app.post("/save_credentials")
async def save_credentials(data: dict):
    service = data.get("service")
    creds = data.get("credentials", {})
    if not service or not creds:
        raise HTTPException(status_code=400, detail="Missing service or credentials")
    
    db = UserDataSessionLocal()
    try:
        for k, v in creds.items():
            # Update if exists, else insert
            existing = db.query(ConnectorCredential).filter_by(service=service, key_name=k).first()
            if existing:
                existing.value = v
            else:
                db.add(ConnectorCredential(service=service, key_name=k, value=v))
        db.commit()
        logger.info(f"  [CONFIG]       Saved {len(creds)} credentials for '{service}'")
        return {"status": "ok", "message": f"Saved credentials for {service}"}
    except Exception as e:
        db.rollback()
        logger.error(f"  [CONFIG]       Error saving credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/get_credentials")
def get_credentials(service: str = Query(...)):
    db = UserDataSessionLocal()
    creds = db.query(ConnectorCredential).filter_by(service=service).all()
    db.close()
    return {c.key_name: c.value for c in creds}

# ── Serve frontend static files (must be last) ────────────────
if os.path.exists("frontend"):
    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
