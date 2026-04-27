# TechTracker — Codebase Description

> **Purpose of this file:** Provides a complete overview of every file, function, class, route, and constant in the TechTracker project. Feed this to an AI agent so it understands the codebase **without** reading every source file — saving tokens and context window.

---

## 📂 Project Structure

```
TechTracker/
├── main.py               # FastAPI backend — agents, routes, helpers (1147 lines)
├── models.py             # SQLAlchemy ORM models for 4 databases (66 lines)
├── database.py           # SQLAlchemy engines, sessions, Base definition (34 lines)
├── gmail_helpers.py      # Gmail OAuth + email parsing + local DB search (262 lines)
├── youtube_helpers.py    # YouTube channel → transcript pipeline (156 lines)
├── lnkdn.py              # LinkdAPI LinkedIn post extractor helper
├── mcp_server.py         # FastMCP server — 2 live-fetch tools (81 lines)
├── pyproject.toml        # uv/pip project config, Python >=3.12
├── .env                  # API keys: GEMINI_API_KEY, TAVILY_API_KEY, MCP_SERVER_URL
├── frontend/
│   ├── index.html        # Single-page app UI
│   ├── style.css         # All styling
│   └── app.js            # Frontend JS logic
└── data/
    ├── local_gmail.db    # Emails + YouTube transcripts
    ├── chat_history.db   # Chat conversations
    ├── daily_updates.db  # Cached daily headline snapshots
    ├── user_data.db      # Connector credentials (Gmail OAuth, YouTube API key)
    └── lnkn.db           # LinkedIn posts data
```

---

## 🗄️ Tech Stack

| Layer        | Technology                                                     |
|--------------|----------------------------------------------------------------|
| Backend      | **FastAPI** (uvicorn)                                          |
| LLM          | **Gemini 2.5 Flash** via `google-generativeai` + `langchain-google-genai` |
| Agent Framework | **LangChain** (`langchain-classic` ReAct agents)            |
| MCP Server   | **FastMCP** (streamable-http transport, port 8002)             |
| Database     | **SQLite** (5 separate DBs via SQLAlchemy ORM)                 |
| Web Search   | **Tavily** (optional, graceful fallback if key missing)        |
| Email        | **Gmail API** (OAuth2 refresh-token flow)                      |
| YouTube      | **YouTube Data API v3** + **youtube-transcript-api** + **RSS** |
| Frontend     | Vanilla HTML/CSS/JS                                            |

---

## 📄 File: `database.py`

**Purpose:** Defines SQLAlchemy engines, session factories, and the shared `Base` for all four SQLite databases.

### Exports (all imported by other modules)

| Name                     | Type               | Description                                                  |
|--------------------------|--------------------|--------------------------------------------------------------|
| `Base`                   | `declarative_base` | Shared ORM base class used by all models in `models.py`      |
| `newsletter_engine`      | `Engine`           | Engine for `data/local_gmail.db`                             |
| `NewsletterSessionLocal` | `sessionmaker`     | Session factory for newsletter/email DB                      |
| `chat_engine`            | `Engine`           | Engine for `data/chat_history.db`                            |
| `ChatSessionLocal`       | `sessionmaker`     | Session factory for chat history DB                          |
| `daily_engine`           | `Engine`           | Engine for `data/daily_updates.db`                           |
| `DailySessionLocal`      | `sessionmaker`     | Session factory for daily updates cache DB                   |
| `user_data_engine`       | `Engine`           | Engine for `data/user_data.db`                               |
| `UserDataSessionLocal`   | `sessionmaker`     | Session factory for user credentials DB                      |

> Also creates `data/` directory on import if it doesn't exist.

---

## 📄 File: `models.py`

**Purpose:** SQLAlchemy ORM model classes for all four databases. All share the same `Base` from `database.py`.

### Class: `Email`
- **Table:** `emails` (in `local_gmail.db`)
- **Usage:** Stores raw Gmail newsletter emails AND YouTube transcripts
- **Columns:**

