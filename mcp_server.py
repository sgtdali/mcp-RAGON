import asyncio
import json
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from ragon_core import search_organizational_memory

# 1. Initialize FastAPI App
app = FastAPI(title="RAGON MCP Server")

@app.get("/")
async def root():
    return {"status": "online", "message": "RAGON MCP Server is running"}

# 2. Create MCP Server Instance
server = Server("ragon-memory")

# 3. Define Tools
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
            # Perform the RAG search
            results = search_organizational_memory(query, deep_mode=True)
            
            # Format output
            output = {
                "summary": f"Found {len(results.get('results', []))} direct matches.",
                "matches": results.get('results', [])[:5], # Top 5 direct
                "deep_insights": results.get('deep_results', [])[:3] # Top 3 deep
            }
            
            # Return as TextContent
            return [TextContent(type="text", text=json.dumps(output, ensure_ascii=False, indent=2))]
        
        except Exception as e:
            return [TextContent(type="text", text=f"Error executing search: {str(e)}")]
    
    raise ValueError(f"Tool not found: {name}")

# 4. SSE Implementation
# We use a global variable to store the active transport for simplicity.
# In a robust production environment, you would map session IDs to transports.
_transport = None

@app.get("/sse")
async def handle_sse(request: Request):
    global _transport
    
    # Create the transport. "/messages" is the endpoint for client->server messages.
    _transport = SseServerTransport("/messages")
    
    async def event_generator():
        global _transport
        try:
            async with server.run_sse(_transport) as streams:
                async for message in streams:
                    # 'message' is typically a ServerSseMessage object with 'event' and 'data'
                    # We need to serialize the data field (often a JSON-RPC dict or model)
                    
                    event_type = message.event
                    
                    if hasattr(message.data, "model_dump_json"):
                        data = message.data.model_dump_json()
                    elif isinstance(message.data, (dict, list)):
                        data = json.dumps(message.data)
                    else:
                        data = str(message.data)
                    
                    # Construct SSE formatted message
                    yield f"event: {event_type}\ndata: {data}\n\n"
                    
        except asyncio.CancelledError:
            print("SSE connection cancelled")
        except Exception as e:
            print(f"SSE Error: {str(e)}")
            yield f"event: error\ndata: {str(e)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/messages")
async def handle_messages(request: Request):
    global _transport
    if not _transport:
        return Response(status_code=400, content="No active SSE connection")
    
    # SseServerTransport.handle_post_message expects standard ASGI (scope, receive, send)
    # Since we are inside FastAPI, we can pass these from the request.
    try:
        # We need to await the transport's handler
        # Note: request.receive constitutes consuming the body.
        await _transport.handle_post_message(request.scope, request.receive, request._send)
        return Response(status_code=202)
    except Exception as e:
        print(f"Message Handling Error: {e}")
        return Response(status_code=500, content=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
