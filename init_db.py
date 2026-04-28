"""
Initialize database tables.
Run this after deploying to Render to create all tables in PostgreSQL.
"""
from database import Base, engine
from models import (
    Newsletter,
    YouTubeTranscript,
    LinkedInPost,
    ChatMessage,
    DailyUpdate,
    ConnectorCredential
)

print("Creating all database tables...")
Base.metadata.create_all(bind=engine)
print("✓ All tables created successfully!")