| Column          | Type       | Notes                                              |
|-----------------|------------|----------------------------------------------------|
| `message_id`    | String PK  | Gmail message ID, or `yt:{video_id}` for YouTube   |
| `subject`       | String     | Email subject or YouTube video title                |
| `sender`        | String     | Email sender or `YouTube: {channel_name}`           |
| `received_date` | DateTime   | When email was received / transcript fetched        |
| `raw_html`      | Text       | Original HTML body (None for YouTube)               |
| `clean_text`    | Text       | Cleaned plaintext body or YouTube transcript        |
| `summary`       | Text       | LLM-generated summary (nullable, generated lazily)  |
| `processed`     | Boolean    | Always True on insert                               |
| `created_at`    | DateTime   | Auto-set to utcnow                                 |

### Class: `ChatMessage`
- **Table:** `chat_messages` (in `chat_history.db`)
- **Usage:** Persists every chat interaction for history

| Column                 | Type       | Notes                    |
|------------------------|------------|--------------------------|
| `id`                   | Integer PK | Auto-increment           |
| `user_query`           | Text       | User's question          |
| `newsletters_followed` | Text       | Comma-separated names    |
| `agent_response`       | Text       | Full AI response         |
| `created_at`           | DateTime   | Auto-set                 |

### Class: `DailyUpdate`
- **Table:** `daily_updates` (in `daily_updates.db`)
- **Usage:** Caches headline extractions per date+newsletter combo to avoid re-running Gemini

| Column           | Type       | Notes                                    |
|------------------|------------|------------------------------------------|
| `id`             | Integer PK | Auto-increment                           |
| `date`           | String     | `YYYY-MM-DD`, indexed                    |
| `newsletters`    | String     | Comma-separated sorted lowercase names   |
| `headlines_json` | Text       | JSON array of `{title, description, source}` |
| `email_count`    | Integer    | How many source emails were used         |
| `created_at`     | DateTime   | Auto-set                                 |

### Class: `ConnectorCredential`
- **Table:** `connector_credentials` (in `user_data.db`)
- **Usage:** Stores OAuth/API credentials for Gmail and YouTube

| Column       | Type       | Notes                                         |
|--------------|------------|-----------------------------------------------|
| `id`         | Integer PK | Auto-increment                                |
| `service`    | String     | `'gmail'` or `'youtube'`, indexed             |
| `key_name`   | String     | e.g. `'client_id'`, `'api_key'`, indexed      |
| `value`      | Text       | The actual secret                             |
| `updated_at` | DateTime   | Auto-set, auto-updated on change              |

### Class: `LinkedInPost`
- **Table:** `linkedin_posts` (in `lnkn.db`)
- **Usage:** Stores extracted LinkedIn posts with metrics
- **Columns:**

| Column       | Type       | Notes                                         |
|--------------|------------|-----------------------------------------------|
| `id`         | Integer PK | Auto-increment                                |
| `username`   | String     | LinkedIn handle (e.g., satyanadella)          |
| `url`        | String     | LinkedIn post URL (unique)                    |
| `text`       | Text       | Post content                                  |
| `likes`      | Integer    | Number of likes                               |
| `comments`   | Integer    | Number of comments                            |
| `posted_at`  | String     | ISO datetime string                           |
| `created_at` | DateTime   | Auto-set to utcnow                            |

---

## 📄 File: `gmail_helpers.py`

**Purpose:** Gmail OAuth token exchange, email HTML parsing, and local DB search logic. Used by both `mcp_server.py` (live fetches) and `main.py` (DB searches).

### Functions

#### `get_credential(service: str, key_name: str) → Optional[str]`
- **What:** Fetches a credential value — first checks `user_data.db`, falls back to `.env` vars
- **Used by:** `get_access_token()`, `youtube_helpers.get_credential()` (imported)
- **Args:** `service` = `"gmail"` or `"youtube"`, `key_name` = e.g. `"client_id"`, `"refresh_token"`, `"api_key"`

#### `get_access_token() → str`
- **What:** Exchanges the stored Gmail OAuth refresh token for a fresh access token via Google's token endpoint
- **Used by:** `sync_newsletters()`
- **Raises:** `ValueError` if client_id, client_secret, or refresh_token missing

