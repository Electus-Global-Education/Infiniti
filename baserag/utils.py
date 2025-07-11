import re
import os
import time
import environ
import requests
import tempfile
import traceback
from docx import Document as DocxDocument
from PyPDF2 import PdfReader
from baserag.connection import embedding_model, vector_store
from typing import List, Dict, Optional, Tuple
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
from youtube_transcript_api._errors import CouldNotRetrieveTranscript
from youtube_transcript_api.formatters import TextFormatter
from celery import shared_task
from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List, Dict, Optional, Union
from urllib.parse import urlparse, parse_qs


SIMILARITY_THRESHOLD = 0.90

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
gemini_env = environ.Env(
    BOCLIPS_CLIENT_ID=(str),     
    BOCLIPS_CLIENT_SECRET=(str),
)

GEMINI_ENV_PATH = os.path.join(BASE_DIR, ".env.gemini")
if os.path.exists(GEMINI_ENV_PATH):
    gemini_env.read_env(GEMINI_ENV_PATH)
    # print("BOCLIPS_CLIENT_ID:", gemini_env("BOCLIPS_CLIENT_ID", default="Not found"))
    # print("BOCLIPS_CLIENT_SECRET:", gemini_env("BOCLIPS_CLIENT_SECRET", default="Not found"))
else:
    print(f"{GEMINI_ENV_PATH} not found.")

# ──────────────────────────────────────────────────────────────────────────────
# A) Read BOCLIPS_CLIENT_ID / CLIENT_SECRET from .env.gemini
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
gemini_env = environ.Env(
    BOCLIPS_CLIENT_ID=(str, ""),
    BOCLIPS_CLIENT_SECRET=(str, ""),
)
GEMINI_ENV_PATH = os.path.join(BASE_DIR, ".env.gemini")
if os.path.exists(GEMINI_ENV_PATH):
    gemini_env.read_env(GEMINI_ENV_PATH)


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


from urllib.parse import urlparse, parse_qs

def extract_video_id(youtube_url: str) -> Optional[str]:
    """
    Extracts the 11-character YouTube video ID from a given YouTube URL.

    Supports multiple YouTube URL formats:
    - Standard watch URLs: https://www.youtube.com/watch?v=VIDEO_ID
    - Shortened URLs: https://youtu.be/VIDEO_ID
    - Embed URLs: https://www.youtube.com/embed/VIDEO_ID

    Args:
        youtube_url (str): The full YouTube URL to extract the video ID from.

    Returns:
        Optional[str]: The extracted 11-character YouTube video ID if found, else None.

    Examples:
        >>> extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        'dQw4w9WgXcQ'
        >>> extract_video_id("https://youtu.be/dQw4w9WgXcQ")
        'dQw4w9WgXcQ'
        >>> extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ")
        'dQw4w9WgXcQ'
    """
    parsed = urlparse(youtube_url)
    query = parse_qs(parsed.query)

    # Method 1: From ?v= parameter
    if "v" in query and len(query["v"][0]) == 11:
        return query["v"][0]

    # Method 2: From path (e.g., youtu.be/<id>)
    match = re.search(r"youtu\.be/([A-Za-z0-9_-]{11})", parsed.path)
    if match:
        return match.group(1)

    # Method 3: From embed URL
    match = re.search(r"/embed/([A-Za-z0-9_-]{11})", parsed.path)
    if match:
        return match.group(1)

    # Method 4: Fallback — 11-char token anywhere in path
    match = re.search(r"([A-Za-z0-9_-]{11})", parsed.path)
    if match:
        return match.group(1)

    return None


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

