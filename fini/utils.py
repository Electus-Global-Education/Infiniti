# fini/utils.py
import re
import time
from baserag.connection import embedding_model, vector_store
from typing import List, Dict, Optional, Tuple
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
from youtube_transcript_api.formatters import TextFormatter
from celery import shared_task
from langchain.text_splitter import RecursiveCharacterTextSplitter


SIMILARITY_THRESHOLD = 0.90

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


def _extract_video_id(youtube_url: str) -> Optional[str]:
    """
    Extract the YouTube video ID from a URL. Handles common formats such as:
      - https://www.youtube.com/watch?v=VIDEO_ID
      - https://youtu.be/VIDEO_ID
      - https://www.youtube.com/embed/VIDEO_ID
      - with additional URL parameters (e.g. &t=30s, &list=XYZ)
    Returns None if no valid ID is found.
    """
    # 1) Standard “v=” query parameter
    match = re.search(r"(?:v=)([A-Za-z0-9_\-]{11})", youtube_url)
    if match:
        return match.group(1)

    # 2) youtu.be short link
    match = re.search(r"youtu\.be/([A-Za-z0-9_\-]{11})", youtube_url)
    if match:
        return match.group(1)

    # 3) embed URL format
    match = re.search(r"youtube\.com/embed/([A-Za-z0-9_\-]{11})", youtube_url)
    if match:
        return match.group(1)

    # 4) Fallback: any 11‐character YouTube ID in the URL
    match = re.search(r"([A-Za-z0-9_\-]{11})", youtube_url)
    if match:
        return match.group(1)

    return None


def fetch_youtube_transcript(video_url: str) -> Optional[str]:
    """
    Fetch the plain‐text transcript of a single YouTube video. Returns the transcript as a single string,
    or None if it could not be retrieved (e.g. no transcript exists, video is unavailable, etc.).
    """
    video_id = _extract_video_id(video_url)
    if not video_id:
        # Invalid URL / no 11‐character ID found
        print(f"[fetch_youtube_transcript] Could not extract video ID from: {video_url}")
        return None

    try:
        raw_transcript = YouTubeTranscriptApi.get_transcript(video_id)
    except TranscriptsDisabled:
        print(f"[fetch_youtube_transcript] Transcripts are disabled for video {video_url} (ID={video_id}).")
        return None
    except NoTranscriptFound:
        print(f"[fetch_youtube_transcript] No transcript found for video {video_url} (ID={video_id}).")
        return None
    except VideoUnavailable:
        print(f"[fetch_youtube_transcript] Video unavailable: {video_url} (ID={video_id}).")
        return None
    except Exception as e:
        print(f"[fetch_youtube_transcript] Error retrieving transcript for {video_url}: {e}")
        return None

    # Format into a single plain‐text string
    formatter = TextFormatter()
    try:
        plain_text = formatter.format_transcript(raw_transcript)
    except Exception as e:
        print(f"[fetch_youtube_transcript] Error formatting transcript for {video_url}: {e}")
        return None

    return plain_text


def fetch_multiple_transcripts(
    video_urls: List[str]
) -> Tuple[Dict[str, str], List[str]]:
    """
    Given a list of YouTube URLs, attempts to fetch each transcript.
    Returns a tuple of:
      1) transcripts_dict: a dict mapping each URL (str) → transcript text (str) for those that succeeded,
      2) failed_urls: a list of URLs (str) for which no transcript was available (or retrieval failed).

    Example usage:
        urls = [
            "https://www.youtube.com/watch?v=abcd1234",
            "https://youtu.be/WXYZ5678?feature=share",
        ]
        transcripts_dict, failed_urls = fetch_multiple_transcripts(urls)

        # transcripts_dict might be:
        # {
        #   "https://www.youtube.com/watch?v=abcd1234": "Full transcript text …"
        # }
        # failed_urls might be:
        # [
        #   "https://youtu.be/WXYZ5678?feature=share"
        # ]
    """
    transcripts_dict: Dict[str, str] = {}
    failed_urls: List[str] = []

    for url in video_urls:
        text = fetch_youtube_transcript(url)
        if text is None:
            # No transcript (or error), so “pass” the URL into failed_urls
            failed_urls.append(url)
        else:
            transcripts_dict[url] = text

    return transcripts_dict, failed_urls

