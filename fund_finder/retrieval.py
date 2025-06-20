import time
from typing import List, Optional, Tuple, Dict, Any

from baserag.connection import embedding_model, vector_store
from google.cloud.aiplatform.matching_engine.matching_engine_index_endpoint import Namespace
from .models import GrantOpportunity

def generate_query_embedding(query: str) -> Tuple[List[float], str]:
    """
    Generate an embedding vector for a given query string.

    Args:
        query: User input query.

    Returns:
        Tuple[embedding vector, cleaned query]
    """
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("Query cannot be empty.")

    emb = embedding_model.embed_documents([cleaned])[0]
    if not emb:
        raise ValueError("Embedding generation failed.")
    return emb, cleaned


def retrieve_grant_chunks_grouped(
    query: str,
    grant_ids: Optional[List[str]] = None,
    funder_ids: Optional[List[str]] = None,
    top_k: int = 5
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    1. Embed the query.
    2. Build VertexAI Namespace filters.
    3. Run a top-K similarity search.
    4. Deduplicate chunks by (grant_id, chunk_index).
    5. Group the distinct chunks under each grant's title.
    
    Returns:
        elapsed_seconds: float
        results: List of {
          'grant_id': str,
          'title':    str,
          'chunks': [
              { 'text': ..., 'score': ..., 'metadata': { ... } },
              ...
          ]
        }
    """
    # 1. Embed
    emb, _ = generate_query_embedding(query)

    # 2. Build Namespace filters
    namespaces = [Namespace("doc_type", ["grant_opportunity"], [])]
    if grant_ids:
        namespaces.append(Namespace("grant_id", grant_ids, []))
    if funder_ids:
        namespaces.append(Namespace("funder_id", funder_ids, []))

    # 3. Search
    start = time.time()
    hits = vector_store.similarity_search_by_vector_with_score(
        embedding=emb,
        k=top_k,
        filter=namespaces
    )
    elapsed = time.time() - start

    # 4. Deduplicate
    seen_keys = set()
    distinct_chunks = []
    for doc, score in hits:
        meta = doc.metadata
        key = (meta["grant_id"], meta["chunk_index"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        distinct_chunks.append({
            "grant_id": meta["grant_id"],
            "title":    meta.get("title"),
            "text":     doc.page_content,
            "score":    score,
            "metadata": meta,
        })

    # 5. Group by grant
    grouped: Dict[str, Dict[str, Any]] = {}
    for chunk in distinct_chunks:
        gid   = chunk["grant_id"]
        title = chunk["title"]
        if gid not in grouped:
            grouped[gid] = {
                "grant_id": gid,
                "title":    title,
                "chunks":   []
            }
        grouped[gid]["chunks"].append({
            "text":     chunk["text"],
            "score":    chunk["score"],
            "metadata": chunk["metadata"],
        })

    return elapsed, list(grouped.values())