def fetch_youtube_transcript(video_url: str) -> Optional[str]:
    """
    Fetches the transcript of a YouTube video in English (manual or auto-generated).

    Attempts to:
    - Extract the video ID from the given YouTube URL
    - Retrieve the transcript list using YouTubeTranscriptApi
    - Fetch the English transcript if available
    - Format and return the transcript text

    Args:
        video_url (str): Full YouTube video URL (e.g., https://www.youtube.com/watch?v=dQw4w9WgXcQ)

    Returns:
        Optional[str]: The full formatted transcript as a single string, or None if unavailable.

    Raises:
        None directly — logs errors and safely returns None on failure.

    Example:
        >>> fetch_youtube_transcript("https://youtu.be/dQw4w9WgXcQ")
        "We're no strangers to love..."
    """
    video_id = extract_video_id(video_url)
    print(f"[DEBUG] Extracted video ID: {video_id}")
    if not video_id:
        print(f"[ERROR] Invalid YouTube URL: {video_url}")
        return None

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Try to find English transcript (manual or generated)
        transcript = transcript_list.find_transcript(['en'])

        # Fetch as Transcript object
        transcript_data = transcript.fetch()
    except NoTranscriptFound:
        print(f"[ERROR] No transcript found for {video_id}")
        return None
    except (TranscriptsDisabled, VideoUnavailable, CouldNotRetrieveTranscript) as e:
        print(f"[ERROR] Known fetch failure for {video_id}: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] Unexpected error fetching transcript: {e}")
        return None

    try:
        formatter = TextFormatter()
        return formatter.format_transcript(transcript_data)
    except Exception as e:
        print(f"[ERROR] Formatting transcript failed: {e}")
        return None

