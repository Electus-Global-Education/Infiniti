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
from baserag.utils import generate_query_embedding, retrieve_chunks_by_embedding #generate_llm_response_from_chunks
from baserag.utils import fetch_youtube_transcript, preprocess_text, process_video_chunks_task, process_boclips_video_task, process_document_task
from celery import shared_task
from fini.edujob_rec import retrieve_distinct_edujob_chunks, retrieve_by_keywords
from core.utils import generate_gemini_response, ALLOWED_MODELS, DEFAULT_MODEL, DEFAULT_TEMPERATURE

# Default fallback values
DEFAULT_ROLE = "Student"
DEFAULT_USER_ID = "none"
DEFAULT_BASE_PROMPT = (
    "You are an intelligent learning assistant that provides helpful, clear, and concise answers "
)



class FiniLLMChatView(APIView):
    """
    RAG-based LLM Chat API – generates contextual responses based on user queries, relevant document chunks, and role-based behavior.

This endpoint accepts a user query and optional parameters to guide how the query is handled and answered. The query is embedded, compared to a vector store of documents, and passed into a prompt for a Gemini-based LLM. Optionally, text-to-speech (TTS) can also be generated for the response.

---

### 🔐 Authentication:
- Requires **API key**:
  - Header: `Authorization: Api-Key <your_api_key>`

---

### 📥 Request Headers:
- `Content-Type`: `application/json`
- `Authorization`: `Api-Key <your_api_key>`

---

### 📦 Request Body (JSON):

#### Required:
- `user_query` (`string`):  
  The natural language input/question provided by the user.

#### Optional:
- `user_id` (`string`, default: `"anonymous_user"`):  
  A unique identifier for the user. Used for tracking or personalization.

- `user_role` (`string`, default: `"learner"`):  
  Role context for the user, which may influence tone or content.

- `base_prompt` (`string`, default: `"You are a helpful assistant."`):  
  Instructions injected into the system prompt for personality or control.

- `model_name` (`string`, default: `"gemini-1.5-flash"`):  
  Model version to use. Example: `"gemini-2.0-flash"`, `"gemini-pro"`.

- `temperature` (`float`, default: `0.5`):  
  Controls randomness in output generation (0 = deterministic, 1 = creative).

- `audio` (`boolean`, default: `false`):  
  If `true`, will trigger text-to-speech (TTS) generation. Returns `tts_task_id`.

---

### ✅ Example Request:

```json
{
  "user_query": "Tell me about Lifehub and Infiniti in two lines.", | (required) from user input
  "user_id": "user_123" (optional),
  "user_role": "student" (optional) default: "learner",
  "base_prompt": "reuired for tone, response type etc.", | (optional) default: "You are a helpful assistant.",
  "model_name": "gemini-2.5-flash" | (optional) default: "gemini-2.5-flash",
  "temperature": 0.2 (optional) | default: 0.5,
  "audio": false | 
}
    """
    permission_classes = [IsAuthenticated]