#### `decode_base64url(data: str) → str`
- **What:** Decodes a URL-safe base64 string (Gmail API format) to UTF-8 text
- **Used by:** `extract_html()`

#### `extract_html(payload: dict) → Optional[str]`
- **What:** Recursively walks a Gmail message payload to find and decode the first `text/html` MIME part
- **Used by:** `sync_newsletters()`
- **Args:** `payload` = the `payload` dict from a Gmail message response

#### `clean_html(html: str) → str`
- **What:** Strips HTML to readable plaintext. Removes `<script>`, `<style>`, images; preserves hyperlinks as `[URL]` inline; removes unsubscribe sections
- **Used by:** `sync_newsletters()`
- **Returns:** Clean plaintext with collapsed whitespace

#### `sync_newsletters(newsletter_names: str, target_date: str = None) → str`
- **What:** Fetches newsletters from Gmail API and saves new ones to `local_gmail.db`. Core sync pipeline.
- **Used by:** `mcp_server.py → fetch_gmail_newsletters` tool
- **Args:**
  - `newsletter_names`: comma-separated search terms (matched against Gmail subject/sender)
  - `target_date`: optional `YYYY-MM-DD` to scope Gmail query to a single day
- **Flow:** get access token → Gmail search API (max 20) → for each new message: fetch full detail → extract HTML → clean → save `Email` row
- **Returns:** Summary string like `"Synced 5 new newsletters. Found emails from: TLDR, AlphaSignal."`

#### `search_newsletters_db(query: str) → str`
- **What:** Searches `local_gmail.db` for newsletters matching query across `subject`, `summary`, `sender` fields. Used by the **Updates Agent**.
- **Used by:** `main.py → search_newsletters_db` LangChain tool
- **Args:** `query` = free-text search terms (noise words like "today", "summary" are stripped)
- **Returns:** Formatted list of up to 10 matches with message IDs, subjects, dates, senders, summaries (first 200 chars)

#### `search_gmail_db_for_context(query: str) → str`
- **What:** Searches `local_gmail.db` for newsletter content matching a query. Searches `clean_text`, `subject`, `summary`. Returns rich snippets with embedded URLs. Used by the **Chat Agent**.
- **Used by:** `main.py → search_gmail_db_for_context` LangChain tool
- **Args:** `query` = highlighted text or user question
- **Returns:** Up to 4 newsletter blocks, each with sender, subject, date, URLs found in content, and a 4000-char content snippet

---

## 📄 File: `youtube_helpers.py`

**Purpose:** YouTube channel resolution, video discovery, transcript fetching, and DB caching.

### Functions

#### `channel_label(url: str) → str`
- **What:** Extracts a human-readable channel name from a YouTube URL (handles `@handle`, `channel/UCxxx`, `user/xxx` formats)
- **Used by:** `fetch_channel_content()`

#### `get_channel_id(channel_url: str) → str`
- **What:** Resolves a YouTube channel URL to its `UC...` channel ID. First tries regex on the URL, then scrapes the page HTML for the ID.
- **Used by:** `fetch_channel_content()`
- **Raises:** `ValueError` if channel ID cannot be found

#### `get_latest_video_id(channel_id: str) → Optional[str]`
- **What:** Returns the latest non-Shorts video ID for a channel. Tries the YouTube Data API first (if `youtube.api_key` credential is stored), falls back to RSS feed.
- **Used by:** `fetch_channel_content()`
- **Returns:** Video ID string, or `None` if no suitable video found

#### `get_video_title(channel_id: str, video_id: str) → str`
- **What:** Looks up a video title from the channel's RSS feed
- **Used by:** `fetch_channel_content()`
- **Returns:** Video title, or `"YouTube video {video_id}"` as fallback

#### `get_transcript(video_id: str, max_chars: int = 8000) → str`
- **What:** Fetches the full transcript with timestamps using `youtube-transcript-api`
- **Used by:** `fetch_channel_content()`
- **Returns:** Timestamped transcript text like `"0s: Hello...\n5s: Today we..."`, truncated to `max_chars`