def fetch_youtube_title(video_url: str) -> Optional[str]:
    """
    Fetches the title of a YouTube video by scraping its HTML <title> tag.
    Strips the trailing " - YouTube" suffix.
    """
    video_id = extract_video_id(video_url)
    print(f"[DEBUG] Extracted video ID for title: {video_id}")
    if not video_id:
        print(f"[ERROR] Invalid YouTube URL: {video_url}")
        return None

    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        resp = requests.get(url)
        resp.raise_for_status()
        match = re.search(r"<title>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
        if not match:
            print(f"[ERROR] Could not parse title for video ID: {video_id}")
            return None
        # Remove the " - YouTube" suffix that appears in the HTML title
        title = match.group(1).replace(" - YouTube", "").strip()
        print(f"[DEBUG] Fetched video title: {title}")
        return title
    except requests.RequestException as e:
        print(f"[ERROR] HTTP error fetching title: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] Unexpected error fetching title: {e}")
        return None



# ──────────────────────────────────────────────────────────────────────────────
# B) Helper: extract the bare Boclips ID from any URL or raw ID,
#    with debug prints to confirm what’s happening.
# ──────────────────────────────────────────────────────────────────────────────
def _extract_boclips_id(video_ref: str) -> str:
    """
    If video_ref is a full URL—e.g.
      - "https://www.boclips.com/videos/6080431a52688a3fcaf2ed26"
      - "https://www.boclips.com/videos/shared/6080431a52688a3fcaf2ed26"
      - "https://classroom.boclips.com/videos/shared/6080431a52688a3fcaf2ed26?…"
    —this returns the last non‐empty path segment ("6080431a52688a3fcaf2ed26").
    If video_ref is already a bare ID, returns it unchanged.
    """
    print(f"[extract_boclips_id] received video_ref = {video_ref}")
    try:
        parsed = urlparse(video_ref)
        path = parsed.path  # e.g. "/videos/shared/6080431a52688a3fcaf2ed26"
        segments = [seg for seg in path.split("/") if seg]
        if not segments:
            print(f"[extract_boclips_id] no path segments, returning original: {video_ref}")
            return video_ref
        video_id = segments[-1]
        print(f"[extract_boclips_id] returning video_id = {video_id}")
        return video_id
    except Exception as e:
        print(f"[extract_boclips_id] exception parsing, returning original: {video_ref}  (error: {e})")
        return video_ref
    
def get_boclips_title(video_ref: str) -> Optional[str]:
    """
    1) Normalize video_ref to bare ID.
    2) Fetch metadata via get_boclips_metadata().
    3) If metadata is present, return metadata['title'] (or fallback
       to another plausible key), else return None.
    """
    # 1) Normalize and log
    video_id = _extract_boclips_id(video_ref)
    print(f"[get_boclips_title] using video_id = {video_id}")

    # 2) Get full metadata
    try:
        metadata: Optional[Dict] = get_boclips_metadata(video_ref)
    except Exception as e:
        print(f"[get_boclips_title] error fetching metadata for {video_id}: {e}")
        return None

    if not metadata:
        print(f"[get_boclips_title] no metadata found for {video_id}")
        return None

    # 3) Extract title field (API typically returns "title")
    title = metadata.get("title") or metadata.get("name")
    if title:
        print(f"[get_boclips_title] fetched title: {title}")
    else:
        print(f"[get_boclips_title] metadata has no 'title' or 'name' field for {video_id}")
    return title


# ──────────────────────────────────────────────────────────────────────────────
# C) Get a Boclips access token via client_credentials (form‐encoded)
# ──────────────────────────────────────────────────────────────────────────────
def get_boclips_access_token() -> str:
    client_id = gemini_env("BOCLIPS_CLIENT_ID")
    client_secret = gemini_env("BOCLIPS_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise Exception("Missing BOCLIPS_CLIENT_ID or BOCLIPS_CLIENT_SECRET in .env.gemini")

    token_url = "https://api.boclips.com/v1/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded; charset=ISO-8859-1"}
    resp = requests.post(token_url, data=payload, headers=headers)
    if resp.status_code == 200:
        return resp.json()["access_token"]
    else:
        raise Exception(f"Boclips token request failed: {resp.status_code} - {resp.text}")


# ──────────────────────────────────────────────────────────────────────────────
# D) Fetch metadata (/v1/videos/{id}); if 403/404, return None, 
#    but log what {id} is being used.
# ──────────────────────────────────────────────────────────────────────────────
def get_boclips_metadata(video_ref: str) -> Optional[Dict]:
    """
    1) Normalize to bare ID
    2) GET /v1/videos/{id}
    3) If 200, return JSON. If 403/404, log and return None.
    4) Else, raise Exception.
    """
    video_id = _extract_boclips_id(video_ref)
    print(f"[get_boclips_metadata] using video_id = {video_id}")
    access_token = get_boclips_access_token()
    metadata_url = f"https://api.boclips.com/v1/videos/{video_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    resp = requests.get(metadata_url, headers=headers)
    if resp.status_code == 200:
        return resp.json()
    elif resp.status_code in (403, 404):
        print(f"[get_boclips_metadata] Warning: metadata {resp.status_code} for ID {video_id}")
        return None
    else:
        raise Exception(f"Error fetching Boclips metadata: {resp.status_code} - {resp.text}")


# ──────────────────────────────────────────────────────────────────────────────
# E) Fetch transcript: use metadata’s link if present, else fallback to /v1/videos/{id}/transcript
#    Again, log exactly which ID is being used.
# ──────────────────────────────────────────────────────────────────────────────
def get_boclips_transcript(video_ref: str) -> Optional[Union[str, Dict]]:
    """
    1) Normalize to bare ID.
    2) Attempt metadata to find a transcript link.
    3) If metadata is None, fall back to constructing
         https://api.boclips.com/v1/videos/{video_id}/transcript
    4) GET the transcript. If 200, return JSON or plain text; if 403/404, return None.
    5) Otherwise, raise Exception.
    """
    video_id = _extract_boclips_id(video_ref)
    print(f"[get_boclips_transcript] using video_id = {video_id}")

    # 1) Attempt metadata
    metadata = None
    try:
        metadata = get_boclips_metadata(video_ref)
    except Exception:
        # If it was a 5xx error, bubble up
        raise

    if metadata and "_links" in metadata and "transcript" in metadata["_links"]:
        transcript_href = metadata["_links"]["transcript"]["href"]
        print(f"[get_boclips_transcript] using transcript link from metadata: {transcript_href}")
    else:
        transcript_href = f"https://api.boclips.com/v1/videos/{video_id}/transcript"
        print(f"[get_boclips_transcript] no metadata link, falling back to: {transcript_href}")

    access_token = get_boclips_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(transcript_href, headers=headers)

    if resp.status_code == 200:
        raw_text = resp.text.strip()
        if not raw_text:
            return None
        try:
            return resp.json()
        except ValueError:
            return raw_text
    elif resp.status_code in (403, 404):
        print(f"[get_boclips_transcript] Warning: transcript {resp.status_code} for ID {video_id}")
        return None
    else:
        raise Exception(f"Error fetching Boclips transcript: {resp.status_code} - {resp.text}")


# ──────────────────────────────────────────────────────────────────────────────
# A) Extract text from DOCX
# ──────────────────────────────────────────────────────────────────────────────
def extract_text_from_docx(path: str) -> str:
    """
    Open a .docx file at `path` and return all paragraphs joined as a single string.
    """
    try:
        doc = DocxDocument(path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return "\n".join(full_text)
    except Exception as e:
        raise Exception(f"Error extracting DOCX text: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# B) Extract text from PDF
# ──────────────────────────────────────────────────────────────────────────────
def extract_text_from_pdf(path: str) -> str:
    """
    Open a .pdf file at `path` using PyPDF2 and return the concatenation of all page texts.
    """
    try:
        reader = PdfReader(path)
        all_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                all_text.append(text)
        return "\n".join(all_text)
    except Exception as e:
        raise Exception(f"Error extracting PDF text: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# C) Celery task: process a document (DOCX or PDF), chunk, embed, dedupe, insert
# ──────────────────────────────────────────────────────────────────────────────


@shared_task
def process_video_chunks_task(video_url: str, org_id: str, org_app_name: str) -> Dict[str, object]:

    """
    Celery task to process a YouTube video into semantically meaningful text chunks
    and store them in a vector database if they are not semantically similar
    to existing entries.

    Steps:
    1. Fetch and clean transcript text from a YouTube video.
    2. Break transcript into semantic chunks.
    3. Generate embeddings for each chunk.
    4. Perform similarity search to avoid duplication.
    5. Store unique chunks into a vector store with metadata.

    Args:
        video_url (str): The full URL of the YouTube video to process.

    Returns:
        Dict[str, object]: A dictionary containing:
            - video_url (str)
            - inserted_ids (List[str])
            - skipped (List[Dict])
            - total_chunks (int)
            - skipped_count (int)
            - raw_transcript (Optional[str])
            - elapsed_time (float)
            - message (Optional[str])
    """

    start_time = time.perf_counter()

    title: Optional[str] = fetch_youtube_title(video_url)
    print(f"[DEBUG] Fetched video title: {title}")

    result: Dict[str, object] = {
        "org_id": org_id,
        "org_app_name": org_app_name,
        "video_url": video_url,
        "inserted_ids": [],
        "skipped": [],
        "total_chunks": 0,
        "skipped_count": 0,
        "elapsed_time": 0.0,
    }

    print(f"[INFO] Processing video: {video_url}")

    # 1) Fetch raw transcript
    raw = fetch_youtube_transcript(video_url)
    result["raw_transcript"] = raw

    if raw is None:
        result["message"] = "No transcript could be retrieved."
        result["elapsed_time"] = time.perf_counter() - start_time
        print(f"[WARN] No transcript retrieved for: {video_url}")
        return result

    # 2) Preprocess transcript
    cleaned = preprocess_text(raw)

    # 3) Create semantic chunks
    chunks = create_semantic_chunks(cleaned)
    result["total_chunks"] = len(chunks)

    if not chunks:
        result["message"] = "Transcript returned no usable chunks."
        result["elapsed_time"] = time.perf_counter() - start_time
        print(f"[WARN] No chunks created for: {video_url}")
        return result

    # 4) Generate base chunk ID using clean video ID
    vid_id = extract_video_id(video_url) or "unknown"
    prefix = f"{vid_id}_chunk_"

    # 5) Determine next index from existing vector store entries
    try:
        existing_ids = vector_store.search_ids_by_prefix(prefix)
    except AttributeError:
        existing_ids = []

    if existing_ids:
        indices = [
            int(i.replace(prefix, "")) for i in existing_ids
            if i.startswith(prefix) and i.replace(prefix, "").isdigit()
        ]
        next_index = max(indices) + 1 if indices else 0
    else:
        next_index = 0

    # 6) Process each chunk
    for i, chunk_text in enumerate(chunks):
        try:
            embedding = embedding_model.embed_documents([chunk_text])[0]
        except Exception as e:
            print(f"[ERROR] Embedding failed at chunk {i}: {e}")
            continue

        try:
            results = vector_store.similarity_search_by_vector_with_score(embedding, k=1)
        except Exception as e:
            print(f"[ERROR] Similarity search failed at chunk {i}: {e}")
            results = []

        if results:
            existing_doc, score = results[0]
            if score >= SIMILARITY_THRESHOLD:
                result["skipped"].append({"chunk_text": chunk_text, "score": score})
                result["skipped_count"] += 1
                continue

        # Insert new chunk
        chunk_id = f"{prefix}{next_index}"
        next_index += 1

        metadata = {
            "title": title, 
            "org_id": org_id,
            "org_app_name": org_app_name,
            "edujob_title": title,
            "text": chunk_text,
            "chunk_text": chunk_text,
            "chunk_index": i,
            "source_link": video_url,
        }
        print("Metadata:")
        for key, value in metadata.items():
            print(f"{key}: {value}")

        try:
            vector_store.add_texts([chunk_text], metadatas=[metadata], ids=[chunk_id])
            result["inserted_ids"].append(chunk_id)
        except Exception as e:
            print(f"[ERROR] Failed to insert chunk {chunk_id}: {e}")

    result["elapsed_time"] = time.perf_counter() - start_time
    print(f"[SUCCESS] Finished processing: {video_url} in {result['elapsed_time']:.2f}s")
    return result



# ──────────────────────────────────────────────────────────────────────────────
# F) Main Celery task: chunk, embed, dedupe, insert. Always use the bare ID.
#    And confirm in logs that `video_id` is not the full URL.
# ──────────────────────────────────────────────────────────────────────────────
@shared_task
def process_boclips_video_task(video_ref: str,org_id: str, org_app_name: str) -> Dict[str, object]:
    """
    1) Normalize to bare ID; set that to result['video_id'].
    2) Try to fetch metadata (title/description) if available.
    3) Fetch transcript (via metadata link or fallback URL).
    4) If transcript is None, return early.
    5) Preprocess → chunk → embed → dedupe → insert in vector_store.
    6) Return metadata + embedding results.
    """
    # 1) Fetch title up-front
    title: Optional[str] = get_boclips_title(video_ref)
    start_time = time.perf_counter()
    result: Dict[str, object] = {
        "org_id": org_id,
        "org_app_name": org_app_name,
        "title": title,
        "video_id": None,
        "title": None,
        "description": None,
        "raw_transcript": None,
        "inserted_ids": [],
        "skipped": [],
        "total_chunks": 0,
        "skipped_count": 0,
        "elapsed_time": 0.0,
    }

    # 1) Normalize to bare ID
    try:
        video_id = _extract_boclips_id(video_ref)
    except Exception as e:
        result["error"] = f"Invalid Boclips reference '{video_ref}': {e}"
        result["elapsed_time"] = time.perf_counter() - start_time
        return result

    result["video_id"] = video_id
    print(f"[process_boclips] video_ref = {video_ref}")
    print(f"[process_boclips] extracted video_id = {video_id}")

    # 2) Fetch metadata (if available)
    metadata = None
    try:
        metadata = get_boclips_metadata(video_ref)
    except Exception:
        # If metadata call threw a 5xx, bubble up
        raise

    if metadata:
        result["title"] = metadata.get("title")
        result["description"] = metadata.get("description")

    # 3) Fetch raw transcript
    try:
        raw = get_boclips_transcript(video_ref)
    except Exception as e:
        result["error"] = f"Failed to fetch Boclips transcript: {e}"
        result["elapsed_time"] = time.perf_counter() - start_time
        return result

    result["raw_transcript"] = raw
    if raw is None:
        result["message"] = "No Boclips transcript available or forbidden."
        result["elapsed_time"] = time.perf_counter() - start_time
        return result

    # 4) Preprocess: if JSON with segments, join; else cast to str
    if isinstance(raw, dict) and "transcript" in raw and isinstance(raw["transcript"], list):
        text = " ".join(segment.get("text", "") for segment in raw["transcript"])
    else:
        text = str(raw)

    cleaned = preprocess_text(text)
    chunks = create_semantic_chunks(cleaned)
    result["total_chunks"] = len(chunks)

    # 5) Deduplication: find existing IDs with prefix
    prefix = f"boclips_{video_id}_chunk_"
    try:
        existing_ids = vector_store.search_ids_by_prefix(prefix)
    except AttributeError:
        existing_ids = []

    if existing_ids:
        numeric_indices = [
            int(idx.replace(prefix, "")) 
            for idx in existing_ids 
            if idx.startswith(prefix) and idx.replace(prefix, "").isdigit()
        ]
        next_index = max(numeric_indices) + 1 if numeric_indices else 0
    else:
        next_index = 0

    # 6) Embed + dedupe + insert
    for i, chunk_text in enumerate(chunks):
        new_embedding = embedding_model.embed_documents([chunk_text])[0]
        results = vector_store.similarity_search_by_vector_with_score(new_embedding, k=1)
        if results:
            existing_doc, score = results[0]
            if score >= 0.90:
                result["skipped"].append({"chunk_text": chunk_text, "score": score})
                result["skipped_count"] += 1
                continue

        new_id = f"{prefix}{next_index}"
        next_index += 1
        metadata_entry = {
            "org_id": org_id,
            "org_app_name": org_app_name,
            "title": title,
            "edujob_title": title,
            "text": chunk_text,
            "chunk_text": chunk_text,
            "chunk_index": i,
            "source_video": f"boclips:{video_id}",
        }
        print("Metadata:")
        for key, value in metadata_entry.items():
            print(f"{key}: {value}")
        vector_store.add_texts([chunk_text], metadatas=[metadata_entry], ids=[new_id])
        result["inserted_ids"].append(new_id)

    # 7) Final elapsed time
    result["elapsed_time"] = time.perf_counter() - start_time
    return result  

@shared_task
def process_document_task(file_path: str, original_filename: str) -> Dict[str, object]:
    """
    1) Determine file type by extension (.docx or .pdf)
    2) Extract text accordingly
    3) Preprocess → chunk → embed → dedupe → insert into vector_store
    4) Delete the uploaded file (whether success or error)
    5) Return a dict summarizing:
         - total_chunks
         - inserted_ids
         - skipped (list of {chunk_index, score})
         - skipped_count
         - elapsed_time
         - error (if any)
    """
    start_time = time.perf_counter()
    result: Dict[str, object] = {
        "original_filename": original_filename,
        "total_chunks": 0,
        "inserted_ids": [],
        "skipped": [],
        "skipped_count": 0,
        "elapsed_time": 0.0,
        "error": None,
    }

    try:
        # 1) Extract raw text based on extension
        _, ext = os.path.splitext(original_filename.lower())
        if ext == ".docx":
            raw_text = extract_text_from_docx(file_path)
        elif ext == ".pdf":
            raw_text = extract_text_from_pdf(file_path)
        else:
            raise Exception(f"Unsupported file extension: {ext}")

        if not raw_text.strip():
            result["error"] = "No text extracted from file."
            return result

        # 2) Preprocess text (reuse existing function)
        cleaned = preprocess_text(raw_text)

        # 3) Create semantic chunks (reuse existing function)
        chunks = create_semantic_chunks(cleaned)
        result["total_chunks"] = len(chunks)

        # 4) Deduplication and embedding logic (similar to Boclips pipeline)
        #    We’ll use a prefix based on filename (to avoid ID collisions):
        safe_filename = os.path.splitext(os.path.basename(original_filename))[0]
        prefix = f"doc_{safe_filename}_chunk_"

        # 4a) Check existing IDs in vector_store with that prefix
        try:
            existing_ids = vector_store.search_ids_by_prefix(prefix)
        except AttributeError:
            existing_ids = []

        if existing_ids:
            numeric_indices = [
                int(idx.replace(prefix, "")) 
                for idx in existing_ids 
                if idx.startswith(prefix) and idx.replace(prefix, "").isdigit()
            ]
            next_index = max(numeric_indices) + 1 if numeric_indices else 0
        else:
            next_index = 0

        # 4b) Iterate each chunk, embed, dedupe, insert
        for i, chunk_text in enumerate(chunks):
            new_embedding = embedding_model.embed_documents([chunk_text])[0]
            results = vector_store.similarity_search_by_vector_with_score(new_embedding, k=1)

            if results:
                existing_doc, score = results[0]
                if score >= 0.90:
                    # Skip this chunk
                    result["skipped"].append({"chunk_index": i, "score": score})
                    result["skipped_count"] += 1
                    continue

            # Otherwise, insert as new
            new_id = f"{prefix}{next_index}"
            next_index += 1

            metadata = {
                "title": original_filename,
                "edujob_title": original_filename,
                "text": chunk_text,
                "chunk_text": chunk_text,
                "chunk_index": i,
                "source_file": safe_filename,
                "original_filename": original_filename,
            }
            print("Metadata:")
            for key, value in metadata.items():
                print(f"{key}: {value}")

            vector_store.add_texts([chunk_text], metadatas=[metadata], ids=[new_id])
            result["inserted_ids"].append(new_id)

    except Exception as e:
        # Capture the stack trace for debugging
        result["error"] = f"{e}\n{traceback.format_exc()}"
    finally:
        # 5) Always delete the file after processing
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            # Ignore deletion errors
            pass

        result["elapsed_time"] = time.perf_counter() - start_time
        return result
