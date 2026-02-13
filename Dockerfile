FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ragon_core.py .
COPY mcp_server.py .
COPY rag_config.json .

# Expose port (Render/Fly usually use 8080 or 8000)
# But MCP usually runs over stdio or SSE. For cloud, we need SSE.
# FastMCP handles execution command, but for Docker deployment usually we serve it via HTTP if using SSE adapter
# Note: FastMCP default run() uses stdio. For HTTP, we need explicit run config.
# However, standard MCP cloud deployment often involves wrapping it in a web server.
# FastMCP has built-in SSE capabilities if run properly or we can just use the script.

CMD ["python", "mcp_server.py"]