#### `fetch_channel_content(channel_url: str) → str`
- **What:** Full pipeline for one YouTube channel: resolve channel ID → find latest video → fetch transcript → store in `local_gmail.db` as an `Email` row (with `message_id = "yt:{video_id}"`)
- **Used by:** `mcp_server.py → fetch_youtube_content` tool
- **Returns:** Formatted string with channel name, video title, URL, and transcript (max 4000 chars)
- **Caching:** If transcript already in DB, returns cached version

---

## 📄 File: `mcp_server.py`

**Purpose:** FastMCP server exposing exactly 2 tools for live external data fetching. Runs on port 8002 with streamable-http transport. The main app (`main.py`) calls these tools via `_call_mcp_tool()`.

### MCP Tool: `fetch_gmail_newsletters`
- **Input:** `newsletter_names: str` — comma-separated names. Optionally append `|date:YYYY-MM-DD` to scope to a day (e.g. `"tldr,alphasignal|date:2026-04-09"`)
- **Delegates to:** `gmail_helpers.sync_newsletters()`
- **Returns:** Sync summary string

### MCP Tool: `fetch_youtube_content`
- **Input:** `channel_urls: str` — comma-separated YouTube channel URLs
- **Delegates to:** `youtube_helpers.fetch_channel_content()` for each URL
- **Returns:** Combined results separated by `─` dividers

### Entry Point
```bash
python mcp_server.py  # Starts on http://localhost:8002
```

---

## 📄 File: `main.py`

**Purpose:** Central FastAPI application — defines LLM setup, content helpers, LangChain agents, callback handler, and all HTTP routes.

### Section A: Imports & Logging
- Uses `TechTracker` logger with both file (`techtracker.log`) and console handlers
- Format: `%(asctime)s │ %(levelname)-5s │ %(message)s`

### Section B: App Setup & Config

#### Constants / Globals

| Name                 | Type/Value            | Description                                                |
|----------------------|-----------------------|------------------------------------------------------------|
| `INPUT_COST_PER_1K`  | `0.000075`            | Approx input token cost for Gemini 2.5 Flash               |
| `OUTPUT_COST_PER_1K` | `0.00030`             | Approx output token cost for Gemini 2.5 Flash              |
| `session_stats`      | `defaultdict`         | In-memory per-request token/cost tracking                  |
| `llm`                | `ChatGoogleGenerativeAI` | LangChain-wrapped Gemini model (temp=0)                |
| `direct_model`       | `GenerativeModel`     | Direct `google.generativeai` model for non-LangChain calls |
| `_tavily_client`     | `TavilyClient / None` | Web search client (None if key missing)                    |
| `MCP_SERVER_URL`     | `str`                 | Default `http://localhost:8002/mcp`                        |
| `chat_sessions`      | `defaultdict(list)`   | In-memory chat history `{session_id: [(user, ai), ...]}`   |
| `MAX_HISTORY_TURNS`  | `8`                   | Max conversation turns kept per session                    |
| `GREETINGS`          | `set`                 | Set of greeting strings for fast-path detection            |

#### `log_tokens(req_id: str, in_t: int, out_t: int) → None`
- **What:** Tracks token usage and estimated cost for a request ID. Updates `session_stats` and logs metrics.

#### `_call_mcp_tool(tool_name: str, arguments: dict) → str`
- **What:** Synchronous wrapper that calls a tool on the MCP server via `fastmcp.Client`. Runs in a dedicated thread with its own event loop to avoid conflicts with FastAPI's AnyIO loop.
- **Args:** `tool_name` = MCP tool name, `arguments` = dict of tool arguments
- **Returns:** Tool result as string, or error message
- **Timeout:** 60 seconds

---

### Section C: Content Helpers

#### `extract_urls_from_text(text: str) → list`
- **What:** Extracts up to 5 unique HTTP/HTTPS URLs from text using regex. Strips trailing punctuation.
- **Used by:** `chat_summarise` route (counting URLs in response)

#### `fetch_url_content_helper(url: str) → str`
- **What:** Direct HTTP GET to fetch and clean a webpage. Strips scripts/styles/nav/footer. Returns first 3000 chars of cleaned text.
- **Used by:** `tavily_search` fallback, `get_url_context` fallback

