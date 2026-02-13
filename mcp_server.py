import asyncio
import json
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent, EmbeddedResource, ImageContent
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import Response
from ragon_core import search_organizational_memory
import uvicorn

# 1. Create MCI Server Instance
server = Server("ragon-memory")

# 2. Define Tools
@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="search_knowledge_base",
            description="Search organizational policies, job descriptions and authority limits.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (supports '||' for multi-query)"
                    }
                },
                "required": ["query"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name, arguments):
    if name == "search_knowledge_base":
        query = arguments.get("query")
        try:
            results = search_organizational_memory(query, deep_mode=True)
            
            output = {
                "summary": f"Found {len(results['results'])} direct matches.",
                "matches": results['results'][:5], # Top 5 direct
                "deep_insights": results['deep_results'][:3] # Top 3 deep
            }
            
            return [TextContent(type="text", text=json.dumps(output, ensure_ascii=False, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    raise ValueError(f"Tool not found: {name}")

# 3. Create SSE Endpoint for Render
async def handle_sse(request):
    async with SseServerTransport("/messages") as transport:
        async with server.run_sse(transport) as streams:
            async for message in streams:
                # In a real ASGI app we need to handle the request/response cycle for SSE
                # This simple example might need a full SSE library wrapper.
                pass
    return Response("SSE Connection Closed")

# --- SIMPLIFIED STARLETTE APP FOR RENDER ---
# We use the official 'mcp' library's SSE transport helper if available, 
# or we just expose a basic HTTP endpoint that implements the protocol.

from mcp.server.starlette import SseServer

sse = SseServer(server, "/sse")

async def root(request):
    return Response("RAGON MCP Server is Running! Connect via SSE at /sse")

# The Starlette App
app = Starlette(
    debug=True,
    routes=[
        Route("/", root),
        Route("/sse", endpoint=sse.handle_sse),
        Route("/messages", endpoint=sse.handle_messages, methods=["POST"])
    ]
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
