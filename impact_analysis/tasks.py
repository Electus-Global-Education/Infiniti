# impact_analysis/tasks.py

import time
from celery import shared_task
from core.utils import generate_gemini_response, ALLOWED_MODELS, DEFAULT_MODEL, DEFAULT_TEMPERATURE

@shared_task(bind=True)
def generate_impact_analysis_task(
    self,
    instruction: str,
    data: str,
    model_name: str,
    temperature: float,
    org_id: str,
    report_params: str
) -> dict:
    """
    1. Build the same prompt you had in the sync view.
    2. Call the LLM via generate_gemini_response.
    3. Measure llm call time and total time.
    4. Return a dict matching your API response shape.
    """
    # Start measuring the total execution time of the task
    total_start = time.perf_counter()


     # Validate and apply defaults:
    # - Use the provided model_name only if it is in the allowed list; otherwise, fall back to DEFAULT_MODEL.
    # - Use the provided temperature if not None; otherwise, use DEFAULT_TEMPERATURE.
    model = model_name if model_name in ALLOWED_MODELS else DEFAULT_MODEL
    temp  = temperature if temperature is not None else DEFAULT_TEMPERATURE


    # Build the final prompt string for the LLM:
    # Include org_id if available, the instruction, data, and optional report_params.
    # Then add an explicit final instruction to generate the report.
    parts = []
    if org_id:
        parts.append(f"Organization ID: {org_id}")
    parts.append(f"Instruction: {instruction}")
    parts.append(f"Data:\n{data}")
    if report_params:
        parts.append(f"Report Parameters:\n{report_params}")
    prompt = "\n\n".join(parts) + "\n\nPlease generate the impact analysis report as instructed."

    # Measure the time specifically taken by the LLM call
    llm_start = time.perf_counter()
    resp      = generate_gemini_response(prompt, model, temp)
    llm_time  = time.perf_counter() - llm_start

     # Extract the report text from the LLM response; provide a fallback if missing
    report    = resp.get("response", "[No response]")

    # Measure total task runtime
    total_time = time.perf_counter() - total_start

    # Return a structured dictionary matching the expected API response format,
    # including metadata such as model used, temperature, org_id, report_params, and timing.
    return {
        "report": report,
        "meta": {
            "model_name":    model,
            "temperature":   temp,
            "org_id":        org_id,
            "report_params": report_params,
            "timing_sec": {
                "llm_generation": round(llm_time, 3),
                "total":          round(total_time, 3),
            }
        }
    }