def preprocess_text(text: str) -> str:
    """
    Remove excessive newlines from the transcript, merging them into single spaces.
    - Replaces one or more consecutive '\n' with a single space.
    - Also merges lone newlines between words into spaces.
    """
    # Replace any block of newlines (\n+) with a single space
    text = re.sub(r'\n+', ' ', text)
    # If a single newline occurs between two word characters, replace it with a space
    text = re.sub(r'(?<=\w)\n(?=\w)', ' ', text)
    return text

def _extract_video_id(youtube_url: str) -> Optional[str]:
    """
    Extract the YouTube video ID from a URL. Handles common formats:
      - https://www.youtube.com/watch?v=VIDEO_ID
      - https://youtu.be/VIDEO_ID
      - https://www.youtube.com/embed/VIDEO_ID
      - plus any trailing parameters
    Returns None if no valid 11-character ID is found.
    """
    # 1) Standard "v=" query parameter
    match = re.search(r"(?:v=)([A-Za-z0-9_\-]{11})", youtube_url)
    if match:
        return match.group(1)

    # 2) youtu.be short link
    match = re.search(r"youtu\.be/([A-Za-z0-9_\-]{11})", youtube_url)
    if match:
        return match.group(1)

    # 3) embed URL format
    match = re.search(r"youtube\.com/embed/([A-Za-z0-9_\-]{11})", youtube_url)
    if match:
        return match.group(1)

    # 4) Fallback: any 11-character block of letters/numbers/underscore/hyphen
    match = re.search(r"([A-Za-z0-9_\-]{11})", youtube_url)
    if match:
        return match.group(1)

    return None

def fetch_youtube_transcript(video_url: str) -> Optional[str]:
    """
    Fetch the raw YouTube transcript (as a plain string) for a given video URL.
    Returns the raw transcript text (with newlines), or None if it cannot be retrieved.
    """
    video_id = _extract_video_id(video_url)
    if not video_id:
        print(f"[fetch_youtube_transcript] Could not extract video ID from: {video_url}")
        return None

    try:
        raw_transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
    except TranscriptsDisabled:
        print(f"[fetch_youtube_transcript] Transcripts disabled for {video_url} (ID={video_id}).")
        return None
    except NoTranscriptFound:
        print(f"[fetch_youtube_transcript] No transcript found for {video_url} (ID={video_id}).")
        return None
    except VideoUnavailable:
        print(f"[fetch_youtube_transcript] Video unavailable: {video_url} (ID={video_id}).")
        return None
    except Exception as e:
        print(f"[fetch_youtube_transcript] Error retrieving transcript for {video_url}: {e}")
        return None

    # Combine segments into one big string
    formatter = TextFormatter()
    try:
        plain_text = formatter.format_transcript(raw_transcript_list)
    except Exception as e:
        print(f"[fetch_youtube_transcript] Error formatting transcript for {video_url}: {e}")
        return None

    return plain_text

