"""
gmail_helpers.py — Gmail OAuth + email parsing utilities for TechTracker MCP.
"""
import os
import re
import base64
import logging
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

from database import NewsletterSessionLocal, UserDataSessionLocal
from models import ConnectorCredential, Email

logger = logging.getLogger("TechTracker.MCP")

TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1"


def get_credential(service: str, key_name: str) -> Optional[str]:
    """Fetch a credential from user_data.db, falling back to .env."""
    db = UserDataSessionLocal()
    c = db.query(ConnectorCredential).filter_by(service=service, key_name=key_name).first()
    db.close()
    if c and c.value:
        return c.value
    return os.getenv(f"{service.upper()}_{key_name.upper()}")


def get_access_token() -> str:
    """Exchange the stored refresh token for a fresh Gmail access token."""
    c_id  = get_credential("gmail", "client_id")
    c_sec = get_credential("gmail", "client_secret")
    r_tok = get_credential("gmail", "refresh_token")
    if not all([c_id, c_sec, r_tok]):
        raise ValueError("Missing Gmail credentials in .env / user_data.db")
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"client_id": c_id, "client_secret": c_sec,
              "refresh_token": r_tok, "grant_type": "refresh_token"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise ValueError(f"Token refresh failed: {resp.text}")
    return resp.json()["access_token"]


def decode_base64url(data: str) -> str:
    """Decode a URL-safe base64 string to UTF-8 text."""
    data = data.replace("-", "+").replace("_", "/")
    return base64.b64decode(data).decode("utf-8", errors="ignore")


def extract_html(payload: dict) -> Optional[str]:
    """Recursively extract the first text/html part from a Gmail message payload."""
    if payload.get("mimeType") == "text/html":
        return decode_base64url(payload["body"].get("data", ""))
    for part in payload.get("parts", []):
        html = extract_html(part)
        if html:
            return html
    return None


