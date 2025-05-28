# fini/utils.py
import time
from baserag.connection import embedding_model,vector_store


def generate_query_embedding(query: str) -> list[float]:
    """
    Generate an embedding vector for a given query string.

    Args:
        query (str): User input query.

    Returns:
        list[float]: Embedding vector.

    Raises:
        ValueError: If the query is empty or embedding fails.
    """
    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    embedding = embedding_model.embed_documents([query])[0]
    if not embedding:
        raise ValueError("Embedding generation failed.")
    cleaned_query = query.strip()
    return embedding,cleaned_query

def retrieve_chunks_by_embedding(embedding: list, top_k: int = 5):
    """
    Retrieves top-K similar chunks from the vector store for a given embedding.
    Returns (elapsed_time, results).
    """
    try:
        start = time.time()
        results = vector_store.similarity_search_by_vector_with_score(embedding, k=top_k)
        elapsed = time.time() - start
        return elapsed, results
    except Exception as e:
        raise RuntimeError(f"Vector store search failed: {str(e)}")

def generate_llm_response_from_chunks(base_prompt: str, user_query: str, user_role: str, chunks: list) -> str:
    """
    Composes a full prompt using base prompt, user role, query, and chunks.
    Sends to Gemini LLM for response.
    """
    # Construct context
    context_text = "\n".join([doc.page_content for doc, _ in chunks]) if chunks else "No additional context found."

    # Final prompt sent to LLM
    full_prompt = (
        f"User Role: {user_role}\n"
        f"Instructions: {base_prompt}\n\n"
        f"Relevant Context:\n{context_text}\n\n"
        f"User Question: {user_query}"
    )

    try:
        response = gemini.generate_content(full_prompt)
        return response.text.strip()
    except Exception as e:
        raise RuntimeError(f"LLM response generation failed: {str(e)}")