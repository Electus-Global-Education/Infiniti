# fini/views.py
# from .models import Prompt
import os
import time
from uuid import uuid4
from django.conf import settings
from django.core.files.storage import default_storage
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from celery.result import AsyncResult
from core.utils import generate_gemini_response
from fini.utils import generate_query_embedding, retrieve_chunks_by_embedding #generate_llm_response_from_chunks
from .utils import fetch_youtube_transcript, preprocess_text, process_video_chunks_task, process_boclips_video_task, process_document_task


# Default fallback values
DEFAULT_ROLE = "Student"
DEFAULT_USER_ID = "none"
DEFAULT_MODEL = "gemini-2.5-flash-preview-05-20"
DEFAULT_TEMPERATURE = 0.4
DEFAULT_BASE_PROMPT = (
    "You are an intelligent assistant that provides helpful, clear, and concise answers "
)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def get_query_embedding_view(request):
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
        return Response({"error": str(ve)}, status=400)
    except Exception as e:
        return Response({"error": f"Unexpected error: {str(e)}"}, status=500)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def retrieve_top_chunks(request):
    """
    Accepts a user query, generates embeddings, performs a similarity search,
    and returns top relevant context chunks.
    """
    query = request.data.get("query", "").strip()
    if not query:
        return Response({"error": "Query is required."}, status=400)

    try:
        # Step 1: Generate embedding
        embedding = generate_query_embedding(query)
        if not embedding:
            return Response({"error": "Failed to generate embedding."}, status=500)

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
        return Response({"error": str(e)}, status=500)


class FiniLLMChatView(APIView):
    permission_classes = [IsAuthenticated]