#### `query_emails_for_nl(db_session, nl_list: list, extra_filter=None, limit_each: int = 5) → list`
- **What:** Queries `Email` table for emails matching any newsletter name in `nl_list` (checks `sender` and `subject` with ILIKE). Applies optional extra SQLAlchemy filter. Deduplicates by `message_id`.
- **Used by:** `today_updates`, `calendar_updates` routes
- **Args:**
  - `db_session`: active SQLAlchemy session
  - `nl_list`: list of newsletter name strings
  - `extra_filter`: optional SQLAlchemy filter expression (e.g. date filter)
  - `limit_each`: max results per newsletter name (default 5)

#### `extract_headlines(content: str, newsletters: str, req_id: str = "global") → list`
- **What:** Calls Gemini directly to parse newsletter/YouTube content into structured headline dicts. Returns a JSON array of `{title, description, source}`.
- **Used by:** `today_updates`, `calendar_updates` routes
- **Args:**
  - `content`: combined newsletter text (max 100K chars sent to LLM)
  - `newsletters`: comma-separated source names (for attribution)
  - `req_id`: request ID for token tracking
- **Returns:** List of dicts, or `[]` on failure

#### `summarize_text(text: str) → str`
- **What:** Generates a structured markdown summary of newsletter text using Gemini directly
- **Used by:** `summarize_newsletter` tool

#### `format_chat_history(session_id: str) → str`
- **What:** Formats the last `MAX_HISTORY_TURNS` conversation turns as context string for the Chat Agent
- **Used by:** `chat_summarise` route
- **Returns:** Formatted string like `"=== Previous conversation ===\nUser: ...\nAssistant: ..."`

#### `save_to_history(session_id: str, user_msg: str, ai_msg: str) → None`
- **What:** Appends a `(user_msg, ai_msg)` turn to in-memory `chat_sessions` and trims to `MAX_HISTORY_TURNS`
- **Used by:** `chat_summarise` route

---

### Section D: Agent Callback Handler

#### Class: `TechTrackerCallbackHandler(BaseCallbackHandler)`
- **Purpose:** Structured logging for every agent step — thoughts, tool starts/ends, LLM calls, token usage extraction
- **Constructor Args:** `request_id: str = ""` — prefixed to all log lines
- **Methods:**

| Method              | Trigger                  | What it logs                                          |
|---------------------|--------------------------|-------------------------------------------------------|
| `on_agent_action`   | Agent selects a tool     | Step number, thought text, tool name, input preview    |
| `on_tool_start`     | Tool begins executing    | Tool name, "started"                                  |
| `on_tool_end`       | Tool finishes            | Tool name, SUCCESS/EMPTY status, data size, duration   |
| `on_tool_error`     | Tool throws exception    | Error message (first 150 chars)                       |
| `on_llm_start`      | LLM call begins          | Total prompt chars                                    |
| `on_llm_end`        | LLM call finishes        | Duration, extracts token counts, calls `log_tokens()` |
| `on_llm_error`      | LLM call fails           | Error message                                         |
| `on_agent_finish`   | Agent produces answer    | Total step count                                      |

#### `_log_step(tag: str, msg: str) → None`
- **What:** Helper for clean, aligned route-level structured logs

---

### Section E: LangChain Tools

These are `@tool`-decorated functions that the LangChain agents can invoke.

#### Tool: `fetch_and_sync_newsletters(newsletter_names: str) → str`
- **What:** Calls MCP `fetch_gmail_newsletters` tool to fetch live Gmail data and sync to `local_gmail.db`
- **Used by:** TechUpdates Agent
- **Input:** Comma-separated newsletter names

#### Tool: `search_newsletters_db(query: str) → str`
- **What:** Delegates to `gmail_helpers.search_newsletters_db()` — searches local DB
- **Used by:** TechUpdates Agent

#### Tool: `summarize_newsletter(message_id: str) → str`
- **What:** Summarizes a specific newsletter by message ID. Checks for existing summary first; if not, generates via `summarize_text()` and caches in DB.
- **Used by:** TechUpdates Agent

