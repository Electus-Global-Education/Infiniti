# Import the Gemini SDK from Google
import google.generativeai as genai

# lru_cache is used for caching model instances to avoid redundant setup.
from functools import lru_cache
import os
import environ
import time
import base64   
from google.cloud import speech
from google.cloud.speech import RecognitionConfig, RecognitionAudio
from google.cloud import texttospeech
from fini.utils import generate_query_embedding, retrieve_chunks_by_embedding
# # Load environment variables
# Get the base directory of the project (two levels up from this file)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Initialize environment handler
env = environ.Env()
env.read_env(os.path.join(BASE_DIR, ".env.gemini"))

GENAI_API_KEY = env("GENAI_API_KEY")
GOOGLE_APPLICATION_CREDENTIALS = env("GOOGLE_APPLICATION_CREDENTIALS")
GOOGLE_STT= env("GOOGLE_SPEECH_TO_TEXT_CREDENTIALS")
GOOGLE_TTS = env("GOOGLE_TEXT_TO_SPEECH_CREDENTIALS")

# Create a Speech-to-Text client.
speech_client = speech.SpeechClient()

# Create a Text-to-Speech client.
tts_client = texttospeech.TextToSpeechClient()

# Audio configuration constants
RATE = 16000         # Sample rate (Hz)
CHUNK = 1024         # Frames per buffer
FORMAT = "LINEAR16"  # Audio encoding format
CHANNELS = 1         # Mono

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

def generate_llm_response_from_chunks(
    base_prompt: str,
    user_query: str,
    user_role: str,
    chunks: list,
    model_name: str = "gemini-2.5-flash-preview-05-20",
    temperature: float = 0.4
) -> dict:
    """
    Composes a full prompt and sends it to the Gemini LLM.
    
    Parameters:
    - base_prompt: Instructions for the LLM
    - user_query: The user's actual question
    - user_role: Role of the user (helps guide the model)
    - chunks: List of (Document, score) tuples
    - model_name: Optional Gemini model to use
    - temperature: Optional generation temperature
    
    Returns:
    - Dictionary with the response and elapsed time
    """
    # Ensure valid model
    if model_name not in ALLOWED_MODELS:
        raise ValueError(f"Model '{model_name}' is not in the allowed list.")

    # Construct context
    context_text = "\n".join([doc.page_content for doc, _ in chunks]) if chunks else "No additional context found."

    # Build the full prompt
    full_prompt = (
        f"User Role: {user_role}\n"
        f"Instructions: {base_prompt}\n\n"
        f"Relevant Context:\n{context_text}\n\n"
        f"User Question: {user_query}"
    )

    try:
        start_time = time.time()
        genai.configure(api_key=os.getenv("GENAI_API_KEY"))
        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={"temperature": temperature}
        )
        response = model.generate_content(full_prompt)
        elapsed = round(time.time() - start_time, 2)
        return {
            "response": response.text.strip(),
            "elapsed": f"{elapsed}s"
        }
    except Exception as e:
        traceback.print_exc()
        raise RuntimeError(f"LLM generation failed: {str(e)}")


def generate_audio_response(text: str, language: str = "en-US", voice_name: str = "en-US-Journey-D") -> str:
    """
    Converts `text` to base64-encoded audio using Google TTS.

    :param text: Text to synthesize
    :param language: BCP-47 language tag (e.g., "en-US")
    :param voice_name: Google voice name
    :return: base64 string of LINEAR16 encoded audio
    """
    if not text.strip():
        return ""

    synthesis_input = texttospeech.SynthesisInput(text=text)

    voice_params = texttospeech.VoiceSelectionParams(
        language_code=language,
        name=voice_name,
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        speaking_rate=1.0,
        pitch=0.0,
        sample_rate_hertz=RATE
    )

    try:
        start = time.time()
        response = tts_client.synthesize_speech(
            input=synthesis_input,
            voice=voice_params,
            audio_config=audio_config
        )
        elapsed = time.time() - start
        print(f"[TTS] Synthesized in {elapsed:.2f} seconds.")

        return base64.b64encode(response.audio_content).decode("utf-8")

    except Exception as e:
        print(f"[TTS Error] {e}")
        return ""

def transcribe_audio_response(
    audio_b64: str,
    language: str = "en-US"
) -> str:
    """
    Converts a base64‐encoded audio blob into text via Google STT.
    Autodetects common encodings (LINEAR16, MP3, OGG_OPUS, FLAC).
    Returns the concatenated transcript, or empty string if nothing recognized.
    """
    if not audio_b64.strip():
        return ""

    # Decode the base64 payload
    audio_content = base64.b64decode(audio_b64)

    # Autodetect common magic bytes
    if audio_content.startswith(b'ID3') or audio_content[:2] == b'\xFF\xFB':
        encoding = RecognitionConfig.AudioEncoding.MP3
    elif audio_content.startswith(b'OggS'):
        encoding = RecognitionConfig.AudioEncoding.OGG_OPUS
    elif audio_content[:4] == b'fLaC':
        encoding = RecognitionConfig.AudioEncoding.FLAC
    else:
        # Default to WAV PCM LINEAR16
        encoding = RecognitionConfig.AudioEncoding.LINEAR16

    audio = RecognitionAudio(content=audio_content)
    config = RecognitionConfig(
        encoding=encoding,
        sample_rate_hertz=RATE,
        language_code=language,
        audio_channel_count=CHANNELS,
    )

    start = time.time()
    try:
        response = speech_client.recognize(config=config, audio=audio)
    except InvalidArgument as e:
        # e.g. “Specify MP3 encoding…” or sample_rate_mismatch
        print(f"[STT InvalidArgument] {e}")
        return ""
    except Exception as e:
        print(f"[STT Error] {e}")
        return ""
    elapsed = time.time() - start
    print(f"[STT] Recognized {len(response.results)} segments in {elapsed:.2f}s")

    # Join all top‐alternative transcripts
    transcripts = [
        result.alternatives[0].transcript
        for result in response.results
        if result.alternatives
    ]
    return " ".join(transcripts)