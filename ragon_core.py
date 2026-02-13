import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI
from typing import List, Dict, Any, Optional

# Load env vars (support both local .env and system envs)
load_dotenv()

# Global Client Instances
supabase: Optional[Client] = None
openai_client: Optional[OpenAI] = None
RAG_CONFIG: Dict = {}

def init_clients():
    """Initialize Supabase and OpenAI clients if not already initialized."""
    global supabase, openai_client, RAG_CONFIG
    
    if supabase is not None and openai_client is not None:
        return

    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variables.")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    # Load Config
    config_path = os.path.join(os.path.dirname(__file__), 'rag_config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            RAG_CONFIG = json.load(f)
    except Exception:
        # Default config if file is missing
        RAG_CONFIG = {
            "folder_weights": {},
            "search_params": {"base_match_count": 8, "full_text_weight": 1.0, "semantic_weight": 1.0, "recency_weight": 0.5}
        }

def get_embedding(text: str) -> List[float]:
    """Generate embedding for query text."""
    if openai_client is None:
        init_clients()
    text = text.replace("\n", " ")
    return openai_client.embeddings.create(input=[text], model="text-embedding-3-small").data[0].embedding

def search_organizational_memory(query_text: str, deep_mode: bool = True) -> Dict[str, Any]:
    """
    Core RAG search logic.
    Returns a dictionary with results instead of printing to stdout.
    """
    init_clients()
    
    search_params = RAG_CONFIG.get("search_params", {})
    folder_weights = RAG_CONFIG.get("folder_weights", {})
    base_match_count = search_params.get("base_match_count", 8)

    # 1. Multi-Query Analysis
    sub_queries = [q.strip() for q in query_text.split("||") if q.strip()]
    is_multi_query = len(sub_queries) > 1
    
    current_limit = base_match_count if not is_multi_query else max(4, int(base_match_count * 0.6))
    
    all_results = []
    response_log = [] # To capture process logs if needed

    # 2. Search for each sub-query
    for q in sub_queries:
        try:
            query_vector = get_embedding(q)
            
            params = {
                "query_text": q,
                "query_embedding": query_vector,
                "match_count": current_limit,
                "full_text_weight": search_params.get("full_text_weight", 1.0),
                "semantic_weight": search_params.get("semantic_weight", 1.0),
                "recency_weight": search_params.get("recency_weight", 0.5),
                "folder_weights": folder_weights
            }
            
            response = supabase.rpc("hybrid_search", params).execute()
            
            for rank, r in enumerate(response.data):
                chunk_id = r['chunk_id']
                rrf_score = 1.0 / (60 + rank)
                
                existing = next((x for x in all_results if x['chunk_id'] == chunk_id), None)
                
                if existing:
                    existing['_rrf_score'] += rrf_score
                    existing['_matched_queries'].append(q)
                else:
                    r['_rrf_score'] = rrf_score
                    r['_matched_queries'] = [q]
                    all_results.append(r)
                    
        except Exception as e:
            response_log.append(f"Error querying '{q}': {str(e)}")

    # 3. Sort Results
    all_results.sort(key=lambda x: x['_rrf_score'], reverse=True)
    final_results = all_results[:12] if is_multi_query else all_results

    if not final_results:
        return {"results": [], "deep_results": [], "log": response_log}

    # 4. Process Results & find Links
    linked_doc_ids = set()
    formatted_results = []

    for res in final_results:
        doc_id = res.get('document_id')
        repo_path = res.get('repo_path', 'Unknown')
        
        # Link Lookup
        references = []
        if doc_id:
            try:
                links_res = supabase.table("rag_links").select("target_doc_path").eq("source_doc_id", doc_id).execute()
                if links_res.data:
                    # Collect target paths for return
                    references = [l['target_doc_path'] for l in links_res.data]
                    
                    # Collect IDs for Deep Search (using basename logic)
                    if deep_mode:
                        target_paths = [os.path.basename(l['target_doc_path']) for l in links_res.data]
                        clean_paths = [tp.split('#')[0] for tp in target_paths if tp.strip()]
                        
                        if clean_paths:
                            or_condition = ",".join([f"repo_path.ilike.%{tp}%" for tp in clean_paths])
                            target_docs = supabase.table("rag_documents").select("id").or_(or_condition).execute()
                            for d in target_docs.data:
                                linked_doc_ids.add(d['id'])
            except Exception:
                pass

        formatted_results.append({
            "content": res.get('content', '').strip(),
            "source": repo_path,
            "score": res.get('_rrf_score', 0),
            "references": references,
            "matched_queries": res.get('_matched_queries', [])
        })

    # 5. Batch Deep Search
    deep_search_results = []
    if deep_mode and linked_doc_ids:
        queries_to_run = sub_queries if is_multi_query else [query_text]
        all_deep_matches = []
        
        for dq in queries_to_run:
            try:
                dq_vec = get_embedding(dq)
                deep_res = supabase.rpc("match_chunks_in_docs", {
                    "query_embedding": dq_vec,
                    "match_threshold": 0.35, # Synced with latest optimization
                    "match_count": 5, 
                    "target_doc_ids": list(linked_doc_ids),
                    "query_text": dq
                }).execute()
                
                if deep_res.data:
                    all_deep_matches.extend(deep_res.data)
            except Exception as e:
                response_log.append(f"Deep search error '{dq}': {str(e)}")

        # Deduplicate Deep Results
        unique_deep = {res['chunk_id']: res for res in all_deep_matches}.values()
        sorted_deep = sorted(unique_deep, key=lambda x: x['similarity'], reverse=True)[:6]
        
        for dr in sorted_deep:
            deep_search_results.append({
                "content": dr.get('chunk_content', '').strip(),
                "source": dr.get('repo_path', 'Unknown'),
                "score": dr.get('similarity', 0)
            })

    return {
        "results": formatted_results,
        "deep_results": deep_search_results,
        "log": response_log
    }
