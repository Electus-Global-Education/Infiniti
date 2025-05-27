from django.shortcuts import render

# Create your views here.
import os
import google.generativeai as genai
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from dotenv import load_dotenv
from celery import shared_task

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env_gemini'))

API_KEY = os.getenv("GENAI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL")
TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE"))

# Configure Gemini
try:
    genai.configure(api_key=API_KEY)
except Exception:
    pass

gemini = genai.GenerativeModel(model_name=MODEL, generation_config={"temperature": TEMPERATURE})

@shared_task
def generate_response_async(prompt):
    try:
        result = gemini.generate_content(prompt)
        return result.text.strip()
    except Exception as e:
        return f"Error: {e}"

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_view(request):
    prompt = request.data.get("prompt", "").strip()
    if not prompt:
        return Response({"error": "Prompt is required."}, status=400)

    try:
        result = gemini.generate_content(prompt)
        answer = result.text.strip()
        # mock_task_id = str(uuid.uuid4())  # Generate a random task ID
        return Response({
            # "task_id": mock_task_id,
            "response": answer
        })
    except Exception as e:
        return Response({"error": f"Gemini error: {str(e)}"}, status=500)
