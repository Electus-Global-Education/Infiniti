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


def retrieve_grant_chunks(
    query: str,
    grant_ids: Optional[List[str]] = None,
    funder_ids: Optional[List[str]] = None,
    top_k: int = 5
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    1. Embed the query.
    2. Build a list of VertexAI Namespace filters for your metadata keys.
    3. Call similarity_search_by_vector_with_score(filter=[...]).
    4. Return elapsed time + [{text, score, metadata}, …].
    """
    # 1. Embed the query
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("Query cannot be empty.")
    emb = embedding_model.embed_documents([cleaned])[0]

    # 2. Build Namespaces for filtering
    namespaces: List[Namespace] = []
    # Only our grant_opportunity docs:
    namespaces.append(Namespace("doc_type", ["grant_opportunity"], []))
    # Optionally restrict to specific grant_ids
    if grant_ids:
        namespaces.append(Namespace("grant_id", grant_ids, []))
    # Optionally restrict to specific funder_ids
    if funder_ids:
        namespaces.append(Namespace("funder_id", funder_ids, []))

    # 3. Run the search
    start = time.time()
    hits = vector_store.similarity_search_by_vector_with_score(
        embedding=emb,
        k=top_k,
        filter=namespaces,            # <-- list of Namespace objects
        rrf_ranking_alpha=1.0,        # keep default or adjust if you’re using hybrid search
    )
    elapsed = time.time() - start

     # Step 4: Collect all grant_ids and bulk‐fetch titles
    #seen_ids = {doc.metadata["grant_id"] for doc, _ in hits}
    #grants = GrantOpportunity.objects.filter(id__in=seen_ids).only("id", "title")
    #title_map = {str(g.id): g.title for g in grants}

    # 4. Massage results
    out = []
    for doc, score in hits:
        #gid = doc.metadata.get("grant_id") 
        out.append({
            "text": doc.page_content,
            "score": score,
            "metadata": doc.metadata,
            #"title": title_map.get(gid, None),
            # "title": metadata.get("title"),  
        })
    return elapsed, out
