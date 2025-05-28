# edujob/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from core.utils import generate_gemini_response, ALLOWED_MODELS, DEFAULT_MODEL, DEFAULT_TEMPERATURE

class EduJobChatAPIView(APIView):
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
