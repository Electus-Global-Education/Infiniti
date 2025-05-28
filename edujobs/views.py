from django.shortcuts import render

# Create your views here.
import os
import google.generativeai as genai
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
import environ
from celery import shared_task

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = environ.Env()
env.read_env(os.path.join(BASE_DIR, ".env.gemini"))  # or any relevant file

API_KEY = env("GENAI_API_KEY")
MODEL = env("GEMINI_MODEL")
TEMPERATURE = float(env("GEMINI_TEMPERATURE"))
#print(f"Using Gemini model: {MODEL} with temperature: {TEMPERATURE}")

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
    """
    Synchronous API endpoint to handle chat prompts and return responses.

    This is typically used when immediate feedback is needed, such as in
    real-time chat features for educational support or job queries.

    Request Body:
    - prompt (str): The input question or message from the user.

    Returns:
    - 200 OK with the generated response text.
    - 400 Bad Request if the prompt is missing.
    - 500 Internal Server Error if something goes wrong with Gemini.
    """

    # Extract and clean the prompt from the POST data.
    prompt = request.data.get("prompt", "").strip()
    # If prompt is empty, return a 400 error.
    if not prompt:
        return Response({"error": "Prompt is required."}, status=400)

    try:
        # Use Gemini to generate a response based on the prompt.
        result = gemini.generate_content(prompt)
        answer = result.text.strip()
        # mock_task_id = str(uuid.uuid4())  # Generate a random task ID
        return Response({
            # "task_id": mock_task_id,
            "response": answer
        })
    except Exception as e:
        # Return a 500 error if Gemini fails to generate a response.
        return Response({"error": f"Gemini error: {str(e)}"}, status=500)
