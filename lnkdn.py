"""
LinkedIn Posts Fetcher - Simple Python Version
Fetch posts from LinkedIn profiles and export to CSV/JSON
No dependencies needed!
"""

import urllib.request
import json
import csv
import sys
from datetime import datetime

# Fix for windows console printing
sys.stdout.reconfigure(encoding='utf-8')

# ============================================================================
# CONFIGURATION - CHANGE THESE!
# ============================================================================

LINKDAPI_KEY = 'li-3N4fAaNECd24ne3LqEFMGYPbnqxLPplO7V0a5ZhvEy-Em9VXO1WWdoqDSprF1yJFgLyO7MsYFsK8wRAj1NxHCjYw8Gz_WQ'  # Get from https://linkdapi.com

PEOPLE_TO_TRACK = [
           # Microsoft CEO
    'kalyanksnlp'      # Apple CEO
]

POSTS_LIMIT = 5  # Number of posts per person

# ============================================================================
# FETCH POSTS FROM LINKEDIN
# ============================================================================

def fetch_posts(username):
    """Fetch posts from a LinkedIn profile using LinkdAPI"""
    print(f"\n[*] Fetching posts from: {username}")
    
    headers = {
        'X-linkdapi-apikey': LINKDAPI_KEY,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    
    try:
        # Step 1: Get the URN from the username
        urn_url = f"https://linkdapi.com/api/v1/profile/username-to-urn?username={username}"
        urn_req = urllib.request.Request(urn_url, headers=headers)
        
        with urllib.request.urlopen(urn_req) as response:
            urn_data = json.loads(response.read().decode())
            
        temp_urn = urn_data.get('data', '')
        # Depending on API response structure, it might be nested
        if isinstance(temp_urn, dict):
            temp_urn = temp_urn.get('urn', '')
            
        profile_urn = temp_urn
            
        if not profile_urn:
            print(f"   [!] Could not resolve username to URN")
            return []
            
        # Step 2: Get posts using the URN
        posts_url = f"https://linkdapi.com/api/v1/posts/all?urn={profile_urn}"
        posts_req = urllib.request.Request(posts_url, headers=headers)
        
        with urllib.request.urlopen(posts_req) as response:
            posts_resp = json.loads(response.read().decode())
        
        # Check if successful
        if not posts_resp.get('success'):
            print(f"   [!] No posts found")
            return []
        
        # Get posts
        posts_data = posts_resp.get('data', [])
        if not isinstance(posts_data, list):
            posts_data = posts_data.get('posts', [])
            if not posts_data:  # If data is a dict and has 'items' or similar
                 posts_data = posts_resp.get('data', {}).get('elements', [])
        
        posts_data = posts_data[:POSTS_LIMIT]
        print(f"   [+] Found {len(posts_data)} posts")
        
        # Format posts
        posts = []
        for post in posts_data:
            posts.append({
                'username': username,
                'text': post.get('text', ''),
                'url': post.get('url', ''),
                'likes': post.get('engagements', {}).get('totalReactions', 0),
                'comments': post.get('engagements', {}).get('commentsCount', 0),
                'posted': post.get('postedAt', datetime.now().isoformat()),
            })
        
        return posts
    
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode()
        print(f"   [-] HTTP Error {e.code}: {e.reason}")
        print(f"      Response from server: {error_msg}")
        return []
    except Exception as e:
        print(f"   [-] Error: {str(e)}")
        return []

def save_to_json(posts, filename='posts.json'):
    """Save posts to JSON file"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(posts, f, indent=2, ensure_ascii=False)
        print(f"\n[+] Saved {len(posts)} posts to {filename}")
    except Exception as e:
        print(f"[-] Error saving JSON: {e}")


def save_to_csv(posts, filename='posts.csv'):
    """Save posts to CSV file"""
    try:
        if not posts:
            print("No posts to export")
            return
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['username', 'posted', 'text', 'url', 'likes', 'comments'])
            writer.writeheader()
            writer.writerows(posts)
        
        print(f"[+] Exported {len(posts)} posts to {filename}")
    except Exception as e:
        print(f"[-] Error saving CSV: {e}")


def main():
    """Main execution"""
    print("-" * 40)
    print("  LinkedIn Posts Fetcher - Python")
    print("-" * 40)
    
    # Check API key
    if LINKDAPI_KEY == 'YOUR_LINKDAPI_KEY_HERE':
        print("\n[-] ERROR: Set LINKDAPI_KEY in this file!")
        print("📍 Get key at: https://linkdapi.com")
        return
    
    # Fetch posts from all people
    all_posts = []
    
    for username in PEOPLE_TO_TRACK:
        posts = fetch_posts(username)
        all_posts.extend(posts)
    
    if not all_posts:
        print("\n[-] No posts fetched. Check usernames and API key.")
        return
    
    # Save results
    save_to_json(all_posts)
    save_to_csv(all_posts)
    
    # Print summary
    print("\n" + "="*40)
    print(f"[+] SUCCESS! Fetched {len(all_posts)} posts")
    print("="*40)
    print("  Saved to: posts.json")
    print("  CSV export: posts.csv")
    print("\n[!] Next: Import posts.csv to Google Sheets")
    print("="*40)


if __name__ == '__main__':
    main()