def create_semantic_chunks(text: str, chunk_size: int = 1000, chunk_overlap: int = 100) -> List[str]:
    """
    Given a cleaned transcript string, split it into semantic chunks of approximately
    `chunk_size` characters with `chunk_overlap` characters overlap, using LangChain’s
    RecursiveCharacterTextSplitter.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", "!", "?", " "],
    )
    return splitter.split_text(text)

@shared_task
def process_video_chunks_task(video_url: str) -> Dict[str, object]:
    """
    Celery task to:
      1) Fetch & preprocess the transcript for a single YouTube URL.
      2) Create semantic chunks.
      3) For each chunk, compute its embedding and perform a similarity search.
         - If a chunk’s top similarity score > SIMILARITY_THRESHOLD, skip insertion.
         - Otherwise, assign a new ID and add to `vector_store`.
      4) Return a dictionary summarizing:
         - "video_url"
         - "inserted_ids":   [ list of new chunk IDs added ]
         - "skipped":       [ { "chunk_text": ..., "score": ... } ]
         - "total_chunks":  total number of semantic chunks generated
         - "skipped_count": how many were skipped due to high similarity
         - "elapsed_time":  how many seconds this entire task took
    """
    start_time = time.perf_counter()

    result: Dict[str, object] = {
        "video_url": video_url,
        "inserted_ids": [],
        "skipped": [],
        "total_chunks": 0,
        "skipped_count": 0,
        "elapsed_time": 0.0,
    }

    # 1) Fetch raw transcript
    raw = fetch_youtube_transcript(video_url)
    result["raw_transcript"] = raw

    if raw is None:
        # No transcript to process
        result["message"] = "No transcript could be retrieved."
        result["elapsed_time"] = time.perf_counter() - start_time
        return result

    # 2) Preprocess
    cleaned = preprocess_text(raw)

    # 3) Create semantic chunks
    chunks = create_semantic_chunks(cleaned)
    result["total_chunks"] = len(chunks)

    # 4) Extract a simple video_id to build unique IDs
    vid_id = _extract_video_id(video_url) or video_url

    # 5) Determine next available chunk index in the vector store metadata
    #    We look at all existing embeddings in the store whose IDs start with "{vid_id}_chunk_"
    existing_ids = []
    # We assume vector_store has a `search_ids_by_prefix(...)` or similar. If not,
    # fall back to scanning metadata in memory or GCS. For simplicity, we’ll try:
    try:
        existing_ids = vector_store.search_ids_by_prefix(f"{vid_id}_chunk_")
    except AttributeError:
        # If `search_ids_by_prefix` does not exist, you could implement another technique
        # (e.g. scan all metadata via GCS listing). For now, we'll just set existing_ids = [].
        existing_ids = []

    if existing_ids:
        numeric_indices = [
            int(idx.replace(f"{vid_id}_chunk_", "")) 
            for idx in existing_ids 
            if idx.startswith(f"{vid_id}_chunk_") and idx.replace(f"{vid_id}_chunk_", "").isdigit()
        ]
        next_index = max(numeric_indices) + 1 if numeric_indices else 0
    else:
        next_index = 0

    # 6) Loop over each chunk, compute embedding, check similarity, and insert if “new”
    for i, chunk_text in enumerate(chunks):
        # Compute embedding (list of floats) for this single chunk
        new_embedding = embedding_model.embed_documents([chunk_text])[0]

        # Search the most similar existing doc by vector, returning (doc, score)
        results = vector_store.similarity_search_by_vector_with_score(new_embedding, k=1)
        if results:
            existing_doc, score = results[0]  # top‐1
            if score >= SIMILARITY_THRESHOLD:
                # Skip inserting
                result["skipped"].append({
                    "chunk_text": chunk_text,
                    "score": score,
                })
                result["skipped_count"] += 1
                continue

        # If we reach here, either `results` was empty or top score < threshold
        new_id = f"{vid_id}_chunk_{next_index}"
        next_index += 1

        metadata = {
            "text": chunk_text,
            "chunk_text": chunk_text,
            "chunk_index": i,
            "source_link": video_url,
            # you can add "user_uuid", "org_uuid", etc. if needed
        }

        # Add to the vector store
        vector_store.add_texts([chunk_text], metadatas=[metadata], ids=[new_id])
        result["inserted_ids"].append(new_id)

    result["elapsed_time"] = time.perf_counter() - start_time
    return result
# def generate_llm_response_from_chunks(base_prompt: str, user_query: str, user_role: str, chunks: list) -> str:
#     """
#     Composes a full prompt using base prompt, user role, query, and chunks.
#     Sends to Gemini LLM for response.
#     """
#     # Construct context
#     context_text = "\n".join([doc.page_content for doc, _ in chunks]) if chunks else "No additional context found."

#     # Final prompt sent to LLM
#     full_prompt = (
#         f"User Role: {user_role}\n"
#         f"Instructions: {base_prompt}\n\n"
#         f"Relevant Context:\n{context_text}\n\n"
#         f"User Question: {user_query}"
#     )

#     try:
#         response = gemini.generate_content(full_prompt)
#         return response.text.strip()
#     except Exception as e:
#         raise RuntimeError(f"LLM response generation failed: {str(e)}")