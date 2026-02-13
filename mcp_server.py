from mcp.server.fastmcp import FastMCP
from ragon_core import search_organizational_memory
import json

# Initialize MCP Server
mcp = FastMCP("RAGON Organizational Memory")

@mcp.tool()
def search_knowledge_base(query: str) -> str:
    """
    Search the organizational knowledge base (RAG System) for policies, job descriptions, 
    processes, and authority limits.
    
    This tool performs a hybrid search (semantic + keywords) and automatically checks 
    referenced documents (Graph Search) for deep context.
    
    Args:
        query: The question or topic to search for. You can use '||' to separate multiple 
               sub-queries (e.g. "Budget Limit || Field Authority").
    
    Returns:
        JSON string containing direct search results and deep search findings.
    """
    try:
        results = search_organizational_memory(query, deep_mode=True)
        
        # Format for AI consumption (minimize tokens but keep structure)
        output = {
            "summary": f"Found {len(results['results'])} direct results and {len(results['deep_results'])} referenced deep insights.",
            "direct_matches": [
                {
                    "source": r['source'],
                    "content": r['content'][:800], # Trucate slightly to save tokens
                    "references": r['references']
                } for r in results['results']
            ],
            "deep_insights": [
                {
                    "source": r['source'],
                    "content": r['content'][:600],
                    "relevance_score": r['score']
                } for r in results['deep_results']
            ]
        }
        
        return json.dumps(output, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"error": str(e)})

if __name__ == "__main__":
    mcp.run()