# Handle POST requests
    def post(self, request):
        start = time.time() # Start timer for performance metrics
        data = request.data  # Get JSON payload from the request

        #  Extract required field: user_query
        user_query = data.get("user_query", "").strip()
         # If user_query is missing or empty, return a 400 error
        if not user_query:
            return Response({"error": "user_query is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Extract optional parameters or use default values
        user_role = data.get("user_role", DEFAULT_ROLE)
        user_id = data.get("user_id", DEFAULT_USER_ID)
        model_name = data.get("model_name", DEFAULT_MODEL)
        temperature = data.get("temperature", DEFAULT_TEMPERATURE)
        base_prompt = data.get("base_prompt", DEFAULT_BASE_PROMPT)

        try:
            # ----------------------------- #
            # Step 1: Generate Embedding    #
            # ----------------------------- #
            embed_start = time.time()
            # Convert user query into a numerical vector and clean the query
            embedding, cleaned_query = generate_query_embedding(user_query)
            embed_time = time.time() - embed_start
            # --------------------------------------------- #
            # Step 2: Retrieve Relevant Chunks from Vector  #
            # --------------------------------------------- #

            # Fetch top-k most similar chunks (documents) based on embedding
            chunk_time, chunks = retrieve_chunks_by_embedding(embedding)

            # ---------------------------------- #
            # Step 3: Prepare Context for LLM   #
            # ---------------------------------- #

            # Join the page content from retrieved chunks to build context
            context_text = "\n".join([doc.page_content for doc, _ in chunks]) if chunks else "No relevant context found."
            # Inject clear instruction to LLM not to mention relevance even if context is not useful
            context_instruction = (
            "Use the context below if it is helpful. "
            "If the context does not answer the question, respond using your general knowledge. "
            "Do NOT mention anything about context being missing or irrelevant."
            )
            # --------------------------------------------- #
            # Step 4: Compose the Full Prompt for the LLM   #
            # --------------------------------------------- #

            # Format the prompt with user and context details for the LLM
            prompt = (
                f"User ID: {user_id}\n"
                f"User Role: {user_role}\n"
                f"Instructions: {base_prompt}\n\n"
                f"Relevant Context Instrustions: \n{context_instruction}\n\n"
                f"Relevant Context:\n{context_text}\n\n"
                f"User Question: {cleaned_query}"
            )

            # ----------------------------- #
            # Step 5: Call the LLM (Gemini) #
            # ----------------------------- #

            llm_start = time.time()
            # Send prompt to Gemini model and receive generated response
            result = generate_gemini_response(prompt, model_name, temperature)
            llm_time = time.time() - llm_start
            total_time = time.time() - start

            # Return final response with metadata and timing diagnostics
            return Response({
                "response": result.get("response", "[No response]"),
                "meta": {
                    "user_query": cleaned_query,
                    "context instruction": context_instruction,
                    "model": model_name,
                    "temperature": temperature,
                    "base_prompt": base_prompt,
                    "user_role": user_role,
                    "user_id": user_id,
                    "timing": {
                        "embedding_sec": round(embed_time, 3),
                        "retrieval_sec": round(chunk_time, 3),
                        "llm_generation_sec": round(llm_time, 3),
                        "total_sec": round(total_time, 3)
                    }
                }
            })

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class YouTubeTranscriptAPIView(APIView):
    """
    Accepts a POST with JSON body: { "urls": [ "<youtube_url1>", "<youtube_url2>", ... ] }
    Ensures the user is authenticated (permission_classes = [IsAuthenticated]).
    For each URL:
      - Measures how much time fetch_youtube_transcript(...) takes
      - If successful, includes it under "cleaned_transcripts"
      - If not, adds the URL to "failed_urls"
      - Also collects the raw transcript (or None) under "raw_texts"
    Responds with something like:
    {
      "raw_texts": {
        "<url1>": "<raw transcript text or None>",
        "<url2>": "<raw transcript text or None>",
        ...
      },
      "cleaned_transcripts": {
        "<url1>": "<cleaned transcript text>",
        ...
      },
      "failed_urls": [ "<urlX>", ... ],
      "elapsed_times": {
        "<url1>": 0.324,   # seconds
        "<url2>": 0.287,   # seconds
        ...
      },
      "total_elapsed": 1.012  # seconds (sum of all per-URL times)
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # 1) Parse & validate the incoming JSON
        data = request.data
        if not isinstance(data, dict):
            return Response(
                {"error": "`{}` body must be a JSON object with a key 'urls'".format(data)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        video_urls = data.get("urls")
        if not isinstance(video_urls, list):
            return Response(
                {"error": "`urls` must be a list of YouTube video URLs."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prepare containers
        raw_texts = {}         # Collect raw transcript (or None) for every URL
        cleaned_transcripts = {}
        failed_urls = []
        elapsed_times = {}

        total_start = time.perf_counter()

        # 2) Loop over each URL
        for url in video_urls:
            per_start = time.perf_counter()
            transcript_text = fetch_youtube_transcript(url)  # can be a string or None
            per_end = time.perf_counter()

            # 2a) Record raw result
            raw_texts[url] = transcript_text

            # 2b) Record elapsed time
            elapsed = per_end - per_start
            elapsed_times[url] = elapsed

            # 2c) Decide if it failed or succeeded
            if transcript_text is None:
                failed_urls.append(url)
            else:
                # Clean up the raw transcript before returning
                cleaned = preprocess_text(transcript_text)
                cleaned_transcripts[url] = cleaned

        total_end = time.perf_counter()
        total_elapsed = total_end - total_start

        # 4) Build and return the response payload
        response_payload = {
            "raw_texts": raw_texts,
            "cleaned_transcripts": cleaned_transcripts,
            "failed_urls": failed_urls,
            "elapsed_times": elapsed_times,
            "total_elapsed": total_elapsed,
        }
        return Response(response_payload, status=status.HTTP_200_OK)
class YouTubeTranscriptAPIView(APIView):
    """
    (Unchanged except for ensuring we’ve already used `fetch_youtube_transcript`
     + `preprocess_text` as before.)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        if not isinstance(data, dict):
            return Response(
                {"error": "`{}` body must be a JSON object with a key 'urls'".format(data)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        video_urls = data.get("urls")
        if not isinstance(video_urls, list):
            return Response(
                {"error": "`urls` must be a list of YouTube video URLs."},
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
        }, status=status.HTTP_200_OK)


class ProcessVideoChunksAPIView(APIView):
    """
    Accepts a POST with JSON body: { "urls": [ "<youtube_url1>", "<youtube_url2>", ... ] }.
    Requires authentication.

    For each URL:
      - We enqueue a Celery task (`process_video_chunks_task.delay(video_url)`).
      - Return immediately a JSON mapping of { url: <celery_task_id> }.

    The Celery worker(s) will process each URL one by one in the background,
    performing chunking → embedding → similarity check → insertion.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        if not isinstance(data, dict):
            return Response(
                {"error": "Request body must be a JSON object with a key 'urls'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        video_urls = data.get("urls")
        if not isinstance(video_urls, list):
            return Response(
                {"error": "`urls` must be a list of YouTube video URLs."},
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
                "tasks": task_map
            },
            status=status.HTTP_202_ACCEPTED
        )


class CheckTaskStatusAPIView(APIView):
    """
    (Optional helper endpoint)
    Given a POST with { "task_id": "<celery_task_id>" }, returns the task state
    and (if finished) the result dictionary from `process_video_chunks_task`.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        task_id = data.get("task_id")
        if not isinstance(task_id, str):
            return Response(
                {"error": "`task_id` must be provided as a string."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        async_result = AsyncResult(task_id)
        if not async_result:
            return Response(
                {"error": f"No such task with id '{task_id}'."},
                status=status.HTTP_404_NOT_FOUND,
            )

        response_data = {
            "task_id": task_id,
            "status": async_result.status,  # e.g. "PENDING", "STARTED", "SUCCESS", "FAILURE"
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
    POST { "video_ids": ["id1", "id2", ... ] }
    Requires authentication. Enqueues a separate Celery task per Boclips video ID.
    Responds with { video_id: task_id, ... } and 202 Accepted.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        if not isinstance(data, dict):
            return Response(
                {"error": "Request body must be a JSON object with a key 'video_ids'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        video_ids = data.get("video_ids")
        if not isinstance(video_ids, list):
            return Response(
                {"error": "`video_ids` must be a list of Boclips video IDs (strings)."},
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
            },
            status=status.HTTP_202_ACCEPTED,
        )


class CheckBoclipsTaskStatusAPIView(APIView):
    """
    POST { "task_id": "<celery_task_id>" }
    Returns { task_id, status, (result|error) } for a Boclips task.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        data = request.data
        task_id = data.get("task_id")
        if not isinstance(task_id, str):
            return Response(
                {"error": "`task_id` must be provided as a string."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        async_result = AsyncResult(task_id)
        if not async_result:
            return Response(
                {"error": f"No such task with id '{task_id}'."},
                status=status.HTTP_404_NOT_FOUND,
            )

        response_data = {"task_id": task_id, "status": async_result.status}
        if async_result.ready():
            try:
                response_data["result"] = async_result.get(timeout=1)
            except Exception as e:
                response_data["error"] = str(e)

        return Response(response_data, status=status.HTTP_200_OK)


class UploadDocumentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Expects a multipart/form-data POST with a single file under "document":
          - document: (file.obj, content_type either application/pdf or application/vnd.openxmlformats-officedocument.wordprocessingml.document)

        Returns:
          {
            "message": "Enqueued document for processing.",
            "task_id": "<celery-task-id>"
          }
        """
        # 1) Validate file presence
        uploaded_file = request.FILES.get("document")
        if not uploaded_file:
            return Response(
                {"error": "No file provided under 'document'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2) Check extension
        filename = uploaded_file.name
        _, ext = os.path.splitext(filename.lower())
        if ext not in (".docx", ".pdf"):
            return Response(
                {"error": "Unsupported file type. Only .docx and .pdf are allowed."},
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
                {"error": f"Failed to save uploaded file: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 4) Enqueue the Celery task, passing both file_path and original filename
        task = process_document_task.delay(save_path, filename)

        return Response(
            {
                "message": "Enqueued document for processing.",
                "task_id": task.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )

# fini/views.py  (append after UploadDocumentAPIView)

class CheckDocumentTaskStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Expects JSON body: { "task_id": "<celery-task-id>" }

        Returns:
          {
            "task_id": "<celery-task-id>",
            "status": "<PENDING|SUCCESS|FAILURE>",
            "result": { …same dict returned by process_document_task… }  # only if ready
          }
        """
        data = request.data
        task_id = data.get("task_id")
        if not isinstance(task_id, str):
            return Response(
                {"error": "`task_id` must be provided as a string."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        async_result = AsyncResult(task_id)
        response_data = {"task_id": task_id, "status": async_result.status}

        if async_result.ready():
            try:
                response_data["result"] = async_result.get(timeout=1)
            except Exception as e:
                response_data["error"] = str(e)

        return Response(response_data, status=status.HTTP_200_OK)



# @api_view(["POST"])
# @permission_classes([IsAuthenticated])
# def query_with_llm_response(request):
#     """
#     Generates a response from LLM using user query, role, base prompt, and retrieved chunks.
#     """
#     query = request.data.get("query", "").strip()
#     # user_role = request.data.get("role", "").strip()
#     user_role = "Student"  # For testing, hardcoded role

#     if not query or not user_role:
#         return Response({"error": "Both query and role are required."}, status=400)

#     try:
#         # Step 1: Generate embedding
#         embedding = generate_query_embedding(query)

#         # Step 2: Retrieve context
#         _, chunks = retrieve_chunks_by_embedding(embedding)

#         # Step 3: Fetch base prompt from DB
#         try:
#             # base_prompt = Prompt.objects.get(role=user_role).text
#             base_prompt = "You are a helpful assistant. Please answer the user's question based on the provided context."
#         except Prompt.DoesNotExist:
#             return Response({"error": f"No base prompt configured for role '{user_role}'."}, status=404)

#         # Step 4: Generate LLM response
#         llm_response = generate_llm_response_from_chunks(base_prompt, query, user_role, chunks)

#         return Response({
#             "query": query,
#             "role": user_role,
#             "response": llm_response,
#             "context_used": [doc.page_content[:300] for doc, _ in chunks]
#         })

#     except Exception as e:
#         return Response({"error": str(e)}, status=500)