def clean_html(html: str) -> str:
    """Strip HTML to readable plain text, removing scripts, ads, and unsubscribe links."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for a in soup.find_all("a", href=True):
        link_text = a.get_text(strip=True)
        link_url  = a["href"]
        if link_url.startswith(("http", "https")):
            a.replace_with(f" {link_text} [{link_url}] " if link_text else f" [{link_url}] ")
    for el in soup.find_all(string=re.compile("unsubscribe", re.I)):
        try:
            if el.parent and el.parent.name not in ("body", "html"):
                el.parent.decompose()
        except Exception:
            pass
    for img in soup.find_all("img"):
        img.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()


def sync_newsletters(newsletter_names: str) -> str:
    """
    Fetch up to 20 Gmail messages matching the given newsletter names and
    save new ones to local_gmail.db. Returns a summary string.
    """
    logger.info(f"[GMAIL] Syncing: {newsletter_names[:80]}")
    token  = get_access_token()
    names  = [n.strip() for n in newsletter_names.split(",")]
    query  = " OR ".join(set(names))

    resp = requests.get(
        f"{GMAIL_API}/users/me/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": query, "maxResults": 20},
        timeout=15,
    )
    messages = resp.json().get("messages", [])
    if not messages:
        return f"No newsletters found in Gmail for '{newsletter_names}'."

    db = NewsletterSessionLocal()
    new_count, already = 0, 0
    found_senders: set = set()

    for msg in messages:
        mid = msg["id"]
        if db.query(Email).filter_by(message_id=mid).first():
            already += 1
            continue
        detail  = requests.get(
            f"{GMAIL_API}/users/me/messages/{mid}",
            headers={"Authorization": f"Bearer {token}"},
            params={"format": "full"},
        ).json()
        payload = detail.get("payload", {})
        hdrs    = {h["name"]: h["value"] for h in payload.get("headers", [])}
        html    = extract_html(payload)
        sender  = hdrs.get("From", "Unknown")
        found_senders.add(sender)
        db.add(Email(
            message_id=mid,
            subject=hdrs.get("Subject"),
            sender=sender,
            received_date=datetime.fromtimestamp(int(detail["internalDate"]) / 1000),
            raw_html=html,
            clean_text=clean_html(html),
            summary=None,
            processed=True,
        ))
        new_count += 1

    db.commit()
    db.close()
    sender_list = sorted(found_senders)
    logger.info(f"[GMAIL] Saved {new_count} new | {already} already present")
    return f"Synced {new_count} new newsletters. Found emails from: {', '.join(sender_list)}."


def search_newsletters_db(query: str) -> str:
    """
    Search local_gmail.db for newsletters matching query across subject/summary/sender.
    Returns a formatted list of matches with IDs, subjects, dates, and summaries.
    """
    logger.info(f"[GMAIL] search_newsletters_db: {query[:80]}")
    noise = ["today", "yesterday", "last week", "this week", "'s", "summary", "summarise"]
    term = query.lower()
    for w in noise:
        term = term.replace(w, "")
    keywords = [k for k in re.split(r"[ ,]+", term.strip()) if len(k) > 2]
    if not keywords:
        return f"Query '{query}' is too vague. Please provide a newsletter name."

    db = NewsletterSessionLocal()
    seen, results = set(), []
    for kw in keywords:
        for r in db.query(Email).filter(
            Email.subject.ilike(f"%{kw}%") |
            Email.summary.ilike(f"%{kw}%") |
            Email.sender.ilike(f"%{kw}%")
        ).order_by(Email.received_date.desc()).limit(10).all():
            if r.message_id not in seen:
                results.append(r)
                seen.add(r.message_id)
    results.sort(key=lambda x: x.received_date, reverse=True)
    results = results[:10]
    db.close()

    if not results:
        return f"No newsletters found in local DB for '{query}'."

    logger.info(f"[GMAIL] search_newsletters_db: {len(results)} results")
    return "Relevant Newsletters Found:\n" + "\n".join(
        f"- ID:{r.message_id} | {r.subject} ({r.received_date}) | From: {r.sender} | "
        f"Summary: {(r.summary or 'Not summarized')[:200]}"
        for r in results
    )


def search_gmail_db_for_context(query: str) -> str:
    """
    Search local_gmail.db for newsletter content related to a query.
    Searches clean_text, subject, and summary. Returns rich snippets with URLs.
    Call this before any web search.
    """
    logger.info(f"[GMAIL] search_gmail_db_for_context: {query[:80]}")
    keywords = [k for k in re.split(r"[\s,\.]+", query) if len(k) > 3][:10]
    if not keywords:
        keywords = [query[:50]]

    db = NewsletterSessionLocal()
    seen, matching = set(), []
    for kw in keywords[:6]:
        for r in db.query(Email).filter(
            Email.clean_text.ilike(f"%{kw}%") |
            Email.subject.ilike(f"%{kw}%") |
            Email.summary.ilike(f"%{kw}%")
        ).order_by(Email.received_date.desc()).limit(4).all():
            if r.message_id not in seen:
                matching.append(r)
                seen.add(r.message_id)
    db.close()

    if not matching:
        return "No relevant content found in local_gmail.db for this query."

    blocks = []
    for r in matching[:4]:
        raw_urls = re.findall(r"https?://[^\s\]\[\)\(,;<>]+", r.clean_text or "")
        urls = list(dict.fromkeys(u.rstrip(".,;:)'\"") for u in raw_urls))[:5]
        url_list = "\n".join(f"  - {u}" for u in urls) if urls else "  None found"
        blocks.append(
            f"NEWSLETTER: {r.sender}\n"
            f"REFERENCE:  {r.sender} | {r.subject} ({r.received_date.strftime('%Y-%m-%d')})\n"
            f"SUBJECT:    {r.subject}\n"
            f"URLS IN EMAIL:\n{url_list}\n\n"
            f"CONTENT Snippet ({len(r.clean_text or '')} chars):\n{(r.clean_text or '')[:4000]}"
        )
    logger.info(f"[GMAIL] search_gmail_db_for_context: {len(matching)} source(s)")
    return "\n\n" + ("\n" + "─" * 40 + "\n").join(blocks)
