# fini/views.py
# from .models import Prompt
import os
import time
import traceback
import base64
from typing import Dict, Any
from uuid import uuid4
from django.conf import settings
from django.core.files.storage import default_storage
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from celery.result import AsyncResult
from core.utils import generate_gemini_response, generate_audio_response, transcribe_audio_response
from fini.utils import generate_query_embedding, retrieve_chunks_by_embedding #generate_llm_response_from_chunks
from .utils import fetch_youtube_transcript, preprocess_text, process_video_chunks_task, process_boclips_video_task, process_document_task
from celery import shared_task

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

        # 3) Check if audio is requested
        want_audio = bool(data.get("audio", False))

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
            # **Important**: extract the actual text reply from the LLM’s response dict
            text_reply = result.get("response", "[No response]")
            total_time = time.time() - start

            #Build base response payload (text + meta)
            payload = {
                "response": text_reply,
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
                        "total_sec": round(total_time, 3),
                    }
                }
            }

            # 7) If audio requested, generate and attach it
            if want_audio:
                # .delay() will immediately return a task AsyncResult
                tts_job = generate_tts_task.delay(text_reply)
                payload["tts_task_id"] = tts_job.id

            return Response(payload, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TTSStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        POST /api/fini/tts-status/
        Body: { "task_id": "<celery‐task‐id>" }

        Returns:
          {
            "task_id": "...",
            "status": "PENDING" | "SUCCESS" | "FAILURE",
            "audio": "<base64 string>"   # only if status == "SUCCESS"
            "error": "..."               # only if status == "FAILURE"
          }
        """
        task_id = request.data.get("task_id")
        if not isinstance(task_id, str):
            return Response(
                {"error": "`task_id` must be provided as a string."},
                status=status.HTTP_400_BAD_REQUEST
            )

        async_res = AsyncResult(task_id)
        response_data = {"task_id": task_id, "status": async_res.status}

        if async_res.ready():
            if async_res.successful():
                # The Celery task returned {"audio_b64": "..."}
                res = async_res.result or {}
                response_data["audio"] = res.get("audio_b64", "")
            else:
                # Celery task failed
                response_data["error"] = str(async_res.result)

        return Response(response_data, status=status.HTTP_200_OK)

@shared_task(name="fini.views.generate_tts_task",bind=True)
def generate_tts_task(self, text: str) -> dict:
    """
    Celery task that takes a text string, sends it to Google TTS,
    and returns a dict containing the base64‐encoded audio.
    """
    print(f"[generate_tts_task] Received text to speak: {repr(text)}")
    try:
        audio_b64 = generate_audio_response(text)
        print(f"[generate_tts_task] Audio length (bytes): {len(audio_b64)}")
        return {"audio_b64": audio_b64}
    except Exception as e:
        # If you want to automatically retry on failure:
        # raise self.retry(exc=e, countdown=5, max_retries=2)
        # Otherwise, just bubble up the exception so the client sees FAILURE:
        print(f"[generate_tts_task] ERROR: {e}")
        raise Exception(f"TTS task failed: {e}\n{traceback.format_exc()}")

# ----------------------------------------------------------------
# Celery Task: Full Voice-Query Pipeline
# ----------------------------------------------------------------
@shared_task(name="fini.tasks.process_voice_query_task")
def process_voice_query_task(
    audio_b64: str,
    language: str,
    user_id: str,
    user_role: str,
    base_prompt: str,
    model_name: str,
    temperature: float,
    want_audio: bool
) -> Dict[str, Any]:
    """
    1) Transcribe input audio → text;
    2) Embed and retrieve context;
    3) Generate LLM response;
    4) Optionally synthesize output audio;
    Returns full payload dict.
    """
    start_total = time.time()

    # 1) Speech-to-Text
    transcript = transcribe_audio_response(audio_b64, language)
    cleaned_query = transcript.strip()

    # 2) Embedding
    embed_start = time.time()
    embedding, cleaned = generate_query_embedding(cleaned_query)
    embed_time = time.time() - embed_start

    # 3) Retrieval
    chunk_time, chunks = retrieve_chunks_by_embedding(embedding)
    context_text = "\n".join([doc.page_content for doc, _ in chunks]) if chunks else "No relevant context found."
    context_instruction = (
        "Use the context if helpful. If not, rely on general knowledge."
    )

    # 4) Compose prompt
    prompt = (
        f"User ID: {user_id}\n"
        f"User Role: {user_role}\n"
        f"Instructions: {base_prompt}\n\n"
        f"Context Instructions: {context_instruction}\n\n"
        f"Context:\n{context_text}\n\n"
        f"User Question: {cleaned_query}"
    )

    # 5) LLM Generation
    llm_start = time.time()
    llm_resp = generate_gemini_response(prompt, model_name, temperature)
    text_reply = llm_resp.get("response", "[No response]")
    llm_time = time.time() - llm_start

    # 6) Optional TTS
    audio_out = None
    if want_audio:
        audio_out = generate_audio_response(text_reply)

    total_time = time.time() - start_total

    return {
        "transcript": cleaned_query,
        "response": text_reply,
        "audio_b64": audio_out or "",
        "meta": {
            "timing": {
                "stt_sec": round(embed_start - start_total, 3),
                "embedding_sec": round(embed_time, 3),
                "retrieval_sec": round(chunk_time, 3),
                "llm_sec": round(llm_time, 3),
                "total_sec": round(total_time, 3),
            },
            "model": model_name,
            "temperature": temperature,
        }
    }

# ----------------------------------------------------------------
# View: Submit Voice Query (accepts base64 or file upload)
# ----------------------------------------------------------------
class VoiceQuerySubmitView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, JSONParser]

    def post(self, request):
        # Determine audio payload: file upload vs base64 field
        audio_b64 = None
        if 'audio_file' in request.FILES:
            audio_file = request.FILES['audio_file']
            audio_bytes = audio_file.read()
            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        else:
            audio_b64 = request.data.get("audio_data")

        if not isinstance(audio_b64, str) or not audio_b64:
            return Response({"error": "Provide 'audio_file' or 'audio_data' (base64)."}, status=status.HTTP_400_BAD_REQUEST)

        language = request.data.get("language", "en-US")
        user_id = request.data.get("user_id", DEFAULT_USER_ID)
        user_role = request.data.get("user_role", DEFAULT_ROLE)
        base_prompt = request.data.get("base_prompt", DEFAULT_BASE_PROMPT)
        model_name = request.data.get("model_name", DEFAULT_MODEL)
        temperature = request.data.get("temperature", DEFAULT_TEMPERATURE)
        want_audio = bool(request.data.get("audio", False))

        task = process_voice_query_task.delay(
            audio_b64, language,
            user_id, user_role,
            base_prompt, model_name,
            temperature, want_audio
        )
        return Response({"message": "Voice query queued.", "task_id": task.id}, status=status.HTTP_202_ACCEPTED)

# ----------------------------------------------------------------
# View: Check Voice Query Status
# ----------------------------------------------------------------
class VoiceQueryStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        task_id = request.data.get("task_id")
        if not isinstance(task_id, str):
            return Response({"error": "`task_id` must be a string."}, status=status.HTTP_400_BAD_REQUEST)

        async_res = AsyncResult(task_id)
        data = {"task_id": task_id, "status": async_res.status}

        if async_res.ready():
            if async_res.successful():
                result = async_res.result or {}
                data.update(result)
            else:
                data["error"] = str(async_res.result)

        return Response(data, status=status.HTTP_200_OK)
    
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