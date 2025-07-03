# edujob/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from core.utils import generate_gemini_response, ALLOWED_MODELS, DEFAULT_MODEL, DEFAULT_TEMPERATURE
from rest_framework import status
from celery.result import AsyncResult
from edujobs.tasks import generate_edujob_chat_task


class ChatBotAPIView(APIView):
    """
    This endpoint takes a text prompt as input and returns a model-generated response. It supports optional parameters to control the model used and the randomness of the output (temperature). Primarily used for educational, conversational, or generative language tasks.

### Request Headers:
- **Content-Type**: `application/json`
- **Authorization**: `Api-Key <your_api_key>`

### Request Body (JSON):
- **prompt** (`str`, required):  
  The input text prompt you want the model to generate a response for.  
  *Example*: `"Tell me about Imran Khan? Write a short paragraph."`

- **model_name** (`str`, optional):  
  The name of the model to use. If not provided, the system will use the default model.  
  *Example*: `"gemini-2.5-flash-preview-05-20"`

- **temperature** (`float`, optional):  
  Controls the randomness of the output. Values range from `0.0` (deterministic) to `1.0` (very random).  
  *Example*: `0.7`

### Example Request Body (JSON):

```json
{
  "prompt": "Tell me about electus education global. Write a short paragraph.", 
  "model_name": "gemini-2.5-flash" (optional),
  "temperature": 0.4 (optional)
}
### Response 200 OK (JSON): 
Returns a JSON object containing the generated response from the model.

```json
{
  "response": "Electus Education Global is an international education company focused on providing educational opportunities and pathways for students....."
}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        prompt = request.data.get("prompt", "").strip()
        model_name = request.data.get("model", "").strip()
        temperature = request.data.get("temperature")

        if not prompt:
            return Response({"error": "Prompt is required."}, status=400)

        result = generate_gemini_response(
            prompt=prompt,
            model_name=model_name,
            temperature=temperature
        )

        return Response({
            #"used_model": model_name if model_name in ALLOWED_MODELS else DEFAULT_MODEL,
           # "used_temperature": temperature if temperature else DEFAULT_TEMPERATURE,
            "response": result["response"],
            #"timing": result["elapsed"]
        })

class EduJobChatAPIView(APIView):
    """
    This endpoint takes a text prompt as input and returns a model-generated response. It supports optional parameters to control the model used and the randomness of the output (temperature). Primarily used for educational, conversational, or generative language tasks.

### Request Headers:
- **Content-Type**: `application/json`
- **Authorization**: `Api-Key <your_api_key>`

### Request Body (JSON):
- **prompt** (`str`, required):  
  The input text prompt you want the model to generate a response for.  
  *Example*: `"Tell me about Imran Khan? Write a short paragraph."`

- **model_name** (`str`, optional):  
  The name of the model to use. If not provided, the system will use the default model.  
  *Example*: `"gemini-2.5-flash-preview-05-20"`

- **temperature** (`float`, optional):  
  Controls the randomness of the output. Values range from `0.0` (deterministic) to `1.0` (very random).  
  *Example*: `0.7`

### Example Request Body (JSON):

```json
{
  "prompt": "Tell me about electus education global. Write a short paragraph.", 
  "model_name": "gemini-2.5-flash" (optional),
  "temperature": 0.4 (optional)
}
### Response 200 OK (JSON): 
Returns a JSON object containing the generated response from the model.

```json
{
  "response": "Electus Education Global is an international education company focused on providing educational opportunities and pathways for students....."
}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        prompt = request.data.get("prompt", "").strip()
        model_name = request.data.get("model", "").strip()
        temperature = request.data.get("temperature")

        if not prompt:
            return Response({"detail": "Prompt is required."}, status=status.HTTP_400_BAD_REQUEST)

        # enqueue
        task = generate_edujob_chat_task.delay(prompt, model_name, temperature)
        return Response({"task_id": task.id}, status=status.HTTP_202_ACCEPTED)

class EduJobChatResultAPIView(APIView):
    """
    This endpoint retrieves the status and final result of a previously submitted EduJob chat generation task.  
    It helps track the progress of asynchronous tasks submitted for edujob generation.

### Request Headers:
- **Content-Type**: `application/json`
- **Authorization**: `Api-Key <your_api_key>`

### Request Body (JSON):
- **task_id** (`str`, required):  
  The unique identifier of the task returned when the chat generation request was initially submitted.  
  *Example*: `"e4b4b03e-81b0-4c67-94c0-6010af0beaf5"`

### Example Request Body (JSON):
```json
{
  "task_id": "e4b4b03e-81b0-4c67-94c0-6010af0beaf5"
}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        task_id = request.data.get("task_id", "").strip()
        if not task_id:
            return Response(
                {"detail": "The 'task_id' field is required in the request body."},
                status=status.HTTP_400_BAD_REQUEST
            )

        async_result = AsyncResult(task_id, app=generate_edujob_chat_task.app)

        if async_result.state in ("PENDING", "RECEIVED", "STARTED"):
            return Response({"status": async_result.state})

        if async_result.successful():
            data = async_result.result  # dict from the task
            return Response({"status": "SUCCESS", **data})

        if async_result.failed():
            return Response({
                "status": "FAILURE",
                "error": str(async_result.result)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"status": async_result.state})