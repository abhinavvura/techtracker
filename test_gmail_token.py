"""Test Gmail token refresh to diagnose the issue."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = "https://oauth2.googleapis.com/token"

client_id = os.getenv("GMAIL_CLIENT_ID")
client_secret = os.getenv("GMAIL_CLIENT_SECRET")
refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")

print("Testing Gmail OAuth token refresh...")
print(f"Client ID: {client_id[:20]}...")
print(f"Client Secret: {client_secret[:20]}...")
print(f"Refresh Token: {refresh_token[:30]}...")
print()

try:
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        },
        timeout=10,
    )
    
    print(f"Response Status: {resp.status_code}")
    print(f"Response Body: {resp.text}")
    print()
    
    if resp.status_code == 200:
        data = resp.json()
        print("✓ SUCCESS! Token refresh worked.")
        print(f"Access Token: {data.get('access_token', '')[:50]}...")
        print(f"Expires In: {data.get('expires_in')} seconds")
    else:
        print("✗ FAILED! Token refresh failed.")
        error_data = resp.json()
        print(f"Error: {error_data.get('error')}")
        print(f"Description: {error_data.get('error_description')}")
        
except Exception as e:
    print(f"✗ EXCEPTION: {e}")
