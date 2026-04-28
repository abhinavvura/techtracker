"""Update Gmail credentials in the database."""
import os
from dotenv import load_dotenv
from database import UserDataSessionLocal
from models import ConnectorCredential

load_dotenv()

db = UserDataSessionLocal()

# Get credentials from .env
client_id = os.getenv("GMAIL_CLIENT_ID")
client_secret = os.getenv("GMAIL_CLIENT_SECRET")
refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")

print("Updating Gmail credentials in database...")

# Update or create each credential
for key_name, value in [
    ("client_id", client_id),
    ("client_secret", client_secret),
    ("refresh_token", refresh_token)
]:
    cred = db.query(ConnectorCredential).filter_by(
        service="gmail", 
        key_name=key_name
    ).first()
    
    if cred:
        old_value = cred.value[:30] + "..." if cred.value else "None"
        cred.value = value
        print(f"✓ Updated {key_name}")
        print(f"  Old: {old_value}")
        print(f"  New: {value[:30]}...")
    else:
        db.add(ConnectorCredential(
            service="gmail",
            key_name=key_name,
            value=value
        ))
        print(f"✓ Created {key_name}: {value[:30]}...")

db.commit()
db.close()
print("\n✓ All Gmail credentials updated in database!")
print("Please restart your MCP server for changes to take effect.")
