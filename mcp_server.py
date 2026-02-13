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

@app.get("/debug")
async def debug():
    import mcp.server
    from mcp.server.sse import SseServerTransport
    return {
        "server_attrs": dir(mcp.server.Server),
        "transport_attrs": dir(SseServerTransport)
    }

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
            # Connect the transport streams to the server's run loop
            # SseServerTransport provides read_stream and write_stream directly compatible with server.run
            # Note: server.run is a blocking call that runs the MCP protocol loop
            
            await server.run(
                _transport.read_stream,
                _transport.write_stream,
                server.create_initialization_options()
            )
                    
        except asyncio.CancelledError:
            print("SSE connection cancelled")
        except Exception as e:
            print(f"SSE Error: {str(e)}")
            yield f"event: error\ndata: {str(e)}\n\n"

    # The SseServerTransport writes to its internal buffer. 
    # We need to yield these messages to the HTTP client.
    # However, SseServerTransport isn't designed to be iterated directly like 'async for message in streams'.
    # It seems we need a different approach for manual SSE with mcp library.
    
    # Correction: The standard mcp.server.sse.SseServerTransport in Python SDK 
    # usually handles the SSE response generation itself via starlette/fastapi integration.
    # Since we are doing it MANUALLY, we should hook into the initialization.
    
    # Let's revert to a simpler method: Iterate the simple messages if strict valid server.run isn't easy.
    # BUT, 'server.run' is THE way to start the server logic.
    
    # We need to bridge the output of the transport to the generator.
    # Let's use the valid approach for manual integration:
    
    async def output_bridge():
        # Yield the endpoint event first.
        # SseServerTransport usually prepares this.
        # We can construct it manually if needed, but let's see if we can read from the transport's output.
        pass

    return StreamingResponse(_transport.sse_response_stream(), media_type="text/event-stream")

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
