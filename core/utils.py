# Import the Gemini SDK from Google
import google.generativeai as genai

# lru_cache is used for caching model instances to avoid redundant setup.
from functools import lru_cache
import os
import environ
import time

# # Load environment variables
# Get the base directory of the project (two levels up from this file)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Initialize environment handler
env = environ.Env()
env.read_env(os.path.join(BASE_DIR, ".env.gemini"))

GENAI_API_KEY = env("GENAI_API_KEY")

# Model configuration constants
# List of allowed Gemini model names to prevent misuse or invalid inputs
ALLOWED_MODELS = [
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-pro-preview-05-06"
]

#Fallback model to use if the user provides an invalid or missing model name
DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_TEMPERATURE = 0.4

# ------------------------------------------------
# Cached model instance factory using lru_cache
# ------------------------------------------------
# This function creates and caches a Gemini model instance based on the provided model name and temperature.
@lru_cache(maxsize=10)
def get_model_instance(model_name: str, temperature: float):
    """
    Get a cached instance of the Gemini model configured with the given temperature.

    Args:
        model_name (str): Name of the Gemini model to use.
        temperature (float): Generation temperature (controls randomness).

    Returns:
        genai.GenerativeModel: Configured model instance.
    """
    # Configure Gemini with the API key
    genai.configure(api_key=GENAI_API_KEY)

    # Return an instance of the configured model
    return genai.GenerativeModel(
        model_name=model_name,
        generation_config={"temperature": temperature}
    )

# -----------------------------------------------------
# Main utility function to generate a Gemini response
# -----------------------------------------------------

def generate_gemini_response(prompt: str, model_name: str = None, temperature: float = None) -> str:
    """
    Generate a response using the Gemini model.

    This function sets up the model, performs inference, and measures execution time.
    It safely handles defaults and error scenarios.

    Args:
        prompt (str): The input text to generate a response for.
        model_name (str, optional): The name of the model to use. Defaults to DEFAULT_MODEL.
        temperature (float, optional): Randomness parameter. Defaults to DEFAULT_TEMPERATURE.

    Returns:
        dict: A dictionary containing either the response or an error message.
    """
    # Start measuring total execution time
    start_total = time.time()
    # Validate model name against allowed list; use default if invalid
    model_name = model_name if model_name in ALLOWED_MODELS else DEFAULT_MODEL
    # Safely cast temperature to float; use default on failure
    try:
        temperature = float(temperature)
    except (TypeError, ValueError):
        temperature = DEFAULT_TEMPERATURE
    
    # Measure time taken to set up the model
    start_model = time.time()
    model = get_model_instance(model_name, temperature)
    end_model = time.time()

    start_gen = time.time()
    try:
        # Generate a response using the Gemini model
        result = model.generate_content(prompt)
        gen_time = time.time() - start_gen
        total_time = time.time() - start_total
        # Return the response text (if present), trimmed of whitespace
        return {
            "response": result.text.strip() if hasattr(result, "text") else "[No response]",
            # "elapsed": {
            #     "model_setup_sec": round(end_model - start_model, 3),
            #     "generation_sec": round(gen_time, 3),
            #     "total_sec": round(total_time, 3)
            # }
        }
    except Exception as e:
        # Handle any exceptions during generation
        return {
            "response": f"[Gemini error]: {str(e)}",
            # "elapsed": {
            #     "model_setup_sec": round(end_model - start_model, 3),
            #     "generation_sec": None,
            #     "total_sec": round(time.time() - start_total, 3)
            # }
        }