# Handle POST requests
    def post(self, request):
        start = time.time() # Start timer for performance metrics
        data = request.data  # Get JSON payload from the request

        #  Extract required field: user_query
        user_query = data.get("user_query", "").strip()
         # If user_query is missing or empty, return a 400 error
        if not user_query:
            return Response(
                {
                    "message": "user_query is required.",
                    "code": status.HTTP_400_BAD_REQUEST   # ← include code in body
                },
                status=status.HTTP_400_BAD_REQUEST      # ← still send 400 status
            )

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
            return Response(
                {
                    "message": str(e),
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class TTSStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
         TTS (Text-to-Speech) Task Status Checker

Checks the status of a background text-to-speech (TTS) generation task initiated earlier via the `rag_chat` endpoint.

If the task has completed successfully, it returns the generated audio in base64 format. If the task failed, it provides an error message. If still processing, returns status only.

---

### 🔐 Authentication:
- Requires **API Key** in the header:
  - `Authorization: Api-Key <your_api_key>`

---

### 📥 Request Headers:
- `Content-Type`: `application/json`
- `Authorization`: `Api-Key <your_api_key>`

---

### 📦 Request Body (JSON):

#### Required:
- `task_id` (`string`):  
  The Celery task ID returned from the TTS generation request.

---

### ✅ Example Request:

```json
{
  "task_id": "765ee02e-5906-4cce-bb63-fbafb8d6a0de"
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
    """
    🎙️ Submit Voice Query for LLM-Based Response

This endpoint accepts audio file mp3(via multipart upload) , processes it using a speech-to-text engine, and submits the transcribed query to a background LLM task. Returns a `task_id` for tracking.

---

### 🔐 Authentication:
- Requires **api key <your_key>**:
  - Header: `Authorization: api key <your_key>`

---

### 📥 Request Headers:
- `Content-Type`: `multipart/form-data` **or** `application/json`
- `Authorization`: `api key <your_key>`

---

### 📦 Request Body Options:

You must submit :
- `audio_file` (file) –mp3 preferred for `multipart/form-data`


#### Additional Parameters:
| Field         | Type     | Default      | Description |
|---------------|----------|--------------|-------------|
| `language`    | string   | `"en-US"`    | Language code for transcription ( `"en-US"` (required) |
| `user_id`     | string   | `"default value: anonymous_user"` | Custom user identifier | (optional)
| `user_role`   | string   | `"default value :learner"`  | Describes the user role for prompt personalization  | (Optional |default: learner)
| `base_prompt` | string   | `"Default value :You are a helpful assistant."` | Instruction prefix for LLM | (required)
| `model_name`  | string   | `"gemini-2.5-flash"` | LLM model to use | optional, default: `gemini-2.5-flash` |
| `temperature` | float    | `0.5`        | Randomness of response (0 = deterministic, 1 = creative) | optional, default: `0.5` |
| `audio`       | boolean  | `false`      | Whether to return synthesized voice response | (optional)  required for audio response, default: `false` |

---

### ✅ Example Request (multipart/form-data):

```http
POST /api/fini/voice-query/
Authorization: Api-Key <key>
Content-Type: multipart/form-data

Form-data:
- audio_file: voice_sample.mp3
- language: en-US
- user_id: user_001
- user_role: student
- model_name: gemini-2.0-pro
- temperature: 0.3
    """
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
    """
    📊 Get Status and Result of a Voice Query Task

This endpoint allows you to check the status and result of a voice query submitted earlier using the `/voice-query/` endpoint.  
It returns the current task state and, if completed, includes the transcribed text, generated response, and (optionally) the TTS task ID.

---

### 🔐 Authentication:
- Requires **API Key**:
  - Header: `Authorization: Api-Key <your_api_key>`

---

### 📥 Request Headers:
- `Content-Type`: `application/json`
- `Authorization`: `Api-Key <your_api_key>`

---

### 📦 Request Body:

```json
{
  "task_id": "166fc44e-20d6-48ee-a224-483f7101896c"
}
    """
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
    

class EdujobRecommendationAPIView(APIView):
    """
    Recommend Relevant Edujob Chunks Based on a Search Query and return top-k distinct chunks.

    **Endpoint:**  
    `POST /api/edujobs/recommend-chunks/`

    **Description:**  
    Accepts a natural language query and returns the most semantically similar chunks
    from your Edujobs corpus, ensuring distinctness by the `edujob_title` metadata field.

    **Request Body (application/json):**
    ```json
    {
      "query": "string",   // Required: text to search against the Edujobs chunks.
      "k": 10              // Optional: number of top chunks to return (default: 10).
    }
    
    OR
    {
      "keywords": ["seven wonders","gravity"],  // Required: keyword to search against the Edujobs chunks.
      "k": 8
    }
    ```

    **Response 200 OK:**
    ```json
    {
      "elapsed": 0.123,      // Time in seconds taken to compute recommendations.
      "recommendations": [
        {
          "chunk_id": "string",          // Unique ID of this chunk.
          "edujob_title": "string",      // The title under which this chunk was stored.
          "snippet": "string",           // A short excerpt of the chunk text.
          "score": 0.95,                 // Similarity score.
          "metadata": { … }              // Any other metadata you attached.
        },
        …
      ]
    }
    ```

    **Errors:**
    - 400 Bad Request: if `"query"` is missing or empty.
    - 401 Unauthorized: if the user is not authenticated.

    **Permissions:**  
    - `IsAuthenticated`
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs) -> Response:
        payload = request.data
        has_query = "query" in payload and payload["query"].strip() != ""
        has_keywords = "keywords" in payload and isinstance(payload["keywords"], list)

        if has_query and has_keywords:
            return Response(
                {"detail": "Please supply only one of 'query' or 'keywords'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not has_query and not has_keywords:
            return Response(
                {"detail": "You must supply either 'query' or 'keywords'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # parse k
        try:
            k = int(payload.get("k", 10))
        except (TypeError, ValueError):
            return Response({"detail": "'k' must be an integer."},
                            status=status.HTTP_400_BAD_REQUEST)

        # **either** single query…
        if has_query:
            q = payload["query"].strip()
            start = time.perf_counter()
            elapsed, recs = retrieve_distinct_edujob_chunks(query=q, top_k=k)
            elapsed = time.perf_counter() - start

        # **or** multiple keywords…
        else:
            keywords = payload["keywords"]
            if not all(isinstance(w, str) and w.strip() for w in keywords):
                return Response(
                    {"detail": "'keywords' must be a list of non-empty strings."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            start = time.perf_counter()
            elapsed, recs = retrieve_by_keywords(keywords=keywords, top_k=k)
            elapsed = time.perf_counter() - start

        return Response({
            "elapsed": round(elapsed, 4),
            "recommendations": recs
        })

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