import asyncio
import json
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from ragon_core import search_organizational_memory

# 1. Initialize FastAPI App
app = FastAPI(title="RAGON MCP Server - Manual Implementation")

@app.get("/")
async def root():
    return {"status": "online", "message": "RAGON MCP Server is running (Manual Mode)"}

# 2. Global Event Helper
# Store client queues: session_id -> asyncio.Queue
CLIENT_QUEUES = {}

@app.get("/sse")
async def handle_sse(request: Request):
    """
    Establish SSE connection.
    Generate a session ID and yield events from the corresponding queue.
    """
    import uuid
    session_id = str(uuid.uuid4())
    queue = asyncio.Queue()
    CLIENT_QUEUES[session_id] = queue
    
    async def event_generator():
        try:
            # 1. Send Endpoint Event (Standard MCP)
            # Client should POST messages to /messages?session_id=...
            # Or simplified: we use a global endpoint, but client needs to know where to send.
            
            # The MCP spec says the first event should be the endpoint for posting messages.
            # Let's say it's relative "/messages".
            # We can also handle session via query param in POST url.
            
            endpoint_url = f"/messages?session_id={session_id}"
            yield f"event: endpoint\ndata: {endpoint_url}\n\n"
            
            # 2. Listen to Queue
            while True:
                # Wait for messages intended for this client
                data = await queue.get()
                if data is None: break # Shutdown signal
                
                # Yield as message event
                yield f"event: message\ndata: {json.dumps(data)}\n\n"
                
        except asyncio.CancelledError:
            print(f"Client {session_id} disconnected.")
        finally:
            CLIENT_QUEUES.pop(session_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/messages")
async def handle_messages(request: Request):
    """
    Handle JSON-RPC requests from the client.
    """
    session_id = request.query_params.get("session_id")
    
    if not session_id or session_id not in CLIENT_QUEUES:
        return Response(status_code=400, content="Invalid or missing session_id")
    
    try:
        payload = await request.json()
    except Exception:
        return Response(status_code=400, content="Invalid JSON")
    
    # Process JSON-RPC Request
    # We spawn a task so we don't block the HTTP response (202 Accepted)
    asyncio.create_task(process_rpc_request(session_id, payload))
    
    return Response(status_code=202)

async def process_rpc_request(session_id, request):
    """
    Manual JSON-RPC Processor
    """
    queue = CLIENT_QUEUES.get(session_id)
    if not queue: return
    
    rpc_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})
    
    response = None
    
    if method == "initialize":
        response = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "protocolVersion": "2024-11-05", # Latest known spec date
                "capabilities": {
                    "tools": {} # We support tools
                },
                "serverInfo": {
                    "name": "ragon-manual",
                    "version": "1.0.0"
                }
            }
        }
    
    elif method == "notifications/initialized":
        # No response needed for notifications
        pass

    elif method == "tools/list":
        response = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "tools": [
                    {
                        "name": "search_knowledge_base",
                        "description": "Search organizational policies, job descriptions and authority limits.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query"
                                }
                            },
                            "required": ["query"]
                        }
                    }
                ]
            }
        }
        
    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})
        
        if tool_name == "search_knowledge_base":
            try:
                query = args.get("query")
                # Perform Search
                results = search_organizational_memory(query, deep_mode=True)
                
                output_data = {
                    "summary": f"Found {len(results.get('results', []))} direct matches.",
                    "matches": results.get('results', [])[:5],
                    "deep_insights": results.get('deep_results', [])[:3]
                }
                
                content_text = json.dumps(output_data, ensure_ascii=False, indent=2)
                
                response = {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": content_text
                            }
                        ],
                        "isError": False
                    }
                }
            except Exception as e:
                response = {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error: {str(e)}"
                            }
                        ],
                        "isError": True
                    }
                }
        else:
            # Unknown Tool
            response = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32601,
                    "message": f"Method {tool_name} not found"
                }
            }
            
    elif method == "ping":
        response = {"jsonrpc": "2.0", "id": rpc_id, "result": {}}
        
    else:
        # Unknown Method
        if rpc_id is not None: # Only respond if it's a request, not a notification
             response = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32601,
                    "message": f"Method {method} not found"
                }
            }
            
    # Send response back to queue
    if response:
        await queue.put(response)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
