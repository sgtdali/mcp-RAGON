import asyncio
import json
import httpx
import os
from dotenv import load_dotenv

# Konfigürasyon
SERVER_URL = "https://mcp-ragon.onrender.com"
SSE_ENDPOINT = f"{SERVER_URL}/sse"
POST_ENDPOINT = f"{SERVER_URL}/messages"

async def main():
    print(f"Connecting to {SSE_ENDPOINT}...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. SSE Bağlantısını Başlat
        async with client.stream("GET", SSE_ENDPOINT) as response:
            print("SSE Connected! Waiting for endpoint event...")

            # SSE Iterator oluştur
            lines = response.aiter_lines()
            
            # İlk event'i bekle (endpoint bildirimi)
            # MCP Protokolü gereği sunucu önce endpoint URL'sini bildirir.
            # Bizim kodumuzda bu '/messages' olacak ama beklemek "hazır" olduğundan emin olur.
            async for line in lines:
                if line.startswith("event: endpoint"):
                    # Bir sonraki satır data olmalı
                    continue
                if line.startswith("data: "):
                    print(f"Received initial event: {line}")
                    break
            
            print("Server ready. Starting handshake...")

            # 2. Initialize İsteği Gönder (JSON-RPC)
            init_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "manual-test", "version": "1.0"}
                }
            }
            
            print("\nSending Initialize...")
            r = await client.post(POST_ENDPOINT, json=init_payload)
            print(f"Init status: {r.status_code}")
            if r.status_code != 202 and r.status_code != 200:
                print(f"Init failed: {r.text}")
                return

            # 3. Initialized Notification
            max_payload = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            await client.post(POST_ENDPOINT, json=max_payload)

            # 4. Tool Listeleme
            list_tools_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list"
            }
            
            print("\nRequesting Tools List...")
            await client.post(POST_ENDPOINT, json=list_tools_payload)
            
            # 5. Arama Yapma (Test Query)
            query = "saha sorumlusu görevleri"
            call_tool_payload = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "search_knowledge_base",
                    "arguments": {"query": query}
                }
            }
            
            print(f"\nCalling Tool 'search_knowledge_base' with query: '{query}'...")
            await client.post(POST_ENDPOINT, json=call_tool_payload)

            print("\nListening for responses (Process will stop after receiving results)...")
            
            # Kalan eventleri oku
            async for line in lines:
                if line.startswith("data: "):
                    data_str = line[6:]
                    try:
                        data = json.loads(data_str)
                        
                        # JSON-RPC Response Kontrolü
                        if "result" in data:
                            if data.get("id") == 1:
                                print("\n[Server] Initialization Response Received.")
                            elif data.get("id") == 2:
                                print("\n[Server] Tools List:")
                                tools = data["result"].get("tools", [])
                                for t in tools:
                                    print(f" - {t['name']}: {t['description']}")
                            elif data.get("id") == 3:
                                print("\n[Server] Search Results:")
                                content = data["result"].get("content", [])
                                for item in content:
                                    text = item.get("text", "")
                                    # JSON string ise parse etip güzel gösterelim
                                    try:
                                        res_json = json.loads(text)
                                        print(json.dumps(res_json, indent=2, ensure_ascii=False))
                                    except:
                                        print(text)
                                break # Sonucu aldık, çıkabiliriz.
                        
                        if "error" in data:
                            print(f"\n[Error] {data['error']}")
                            
                    except json.JSONDecodeError:
                        pass
                        
if __name__ == "__main__":
    asyncio.run(main())
