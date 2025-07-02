# fini/utils.py
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
from baserag.utils import generate_query_embedding, retrieve_chunks_by_embedding, fetch_multiple_transcripts, preprocess_text, create_semantic_chunks, extract_video_id, fetch_youtube_title, fetch_youtube_transcript, get_boclips_title, get_boclips_metadata, get_boclips_transcript, _extract_boclips_id, get_boclips_access_token
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



@shared_task
def process_video_chunks_task(video_url: str) -> Dict[str, object]:

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
def process_boclips_video_task(video_ref: str) -> Dict[str, object]:
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