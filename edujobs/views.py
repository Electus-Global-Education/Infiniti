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

### Request Body (JSON):
- **prompt** (`str`, required):  
  The input text prompt you want the model to generate a response for.  
  *Example*: `"Tell me about Electus Education Global? Write a short paragraph."`

- **model_name** (`str`, optional, default: `gemini-2.5-flash`):  
  The name of the model to use. If not provided, the system will use the default model.  
  *Example*: `"gemini-2.5-flash-preview-05-20"`

- **temperature** (`float`, optional, `default: 0.5`):  
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
            return Response({"message": "Prompt is required.",
                              "code":    status.HTTP_400_BAD_REQUEST},  
                              status=status.HTTP_400_BAD_REQUEST
                              )

        result = generate_gemini_response(
            prompt=prompt,
            model_name=model_name,
            temperature=temperature
        )

        return Response({
            #"used_model": model_name if model_name in ALLOWED_MODELS else DEFAULT_MODEL,
           # "used_temperature": temperature if temperature else DEFAULT_TEMPERATURE,
            "response": result["response"],
            "message": "SUCCESS",
            "code": status.HTTP_200_OK,
            #"timing": result["elapsed"]
        })

class EduJobChatAPIView(APIView):
    """
    This endpoint takes a text prompt as input and returns a model-generated response. It supports optional parameters to control the model used and the randomness of the output (temperature). Primarily used for educational, conversational, or generative language tasks.

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

### Request Body (JSON):
- **prompt** (`str`, required):  
  The input text prompt you want the model to generate a response for.  
  *Example*: `""Tell me about Electus Education Global? Write a short paragraph."`

- **model_name** (`str`, optional, default: `gemini-2.5-flash`):  
  The name of the model to use. If not provided, the system will use the default model.  
  *Example*: `"gemini-2.5-flash-preview-05-20"`

- **temperature** (`float`, optional, `default: 0.5`):  
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
        # Extract optional fields:
        # - 'model_name': which LLM model to use; defaults applied later if empty
        # - 'temperature': controls creativity/randomness of the response
        model_name = request.data.get("model", "").strip()
        temperature = request.data.get("temperature")

        # Validate: prompt must be provided and not empty
        if not prompt:
            return Response({"message": "Prompt is required.",
                             "code": status.HTTP_400_BAD_REQUEST}, 
                             status=status.HTTP_400_BAD_REQUEST)

        # Enqueue the request to an asynchronous Celery task:
        # - generate_edujob_chat_task will handle calling the LLM and building the response.
        # - Returns a task_id that the client can use to check the result later.
        task = generate_edujob_chat_task.delay(prompt, model_name, temperature)

        # Respond with HTTP 202 Accepted and include the task_id
        return Response({"task_id": task.id,
                         "message":task.id,
                         "code":status.HTTP_202_ACCEPTED}, 
                         status=status.HTTP_202_ACCEPTED)

class EduJobChatResultAPIView(APIView):
    """
    This endpoint retrieves the status and final result of a previously submitted EduJob chat generation task.  
    It helps track the progress of asynchronous tasks submitted for edujob generation.

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
        # Extract and sanitize the 'task_id' field from the request JSON
        task_id = request.data.get("task_id", "").strip()
         # Validate: task_id must be provided; if missing, return 400 Bad Request
        if not task_id:
            return Response(
                {"message": "The 'task_id' field is required in the request body.",
                 "code": status.HTTP_400_BAD_REQUEST},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Initialize AsyncResult object to track the current state of the task
        async_result = AsyncResult(task_id, app=generate_edujob_chat_task.app)
        # Check the current state of the task:
        # If the task is waiting in queue, picked up, or currently running,
        # return the status so the client knows to keep polling.
        if async_result.state in ("PENDING", "RECEIVED", "STARTED"):
            return Response({"message": async_result.state,
                             "code": status.HTTP_202_ACCEPTED},
                            status=status.HTTP_202_ACCEPTED)

         # If the task completed successfully, return status "SUCCESS" and include the task's result data
        if async_result.successful():
            data = async_result.result  # dict from the task
            return Response({"message": "SUCCESS", **data,
                             "code": status.HTTP_200_OK},
                            status=status.HTTP_200_OK)

        # If the task failed, return status "FAILURE" and include the error message for transparency
        if async_result.failed():
            return Response({
                "message": "FAILURE",
                "error": str(async_result.result),
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        # Fallback: if the task is in an unexpected state, return its raw state
        return Response({"status": async_result.state})