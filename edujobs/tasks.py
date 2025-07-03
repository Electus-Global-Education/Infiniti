# edujob/tasks.py
import time
from celery import shared_task
from core.utils import generate_gemini_response, ALLOWED_MODELS, DEFAULT_MODEL, DEFAULT_TEMPERATURE

@shared_task(bind=True)
def generate_edujob_chat_task(self, prompt: str, model_name: str, temperature: float):
    """
    Celery task to call the chat LLM and return its response.
    Returns a dict with keys: response, model, temperature, elapsed.
    """
    # enforce defaults
    model = model_name if model_name in ALLOWED_MODELS else DEFAULT_MODEL
    temp = temperature if temperature is not None else DEFAULT_TEMPERATURE

     # 2) Time the LLM invocation
    start = time.perf_counter()

    # call into your core util
    result = generate_gemini_response(prompt=prompt, model_name=model, temperature=temp)
    elapsed = time.perf_counter() - start
    return {
        "response": result["response"],
        "model": model,
        "temperature": temp,
        "elapsed":    round(elapsed, 4),
    }
