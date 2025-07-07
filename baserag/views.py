# baserag/views.py
import os
import time
import traceback
import base64
from typing import Dict, Any
from uuid import uuid4
from django.conf import settings
from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from .connection import vector_store, embedding_model
from .serializers import VectorQueryRequestSerializer, VectorQueryResponseSerializer
from baserag.utils import generate_query_embedding, retrieve_chunks_by_embedding, fetch_multiple_transcripts, preprocess_text, create_semantic_chunks, extract_video_id, fetch_youtube_title, fetch_youtube_transcript, get_boclips_title, get_boclips_metadata, get_boclips_transcript, _extract_boclips_id, get_boclips_access_token, extract_text_from_pdf, extract_text_from_docx, process_video_chunks_task, process_boclips_video_task, process_document_task
SIMILARITY_THRESHOLD = 0.90
from django.core.files.storage import default_storage
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.views import APIView
from celery.result import AsyncResult
from core.utils import generate_gemini_response, generate_audio_response, transcribe_audio_response
#from fini.utils import generate_query_embedding, retrieve_chunks_by_embedding #generate_llm_response_from_chunks
from .utils import fetch_youtube_transcript, preprocess_text, process_video_chunks_task, process_boclips_video_task, process_document_task
from celery import shared_task
from fini.edujob_rec import retrieve_distinct_edujob_chunks, retrieve_by_keywords
from rest_framework import status