#### Tool: `search_gmail_db_for_context(query: str) → str`
- **What:** Delegates to `gmail_helpers.search_gmail_db_for_context()` — searches local DB for rich context
- **Used by:** Chat Agent (always called FIRST)

#### Tool: `tavily_search(query: str) → str`
- **What:** Web search via Tavily. If input is URL, uses `extract`; otherwise uses `search` (max 3 results). Falls back to `fetch_url_content_helper` if Tavily disabled.
- **Used by:** Chat Agent (called AFTER local DB search if needed)

#### Tool: `get_url_context(url: str) → str`
- **What:** Fetches full text content of a webpage using LangChain's `WebBaseLoader` (or direct fetch fallback). Returns up to 4000 chars.
- **Used by:** Chat Agent (for following URLs found in newsletters)

#### Tool: `fetch_youtube_content(channel_urls: str) → str`
- **What:** Calls MCP `fetch_youtube_content` tool to fetch live YouTube transcripts
- **Used by:** TechUpdates Agent
- **Input:** Comma-separated YouTube channel URLs

---

### Section F: Agents

#### Agent 1: TechUpdates Agent (`techupdates_agent_executor`)
- **Type:** LangChain ReAct agent
- **LLM:** Gemini 2.5 Flash (temp=0)
- **Tools:** `search_newsletters_db`, `fetch_and_sync_newsletters`, `summarize_newsletter`, `fetch_youtube_content`
- **Max iterations:** 12
- **Purpose:** Curates tech briefings from newsletters AND YouTube channels
- **Output format:** Structured markdown with `📰 Newsletter Highlights`, `▶️ YouTube Insights`, `🔥 Most Notable`, `💡 Key Takeaway` sections

#### Agent 2: Chat Agent (`chat_executor`)
- **Type:** LangChain ReAct agent
- **LLM:** Gemini 2.5 Flash (temp=0)
- **Tools:** `search_gmail_db_for_context`, `get_url_context`, `tavily_search`
- **Max iterations:** 15
- **Purpose:** Deep-dive on highlighted text or follow-up questions with conversation memory
- **Execution order:** (1) always search local DB first → (2) follow URLs if found → (3) Tavily web search if still missing info
- **Output format:** Starts with `🔍 Deep Dive: [Topic]`, ends with `🔗 References` section

---

### Section G: Routes (HTTP API)

#### `GET /` — Root
- **Returns:** Service info, list of agents, databases, and endpoints

#### `GET /get_updates`
- **Query params:**
  - `query` (required): user's question/topic
  - `newsletters` (required): comma-separated newsletter names
  - `yt_channels` (optional): comma-separated YouTube channel URLs
- **Flow:** Runs the TechUpdates Agent with the query → saves response to `chat_history.db`
- **Returns:** `{query, newsletters_followed, response, usage}`

#### `GET /today_updates`
- **Query params:**
  - `newsletters` (required): comma-separated newsletter names
  - `days` (optional, default=7): fallback window in days
  - `force` (optional, default=false): skip cache & DB, go straight to Gmail sync
  - `yt_channels` (optional): comma-separated YouTube channel URLs
  - `linkedin_profiles` (optional): comma-separated LinkedIn profile handles
- **Flow (normal, 5 steps):**
  1. Check `daily_updates.db` cache for today → return if HIT
  2. Check `local_gmail.db` for today's emails
  3. Gmail sync via MCP if no emails found
  4. Fallback to last N days if still nothing
  5. Run `extract_headlines()` via Gemini on combined content + optional YouTube transcripts → cache result
- **Flow (force):** Skip steps 1-2, go directly to Gmail sync, then extract
- **Returns:** `{headlines[], newsletters[], count, is_today, source, message, generated_at, usage}`

#### `GET /available_dates`
- **Query params:** `newsletters` (required)
- **What:** Returns all dates that have cached headlines in `daily_updates.db`
- **Returns:** `{dates[], count}`

#### `GET /calendar_updates`
- **Query params:**
  - `date` (required): `YYYY-MM-DD`
  - `newsletters` (required): comma-separated names
  - `yt_channels` (optional): comma-separated YouTube channel URLs
