"""
models.py  — SQLAlchemy ORM models.
Content models (Newsletter, YouTubeTranscript, LinkedInPost) all live in source.db.
"""
from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer
from datetime import datetime
from database import Base


# ── source.db: newsletters table ──────────────────────────────
class Newsletter(Base):
    __tablename__ = "newsletters"

    message_id   = Column(String, primary_key=True, index=True)
    subject      = Column(String)
    sender       = Column(String)
    received_date = Column(DateTime)
    raw_html     = Column(Text)
    clean_text   = Column(Text)
    summary      = Column(Text)
    processed    = Column(Boolean, default=False)
    created_at   = Column(DateTime, default=datetime.utcnow)


# ── source.db: youtube_transcripts table ─────────────────────
class YouTubeTranscript(Base):
    __tablename__ = "youtube_transcripts"

    video_id     = Column(String, primary_key=True, index=True)
    channel      = Column(String, index=True)
    title        = Column(String)
    transcript   = Column(Text)
    published_at = Column(DateTime)
    created_at   = Column(DateTime, default=datetime.utcnow)



# ── chat_history.db ────────────────────────────────────────────
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id                   = Column(Integer, primary_key=True, index=True)
    user_query           = Column(Text)
    newsletters_followed = Column(Text)   # comma-separated
    agent_response       = Column(Text)
    created_at           = Column(DateTime, default=datetime.utcnow)


# ── daily_updates.db ───────────────────────────────────────────
class DailyUpdate(Base):
    """
    Stores a snapshot of headlines for a given date + newsletter combo.
    This allows instant calendar lookups without re-running Gemini.
    """
    __tablename__ = "daily_updates"

    id               = Column(Integer, primary_key=True, index=True)
    date             = Column(String, index=True)        # YYYY-MM-DD
    newsletters      = Column(String)                    # comma-separated requested newsletters
    headlines_json   = Column(Text)                      # JSON array of headline dicts
    email_count      = Column(Integer, default=0)        # how many source emails were used
    created_at       = Column(DateTime, default=datetime.utcnow)


# ── user_data.db ───────────────────────────────────────────────
class ConnectorCredential(Base):
    """
    Stores credentials for different services (gmail, youtube).
    key: e.g. 'gmail_client_id', 'youtube_api_key'
    value: the actual secret or ID
    """
    __tablename__ = "connector_credentials"

    id         = Column(Integer, primary_key=True, index=True)
    service    = Column(String, index=True)  # 'gmail' or 'youtube'
    key_name   = Column(String, index=True)  # 'client_id', 'api_key', etc.
    value      = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ── source.db: linkedin_posts table ──────────────────────────
class LinkedInPost(Base):
    __tablename__ = "linkedin_posts"

    id         = Column(Integer, primary_key=True, index=True)
    username   = Column(String, index=True)
    url        = Column(String, unique=True, index=True)
    text       = Column(Text)
    likes      = Column(Integer)
    comments   = Column(Integer)
    posted_at  = Column(String)  # ISO string from API
    created_at = Column(DateTime, default=datetime.utcnow)