@extend_schema(
    tags=['Baserag - Utilities'],
    request=VectorQueryRequestSerializer,
    responses=VectorQueryResponseSerializer,
    description="Test endpoint to perform a semantic search query against the vector store."
)
@api_view(["POST"])
@permission_classes([IsAuthenticated]) # Or IsAdminUser if it's a dev-only tool
def test_vector_query(request):
    request_serializer = VectorQueryRequestSerializer(data=request.data)
    if not request_serializer.is_valid():
        return Response({"message":request_serializer.errors,
                        "code": status.HTTP_400_BAD_REQUEST},
                        status=status.HTTP_400_BAD_REQUEST)

    query = request_serializer.validated_data.get("query")
    
    try:
        embedding = embedding_model.embed_documents([query])[0]
        if not embedding:
            return Response({"message": "Failed to generate embedding",
                             "code": status.HTTP_400_BAD_REQUEST}, 
                             status=status.HTTP_400_BAD_REQUEST)

        start = time.time()
        results = vector_store.similarity_search_by_vector_with_score(embedding, k=5)
        elapsed = time.time() - start

        chunks = [
            {"score": score, "content": doc.page_content[:300]}
            for doc, score in results
        ]

        response_data = {
            "query": query,
            "elapsed": f"{elapsed:.2f}s",
            "results": chunks or []
        }
        
        response_serializer = VectorQueryResponseSerializer(data=response_data)
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.data)

    except Exception as e:
        return Response({"message": f"Vector store query failed: {str(e)}",
                         "code": status.HTTP_500_INTERNAL_SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def get_query_embedding_view(request):
    """
    Generate an embedding vector for a given natural language query.

This endpoint accepts a textual query and returns a high-dimensional vector (embedding) representation using a preconfigured embedding model. Useful for semantic search, similarity comparison, or input to downstream machine learning tasks.

---

**Prerequisites**  
    - The organization must be registered in the system.  
    - The client application must be registered with a valid redirect/Base URL.  
    - There must be at least one active staff user on the organization.  

    **Base URL**  
    For example, if your org “xyz” is registered with the system, the base URL will be:
    `https://app.xyz.ai/`,   
    
---

### 🔐 Authentication:
- Requires **api key <your_key>**:
  - Header: `Authorization: api key <your_key>`

---

### 📥 Request Headers:
- `Content-Type`: `application/json`
- `Authorization`: `api key <your_key>`
- `Orgin : https://app.xyz.ai/ `    
---


### 📦 Request Body (JSON):

- **query** (`str`, required):  
  A natural language query to be embedded.

#### ✅ Example Request:

```json
{
  "query": "What are educational jobs?"
}
    """
    query = request.data.get("query", "").strip()

    try:
        start = time.time()
        embedding = generate_query_embedding(query)
        elapsed = time.time() - start

        return Response({
            "query": query,
            "embedding": embedding,
            "elapsed": f"{elapsed:.2f} seconds"
        })
    except ValueError as ve:
        return Response({"message": str(ve),
                          "code": status.HTTP_400_BAD_REQUEST}, 
                             status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": f"Unexpected error: {str(e)}", "code": status.HTTP_500_INTERNAL_SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def get_query_embedding_view(request):
    """
    Generate an embedding vector for a given natural language query.

This endpoint accepts a textual query and returns a high-dimensional vector (embedding) representation using a preconfigured embedding model. Useful for semantic search, similarity comparison, or input to downstream machine learning tasks.

---

**Prerequisites**  
    - The organization must be registered in the system.  
    - The client application must be registered with a valid redirect/Base URL.  
    - There must be at least one active staff user on the organization.  

    **Base URL**  
    For example, if your org “xyz” is registered with the system, the base URL will be:
    `https://app.xyz.ai/`,   
    
---

### 🔐 Authentication:
- Requires **api key <your_key>**:
  - Header: `Authorization: api key <your_key>`

---

### 📥 Request Headers:
- `Content-Type`: `application/json`
- `Authorization`: `api key <your_key>`
- `Orgin : https://app.xyz.ai/ `    
---


### 📦 Request Body (JSON):

- **query** (`str`, required):  
  A natural language query to be embedded.

#### ✅ Example Request:

```json
{
  "query": "What are educational jobs?"
}
    """
    query = request.data.get("query", "").strip()

    try:
        start = time.time()
        embedding = generate_query_embedding(query)
        elapsed = time.time() - start

        return Response({
            "query": query,
            "embedding": embedding,
            "elapsed": f"{elapsed:.2f} seconds"
        })
    except ValueError as ve:
        return Response({"message": str(ve),"code": status.HTTP_400_BAD_REQUEST}, 
                             status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"message": f"Unexpected error: {str(e)}",
                          "code": status.HTTP_500_INTERNAL_SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def retrieve_top_chunks(request):
    """
    Accepts a user query, generates embeddings, performs a similarity search,
    and returns top relevant context chunks.
    """
    query = request.data.get("query", "").strip()
    if not query:
        return Response({"message": "Query is required.", "code": status.HTTP_400_BAD_REQUEST}, 
                             status=status.HTTP_400_BAD_REQUEST)

    try:
        # Step 1: Generate embedding
        embedding = generate_query_embedding(query)
        if not embedding:
            return Response({"message": "Failed to generate embedding.", "code": status.HTTP_500_INTERNAL_SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Step 2: Retrieve chunks
        elapsed, results = retrieve_chunks_by_embedding(embedding)

        # Format response
        chunks = [
            {"score": score, "content": doc.page_content[:500]}
            for doc, score in results
        ]

        return Response({
            "query": query,
            "elapsed": f"{elapsed:.2f} seconds",
            "results": chunks or "No relevant chunks found."
        })

    except Exception as e:
        return Response({"message": str(e), "code": status.HTTP_500_INTERNAL_SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class YouTubeTranscriptAPIView(APIView):
    """
    Fetch and clean YouTube video transcripts from a list of video URLs.

This endpoint accepts a list of YouTube video URLs, retrieves their transcripts (if available), preprocesses the text for downstream use (e.g. chunking or embedding), and returns both raw and cleaned transcripts. It also measures and returns timing metrics per video.

---

**Prerequisites**  
    - The organization must be registered in the system.  
    - The client application must be registered with a valid redirect/Base URL.  
    - There must be at least one active staff user on the organization.  

    **Base URL**  
    For example, if your org “xyz” is registered with the system, the base URL will be:
    `https://app.xyz.ai/`,   
    
---

### 🔐 Authentication:
- Requires **api key <your_key>**:
  - Header: `Authorization: api key <your_key>`

---

### 📥 Request Headers:
- `Content-Type`: `application/json`
- `Authorization`: `api key <your_key>`
- `Orgin : https://app.xyz.ai/ `    
---


### 📦 Request Body (JSON):

- **urls** (`list[str]`, required):  
  A list of valid YouTube video URLs to process.

#### ✅ Example Request:

```json
{
  "urls": [
    "https://youtu.be/dQw4w9WgXcQ",
    "https://youtu.be/2vjPBrBU-TM"
  ]
}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        if not isinstance(data, dict):
            return Response(
                {"error": "`{}` body must be a JSON object with a key 'urls'".format(data),
                 "code": status.HTTP_400_BAD_REQUEST},
                status=status.HTTP_400_BAD_REQUEST,
            )

        video_urls = data.get("urls")
        if not isinstance(video_urls, list):
            return Response(
                {"error": "`urls` must be a list of YouTube video URLs.",
                 "code": status.HTTP_400_BAD_REQUEST},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_texts = {}
        cleaned_transcripts = {}
        failed_urls = []
        elapsed_times = {}

        total_start = time.perf_counter()

        for url in video_urls:
            per_start = time.perf_counter()
            transcript_text = fetch_youtube_transcript(url)
            per_end = time.perf_counter()

            raw_texts[url] = transcript_text
            elapsed_times[url] = per_end - per_start

            if transcript_text is None:
                failed_urls.append(url)
            else:
                cleaned_transcripts[url] = preprocess_text(transcript_text)

        total_elapsed = time.perf_counter() - total_start

        return Response({
            "raw_texts": raw_texts,
            "cleaned_transcripts": cleaned_transcripts,
            "failed_urls": failed_urls,
            "elapsed_times": elapsed_times,
            "total_elapsed": total_elapsed,
            "message": "Transcript retrieval completed.",
            "code": status.HTTP_200_OK
        }, status=status.HTTP_200_OK)

class UploadDocumentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        📄 Upload Document for Background Processing (Embedding + Chunking)

This endpoint accepts a `.pdf` or `.docx` document upload via `multipart/form-data`. Once the file is validated and saved, a Celery task is triggered to process the document (e.g., split it into text chunks and embed them). A task ID is returned for tracking progress.

---

**Prerequisites**  
    - The organization must be registered in the system.  
    - The client application must be registered with a valid redirect/Base URL.  
    - There must be at least one active staff user on the organization.  

    **Base URL**  
    For example, if your org “xyz” is registered with the system, the base URL will be:
    `https://app.xyz.ai/`,   
    
---

### 🔐 Authentication:
- Requires **api key <your_key>**:
  - Header: `Authorization: api key <your_key>`

---

### 📥 Request Headers:
- `Content-Type`: `application/json`
- `Authorization`: `api key <your_key>`
- `Orgin : https://app.xyz.ai/ `    
---


### 📦 Request Body (form-data):

- `document` (**file**, required):  
  The `.pdf` or `.docx` file to upload and process. Only these two formats are supported.

---

### ✅ Example (cURL Upload):

```bash
curl -X POST http://localhost:8000/api/fini/upload-document/ \
  -H "Authorization: api key <your_token>" \
  -F "document=@/path/to/your_file.pdf"
        """
        # 1) Validate file presence
        uploaded_file = request.FILES.get("document")
        if not uploaded_file:
            return Response(
                {"message": "No file provided under 'document'.",
                 "code": status.HTTP_400_BAD_REQUEST},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2) Check extension
        filename = uploaded_file.name
        _, ext = os.path.splitext(filename.lower())
        if ext not in (".docx", ".pdf"):
            return Response(
                {"message": "Unsupported file type. Only .docx and .pdf are allowed.",
                 "code": status.HTTP_400_BAD_REQUEST},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3) Save file to MEDIA_ROOT with a random prefix to avoid collisions
        random_prefix = uuid4().hex
        safe_filename = f"{random_prefix}_{filename}"
        save_path = os.path.join(settings.MEDIA_ROOT, safe_filename)

        try:
            with default_storage.open(save_path, "wb+") as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
        except Exception as e:
            return Response(
                {"message": f"Failed to save uploaded file: {e}",
                 "code": status.HTTP_500_INTERNAL_SERVER_ERROR},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 4) Enqueue the Celery task, passing both file_path and original filename
        task = process_document_task.delay(save_path, filename)

        return Response(
            {
                "message": "Enqueued document for processing.",
                "task_id": task.id,
                "code": status.HTTP_202_ACCEPTED,
            },
            status=status.HTTP_202_ACCEPTED,
        )



class CheckDocumentTaskStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Check the status of a background document processing task.

This endpoint allows you to track the status of a Celery task submitted for document processing (e.g., parsing, chunking, embedding). It returns the current task state and, if completed, includes the result or error.

---

**Prerequisites**  
    - The organization must be registered in the system.  
    - The client application must be registered with a valid redirect/Base URL.  
    - There must be at least one active staff user on the organization.  

    **Base URL**  
    For example, if your org “xyz” is registered with the system, the base URL will be:
    `https://app.xyz.ai/`,   
    
---

### 🔐 Authentication:
- Requires **api key <your_key>**:
  - Header: `Authorization: api key <your_key>`

---

### 📥 Request Headers:
- `Content-Type`: `application/json`
- `Authorization`: `api key <your_key>`
- `Orgin : https://app.xyz.ai/ `    
---


### 📦 Request Body (JSON):

- **task_id** (`str`, required):  
  The ID of the Celery task previously submitted to process a document.

#### ✅ Example:

```json
{
  "task_id": "1707570c-5241-42f5-926f-e01d5d7c2c70"
}
        """
        data = request.data
        task_id = data.get("task_id")
        if not isinstance(task_id, str):
            return Response(
        {
            "message": "`task_id` must be provided as a string.",
            "code": status.HTTP_400_BAD_REQUEST
        },
        status=status.HTTP_400_BAD_REQUEST,
    )

        async_result = AsyncResult(task_id)
        response_data = {"task_id": task_id, "status": async_result.status}

        if async_result.ready():
            try:
                response_data["result"] = async_result.get(timeout=1)
            except Exception as e:
                response_data["message"] = str(e)
                response_data["code"] = status.HTTP_200_OK

        return Response(response_data, status=status.HTTP_200_OK)
class CheckBoclipsTaskStatusAPIView(APIView):
    """
    Check the status of a Boclips video processing task submitted to Celery.

This endpoint allows clients to query the current status of an asynchronous Celery task related to Boclips content processing. It returns the task's status and, if completed, includes the result or any error that occurred during processing.

---

**Prerequisites**  
    - The organization must be registered in the system.  
    - The client application must be registered with a valid redirect/Base URL.  
    - There must be at least one active staff user on the organization.  

    **Base URL**  
    For example, if your org “xyz” is registered with the system, the base URL will be:
    `https://app.xyz.ai/`,   
    
---

### 🔐 Authentication:
- Requires **api key <your_key>**:
  - Header: `Authorization: api key <your_key>`

---

### 📥 Request Headers:
- `Content-Type`: `application/json`
- `Authorization`: `api key <your_key>`
- `Orgin : https://app.xyz.ai/ `    
---


### 📦 Request Body (JSON):

- **task_id** (`str`, required):  
  The Celery task ID you received when the Boclips task was submitted.

#### ✅ Example Request:

```json
{
  "task_id": "04c2a931-a070-46f6-a42d-b9544d6b8354"
}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        task_id = data.get("task_id")
        if not isinstance(task_id, str):
            return Response(
            {
                "message": "`task_id` must be provided as a string.",
                "code": status.HTTP_400_BAD_REQUEST
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

        async_result = AsyncResult(task_id)
        if not async_result:
            return Response(
            {
                "message": f"No such task with id '{task_id}'.",
                "code": status.HTTP_404_NOT_FOUND
            },
            status=status.HTTP_404_NOT_FOUND,
        )
        response_data = {"task_id": task_id, "status": async_result.status}
        if async_result.ready():
            try:
                response_data["result"] = async_result.get(timeout=1)
            except Exception as e:
                response_data["message"] = str(e)
                response_data["code"] = status.HTTP_200_OK

        return Response(response_data, status=status.HTTP_200_OK)

class ProcessVideoChunksAPIView(APIView):
    """
Process a list of YouTube video URLs by queuing background tasks to extract, chunk, embed, and analyze content.

This endpoint accepts a list of YouTube video URLs and asynchronously queues a background task (via Celery) for each URL. These tasks handle video content chunking, embedding, and semantic processing (e.g., similarity checks). This is typically used for educational or knowledge-indexing pipelines.

### 🔐 Authentication:
- Requires API key authentication (`Authorization: Api-Key <your_api_key>`)

---

**Prerequisites**  
    - The organization must be registered in the system.  
    - The client application must be registered with a valid redirect/Base URL.  
    - There must be at least one active staff user on the organization.  

    **Base URL**  
    For example, if your org “xyz” is registered with the system, the base URL will be:
    `https://app.xyz.ai/`,   
    
---

### 🔐 Authentication:
- Requires **api key <your_key>**:
  - Header: `Authorization: api key <your_key>`

---

### 📥 Request Headers:
- `Content-Type`: `application/json`
- `Authorization`: `api key <your_key>`
- `Orgin : https://app.xyz.ai/ `    
---


### 📦 Request Body (JSON):

- **urls** (`list[str]`, required):  
  A list of valid YouTube video URLs to be processed.

#### ✅ Example:

```json
{
  "urls": [
    "https://youtu.be/aa528jbZDeI?si=fIONn5nt3xsKV45Q",
    "https://youtu.be/yadfklLi9tk?si=Pz7aPUxr2KLGf0nG"
  ]
}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        if not isinstance(data, dict):
            return Response(
                {"message": "Request body must be a JSON object with a key 'urls'.",
                 "code": status.HTTP_400_BAD_REQUEST},
                status=status.HTTP_400_BAD_REQUEST,
            )

        video_urls = data.get("urls")
        if not isinstance(video_urls, list):
            return Response(
                {"message": "`urls` must be a list of YouTube video URLs.",
                 "code": status.HTTP_400_BAD_REQUEST},
                status=status.HTTP_400_BAD_REQUEST,
            )

        task_map = {}
        for url in video_urls:
            # Enqueue one Celery task per URL
            async_result = process_video_chunks_task.delay(url)
            task_map[url] = async_result.id

        return Response(
            {
                "message": "Chunk/embedding tasks have been queued.",
                "code": status.HTTP_202_ACCEPTED,
                "tasks": task_map
                            },
            status=status.HTTP_202_ACCEPTED
        )


class CheckTaskStatusAPIView(APIView):
    """
    Check the status of a previously submitted video processing task.

This endpoint allows clients to check the current status of a background Celery task that was submitted using the `/api/fini/YTprocess-chunks/` endpoint. It returns the task status (e.g., `PENDING`, `STARTED`, `SUCCESS`, `FAILURE`) and includes the result if the task has finished.

---

**Prerequisites**  
    - The organization must be registered in the system.  
    - The client application must be registered with a valid redirect/Base URL.  
    - There must be at least one active staff user on the organization.  

    **Base URL**  
    For example, if your org “xyz” is registered with the system, the base URL will be:
    `https://app.xyz.ai/`,   
    
---

### 🔐 Authentication:
- Requires **api key <your_key>**:
  - Header: `Authorization: api key <your_key>`

---

### 📥 Request Headers:
- `Content-Type`: `application/json`
- `Authorization`: `api key <your_key>`
- `Orgin : https://app.xyz.ai/ `    
---

---

### 📦 Request Body (JSON):

- **task_id** (`str`, required):  
  The Celery task ID returned when the task was first enqueued.

#### ✅ Example Request:

```json
{
  "task_id": "fe9b0576-01b7-4878-9174-187eb9acb8f1"
}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        task_id = data.get("task_id")
        if not isinstance(task_id, str):
            return Response(
                {"message": "`task_id` must be provided as a string.",
                 "code": status.HTTP_400_BAD_REQUEST},
                status=status.HTTP_400_BAD_REQUEST,
            )

        async_result = AsyncResult(task_id)
        if not async_result:
            return Response(
                {"message": f"No such task with id '{task_id}'.",
                 "code": status.HTTP_404_NOT_FOUND},
                status=status.HTTP_404_NOT_FOUND,
            )

        response_data = {
            "task_id": task_id,
            "message": async_result.status,  # e.g. "PENDING", "STARTED", "SUCCESS", "FAILURE"
            "code": status.HTTP_200_OK
        }
        if async_result.ready():
            # If the task finished (either SUCCESS or FAILURE),
            # return its result or exception info
            try:
                response_data["result"] = async_result.get(timeout=1)
            except Exception as e:
                response_data["error"] = str(e)

        return Response(response_data, status=status.HTTP_200_OK)

class ProcessBoclipsChunksAPIView(APIView):
    """
    Enqueue background tasks to process Boclips videos by video ID.

This endpoint accepts a list of Boclips video IDs (or URLs), and for each one, queues a background Celery task to fetch the transcript (if any), chunk the content, and generate embeddings. It returns a map of input video IDs to their respective Celery task IDs.

---

**Prerequisites**  
    - The organization must be registered in the system.  
    - The client application must be registered with a valid redirect/Base URL.  
    - There must be at least one active staff user on the organization.  

    **Base URL**  
    For example, if your org “xyz” is registered with the system, the base URL will be:
    `https://app.xyz.ai/`,   
    
---

### 🔐 Authentication:
- Requires **api key <your_key>**:
  - Header: `Authorization: api key <your_key>`

---

### 📥 Request Headers:
- `Content-Type`: `application/json`
- `Authorization`: `api key <your_key>`
- `Orgin : https://app.xyz.ai/ `    
---

---

### 📦 Request Body (JSON):

- **video_ids** (`list[str]`, required):  
  A list of Boclips video URLs or IDs to process.

#### ✅ Example Request:

```json
{
  "video_ids": [
    "https://classroom.boclips.com/videos/shared/6080431a52688a3fcaf2ed26?referer=cf55155d-5f68-419c-97bd-c4298e8dea72&segmentEnd=60",
    "https://classroom.boclips.com/videos/shared/6432cf562154dd5afd5f4854?referer=cf55155d-5f68-419c-97bd-c4298e8dea72&segmentEnd=275"
  ]
}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        if not isinstance(data, dict):
            return Response(
                {"message": "Request body must be a JSON object with a key 'video_ids'.",
                 "code": status.HTTP_400_BAD_REQUEST},
                status=status.HTTP_400_BAD_REQUEST,
            )

        video_ids = data.get("video_ids")
        if not isinstance(video_ids, list):
            return Response(
                {"message": "`video_ids` must be a list of Boclips video IDs (strings).",
                 "code": status.HTTP_400_BAD_REQUEST},
                status=status.HTTP_400_BAD_REQUEST,
            )

        task_map = {}
        for vid in video_ids:
            async_result = process_boclips_video_task.delay(vid)
            task_map[vid] = async_result.id

        return Response(
            {
                "message": "Boclips chunk/embedding tasks have been queued.",
                "tasks": task_map,
                "code": status.HTTP_202_ACCEPTED
            },
            status=status.HTTP_202_ACCEPTED,
        )
