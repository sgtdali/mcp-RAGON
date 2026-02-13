# RAGON MCP Server

This is the Model Context Protocol (MCP) server for the Organizational RAG System.
It exposes the "search_knowledge_base" tool to AI agents (Claude, Cursor, etc.).

## 🚀 Deployment (Cloud)

This server is ready to be deployed on platforms like **Render**, **Railway**, or **Fly.io**.

### 1. Environment Variables
You MUST set the following environment variables in your cloud provider's dashboard:

*   `SUPABASE_URL`: Your Supabase Project URL.
*   `SUPABASE_SERVICE_ROLE_KEY`: Your Supabase Service Role Key (Required for db access).
*   `OPENAI_API_KEY`: Your OpenAI API Key (for embeddings).

### 2. Docker Deployment
The included `Dockerfile` builds a Python 3.11 environment with all dependencies.
Build command: `docker build -t ragon-mcp .`

### 3. Local Cursor Usage
To use this locally in Cursor without deploying:

1.  Make sure you are in this directory (`ragon_mcp_server`).
2.  Install dependencies: `pip install -r requirements.txt`
3.  Add to Cursor Settings -> MCP:
    *   **Name:** RAGON
    *   **Type:** command
    *   **Command:** `python c:/absolute/path/to/ragon_mcp_server/mcp_server.py`

## 🛠 Project Structure
*   `mcp_server.py`: The entry point defining the MCP Tool.
*   `ragon_core.py`: The core RAG logic (Search, Embedding, Graph Deep Search).
*   `rag_config.json`: Configuration for search weights.
