import time
from typing import List, Optional, Tuple, Dict, Any

from baserag.connection import embedding_model, vector_store
from google.cloud.aiplatform.matching_engine.matching_engine_index_endpoint import Namespace


def retrieve_distinct_edujob_chunks(
    query: str,
    top_k: int = 10
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    1. Embed the user’s query.
    2. Run a top-K similarity search against all Edujob chunks.
    3. De-dupe on edujob_title, keeping the highest-scoring chunk per title.
    Returns (elapsed_sec, [ {chunk_id, edujob_title, snippet, score, metadata}, … ])
    """
    # 1) Clean & embed
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("Query cannot be empty.")
    emb = embedding_model.embed_documents([cleaned])[0]

    # 2) Search
    start = time.time()
    hits = vector_store.similarity_search_by_vector_with_score(
        embedding=emb,
        k=top_k
    )
    elapsed = time.time() - start

    # 3) De-dupe per edujob_title
    seen_titles = set()
    recs: List[Dict[str, Any]] = []
    for doc, score in hits:
        meta = doc.metadata
        title = meta.get("edujob_title")
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        recs.append({
            "chunk_id":    doc.id,
            "edujob_title": title,
            "snippet":     doc.page_content,
            "score":       score,
            "metadata":    meta,
        })

    return elapsed, recs


def retrieve_by_keywords(
    keywords: List[str],
    top_k: int = 10
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    For each keyword in `keywords`, run retrieve_distinct_edujob_chunks(keyword, top_k)
    and tag each hit with "matched_keyword". Returns total_elapsed and flattened list.
    """
    from fini.edujob_rec import retrieve_distinct_edujob_chunks

    total_time = 0.0
    all_recs: List[Dict[str, Any]] = []

    for kw in keywords:
        start = time.perf_counter()
        elapsed, recs = retrieve_distinct_edujob_chunks(query=kw, top_k=top_k)
        total_time += elapsed

        # tag each result so you know which keyword matched
        for r in recs:
            r['matched_keyword'] = kw
            all_recs.append(r)

    return total_time, all_recs