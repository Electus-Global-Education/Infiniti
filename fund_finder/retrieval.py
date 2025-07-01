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


def retrieve_distinct_grant_recs(
    query: str,
    funder_ids: Optional[List[str]] = None,
    top_k: int = 5
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    1. Embed the user’s query.
    2. Filter to only grant_opportunity docs (and optional funders).
    3. Top-K similarity search.
    4. Dedupe on grant_id, keeping the highest‐scoring chunk per grant.
    Returns (elapsed_sec, [ {grant_id, title, snippet, score, metadata}, … ])
    """
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("Query cannot be empty.")
    emb = embedding_model.embed_documents([cleaned])[0]

    # build namespaces filter
    namespaces = [Namespace("doc_type", ["grant_opportunity"], [])]
    if funder_ids:
        namespaces.append(Namespace("funder_id", funder_ids, []))

    start = time.time()
    hits = vector_store.similarity_search_by_vector_with_score(
        embedding=emb,
        k=top_k,
        filter=namespaces
    )
    elapsed = time.time() - start

    seen: set[str] = set()
    recs: List[Dict[str, Any]] = []
    for doc, score in hits:
        gid = doc.metadata.get("grant_id")
        if not gid or gid in seen:
            continue
        seen.add(gid)
        recs.append({
            "grant_id": gid,
            "title":     doc.metadata.get("title"),
            "snippet":   doc.page_content,
            "score":     score,
            "metadata":  doc.metadata,
        })

    return elapsed, recs


def retrieve_by_grant_keywords(
    keywords: List[str],
    funder_ids: Optional[List[str]] = None,
    top_k: int = 5
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Run retrieve_distinct_grant_recs for each keyword, tag each hit with
    'matched_keyword', then dedupe by grant_id (highest‐score wins).
    Returns (total_elapsed_sec, distinct_recs).
    """
    total_elapsed = 0.0
    all_hits: List[Dict[str, Any]] = []

    for kw in keywords:
        elapsed, recs = retrieve_distinct_grant_recs(
            query=kw,
            funder_ids=funder_ids,
            top_k=top_k
        )
        total_elapsed += elapsed
        for r in recs:
            r["matched_keyword"] = kw
            all_hits.append(r)

    # dedupe by grant_id, keep best
    best: Dict[str, Dict[str, Any]] = {}
    for hit in all_hits:
        gid = hit["grant_id"]
        if gid not in best or hit["score"] > best[gid]["score"]:
            best[gid] = hit

    return total_elapsed, list(best.values())