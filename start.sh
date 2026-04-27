#!/bin/bash
# Start MCP server in background
python mcp_server.py &

# Start FastAPI (Render injects $PORT)
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
