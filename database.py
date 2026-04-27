"""
database.py — SQLAlchemy engine / session / Base definitions.

All databases live in the data/ folder:
  data/source.db        — All content: newsletters, YouTube transcripts, LinkedIn posts
  data/chat_history.db  — AI chat conversations
  data/daily_updates.db — daily headline snapshots (cache)
  data/user_data.db     — connector credentials (Gmail OAuth, YouTube API key)
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Ensure the data directory exists
os.makedirs("data", exist_ok=True)

Base = declarative_base()

# ── 1. Unified source database (newsletters + YouTube + LinkedIn) ──
source_engine      = create_engine("sqlite:///./data/source.db", connect_args={"check_same_thread": False})
SourceSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=source_engine)

# ── 2. Chat history database ────────────────────────────────────
chat_engine      = create_engine("sqlite:///./data/chat_history.db",  connect_args={"check_same_thread": False})
ChatSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=chat_engine)

# ── 3. Daily updates snapshot database ─────────────────────────
daily_engine      = create_engine("sqlite:///./data/daily_updates.db", connect_args={"check_same_thread": False})
DailySessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=daily_engine)

# ── 4. User data / connector credentials database ──────────────
user_data_engine      = create_engine("sqlite:///./data/user_data.db",    connect_args={"check_same_thread": False})
UserDataSessionLocal  = sessionmaker(autocommit=False, autoflush=False, bind=user_data_engine)
