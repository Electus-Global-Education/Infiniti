import google.generativeai as genai
from functools import lru_cache
import os
import environ
import time

# Load environment
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = environ.Env()
env.read_env(os.path.join(BASE_DIR, ".env.gemini"))

GENAI_API_KEY = env("GENAI_API_KEY")

# Constants
ALLOWED_MODELS = [
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-pro-preview-05-06"
]

DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_TEMPERATURE = 0.4

@lru_cache(maxsize=10)
def get_model_instance(model_name: str, temperature: float):
    genai.configure(api_key=GENAI_API_KEY)
    return genai.GenerativeModel(
        model_name=model_name,
        generation_config={"temperature": temperature}
    )

def generate_gemini_response(prompt: str, model_name: str = None, temperature: float = None) -> str:
    start_total = time.time()
    model_name = model_name if model_name in ALLOWED_MODELS else DEFAULT_MODEL
    try:
        temperature = float(temperature)
    except (TypeError, ValueError):
        temperature = DEFAULT_TEMPERATURE
    start_model = time.time()
    model = get_model_instance(model_name, temperature)
    end_model = time.time()

    start_gen = time.time()
    try:
        result = model.generate_content(prompt)
        gen_time = time.time() - start_gen
        total_time = time.time() - start_total
        return {
            "response": result.text.strip() if hasattr(result, "text") else "[No response]",
            # "elapsed": {
            #     "model_setup_sec": round(end_model - start_model, 3),
            #     "generation_sec": round(gen_time, 3),
            #     "total_sec": round(total_time, 3)
            # }
        }
    except Exception as e:
        return {
            "response": f"[Gemini error]: {str(e)}",
            # "elapsed": {
            #     "model_setup_sec": round(end_model - start_model, 3),
            #     "generation_sec": None,
            #     "total_sec": round(time.time() - start_total, 3)
            # }
        }