- **Flow (4 steps):**
  1. Check `daily_updates.db` cache → return if HIT
  2. Check `local_gmail.db` for that date
  3. Gmail sync via MCP (only if date within last 30 days)
  4. `extract_headlines()` via Gemini → cache result
- **Returns:** `{headlines[], date, newsletters[], count, source, usage}`

#### `GET /chat_summarise`
- **Query params:**
  - `text` (required): user question or highlighted text
  - `newsletters` (required): comma-separated names
  - `session_id` (optional, default="default"): session ID for conversation memory
- **Fast-path:** If input matches a greeting (from `GREETINGS` set), returns a canned welcome message without invoking the agent
- **Normal flow:** Builds agent input with conversation history → runs Chat Agent → saves to memory + `chat_history.db`
- **Returns:** `{user_text, summary, sources_count, urls_fetched, usage}`

#### `GET /chat_history`
- **Query params:** `limit` (optional, default=20)
- **Returns:** Last N chat messages from `chat_history.db`, newest first

#### `POST /save_credentials`
- **Body:** `{service: str, credentials: {key: value, ...}}`
- **What:** Upserts connector credentials to `user_data.db`. Used for Gmail OAuth creds, YouTube API key, etc.
- **Returns:** `{status, message}`

#### `GET /get_credentials`
- **Query params:** `service` (required): e.g. `"gmail"`, `"youtube"`
- **Returns:** Dict of `{key_name: value}` for the service

---

## 📄 File: `lnkdn.py`

**Purpose:** Integrated helper for fetching real-time LinkedIn posts from specific profiles using LinkdAPI. Saves posts to `lnkn.db` via `fetch_posts()` when requested by `/today_updates`.

### Auth
- Uses `LINKDAPI_KEY` provided internally by LinkdAPI service.

### Functions

#### `fetch_posts(username: str) → List[Dict]`
- **What:** Uses LinkdAPI username-to-urn and then fetches the most recent posts. Extract likes, comments, date, text, and url.
- **Args:** `username` (e.g., `'satyanadella'`)
- **Returns:** List of post dicts.

---

## 🔗 Data Flow Diagram

```
User (Frontend)
    │
    ├─ /today_updates ──► main.py ──► [Cache Check] ──► [DB Check] ──► [MCP: Gmail Sync] ──► [Gemini: Extract Headlines]
    ├─ /calendar_updates ──► main.py ──► [Cache] ──► [DB] ──► [MCP: Gmail + YouTube] ──► [Gemini]
    ├─ /get_updates ──► main.py ──► TechUpdates Agent (LangChain ReAct) ──► Tools ──► Gemini
    ├─ /chat_summarise ──► main.py ──► Chat Agent (LangChain ReAct) ──► Tools ──► Gemini
    │
    └─ MCP Server (port 8002)
         ├─ fetch_gmail_newsletters ──► gmail_helpers.sync_newsletters() ──► Gmail API
         └─ fetch_youtube_content ──► youtube_helpers.fetch_channel_content() ──► YouTube API + Transcript API
```

---

## 🔑 Environment Variables (.env)

| Variable           | Required | Description                             |
|--------------------|----------|-----------------------------------------|
| `GEMINI_API_KEY`   | Yes      | Google Gemini API key                   |
| `TAVILY_API_KEY`   | No       | Tavily web search API key (optional)    |
| `MCP_SERVER_URL`   | No       | MCP server URL (default: `http://localhost:8002/mcp`) |
| `GMAIL_CLIENT_ID`  | Yes*     | Gmail OAuth client ID (* or in user_data.db)  |
| `GMAIL_CLIENT_SECRET` | Yes*  | Gmail OAuth client secret                     |
| `GMAIL_REFRESH_TOKEN` | Yes*  | Gmail OAuth refresh token                     |

---

## 🚀 How to Run

```bash
# Terminal 1: Start MCP Server
python mcp_server.py   # → http://localhost:8002

# Terminal 2: Start FastAPI Backend
uvicorn main:app --reload --port 8000

# Frontend: Open frontend/index.html in browser
```
