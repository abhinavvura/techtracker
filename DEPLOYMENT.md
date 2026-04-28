# TechTracker Deployment Guide

## Local Development (SQLite)
Your app automatically uses SQLite when `DATABASE_URL` is not set. No changes needed for local dev.

## Deploying to Render (PostgreSQL)

### Step 1: Push to GitHub
```bash
git add .
git commit -m "Add PostgreSQL support for Render deployment"
git push origin main
```

### Step 2: Create Render Account
1. Go to https://render.com
2. Sign up with GitHub

### Step 3: Deploy from Dashboard
1. Click "New +" → "Blueprint"
2. Connect your GitHub repository
3. Render will detect `render.yaml` and create:
   - Web Service (techtracker)
   - PostgreSQL Database (techtracker-db) - **FREE for 90 days**

### Step 4: Set Environment Variables
In the Render dashboard, go to your web service and add these environment variables:
- `GEMINI_API_KEY`
- `TAVILY_API_KEY`
- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `GMAIL_REFRESH_TOKEN`
- `LINKEDIN_EMAIL`
- `LINKEDIN_PASSWORD`
- `LINKEDIN_LI_AT`
- `LINKEDIN_JSESSIONID`
- `LINKEDIN_ACCESS_TOKEN`

**Note:** `DATABASE_URL` is automatically set by Render when you link the database.

### Step 5: Deploy
Render will automatically:
1. Install dependencies from `requirements.txt`
2. Run `init_db.py` to create all tables
3. Start your application with `start.sh`

### Important Notes

**Free PostgreSQL Limitations:**
- ✓ 1GB storage
- ✓ Free for 90 days
- ✗ Expires after 90 days (need to create new one or upgrade)

**After 90 Days:**
- Upgrade to paid plan ($7/month for Starter)
- Or create a new free database and migrate data

**Database Persistence:**
- All your SQLite data stays local
- PostgreSQL on Render is separate
- You'll need to re-sync newsletters/YouTube data after deployment

## Testing Locally with PostgreSQL

If you want to test PostgreSQL locally before deploying:

1. Install PostgreSQL locally
2. Create a database: `createdb techtracker`
3. Set environment variable:
   ```bash
   export DATABASE_URL=postgresql://localhost/techtracker
   ```
4. Run: `python init_db.py`
5. Start your app normally

## Troubleshooting

**Build fails with "psycopg2" error:**
- This is normal, `psycopg2-binary` should work
- If issues persist, try adding `pg_config` to build command

**Tables not created:**
- Check Render logs for `init_db.py` output
- Manually run: `python init_db.py` from Render shell

**Connection errors:**
- Verify `DATABASE_URL` is set in Render dashboard
- Check PostgreSQL database is running
