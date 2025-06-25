# edujob/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from core.utils import generate_gemini_response, ALLOWED_MODELS, DEFAULT_MODEL, DEFAULT_TEMPERATURE

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
  "prompt": "Tell me about Imran Khan. Write a short paragraph.", 
  "model_name": "gemini-2.5-flash-preview-05-20" (optional),
  "temperature": 0.4 (optional)
}
### Response 200 OK (JSON): 
Returns a JSON object containing the generated response from the model.

```json
{
  "response": "Imran Khan is a former cricketer and the 22nd Prime Minister of Pakistan..."
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
