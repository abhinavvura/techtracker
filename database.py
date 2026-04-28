"""
database.py — SQLAlchemy engine / session / Base definitions.

For local development: uses SQLite databases in data/ folder
For production (Render): uses PostgreSQL via DATABASE_URL environment variable

All tables are in a single database:
  - newsletters, youtube_transcripts, linkedin_posts (content)
  - chat_messages (AI conversations)
  - daily_updates (headline snapshots/cache)
  - connector_credentials (Gmail OAuth, YouTube API key)
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

# Get database URL from environment or use SQLite for local dev
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Production: PostgreSQL on Render
    # Render provides postgres:// but SQLAlchemy needs postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    # Single PostgreSQL database for all tables
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    
    # All session makers point to the same PostgreSQL database
    SourceSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    ChatSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    DailySessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    UserDataSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
else:
    # Local development: SQLite databases in data/ folder
    os.makedirs("data", exist_ok=True)
    
    # ── 1. Unified source database (newsletters + YouTube + LinkedIn) ──
    source_engine = create_engine("sqlite:///./data/source.db", connect_args={"check_same_thread": False})
    SourceSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=source_engine)
    
    # ── 2. Chat history database ────────────────────────────────────
    chat_engine = create_engine("sqlite:///./data/chat_history.db", connect_args={"check_same_thread": False})
    ChatSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=chat_engine)
    
    # ── 3. Daily updates snapshot database ─────────────────────────
    daily_engine = create_engine("sqlite:///./data/daily_updates.db", connect_args={"check_same_thread": False})
    DailySessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=daily_engine)
    
    # ── 4. User data / connector credentials database ──────────────
    user_data_engine = create_engine("sqlite:///./data/user_data.db", connect_args={"check_same_thread": False})
    UserDataSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=user_data_engine)
    
    engine = source_engine  # For create_all() compatibility
