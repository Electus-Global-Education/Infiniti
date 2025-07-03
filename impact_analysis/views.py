from django.shortcuts import render

# Create your views here.
# impact_analysis/views.py

import time
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from core.utils import generate_gemini_response, ALLOWED_MODELS, DEFAULT_MODEL, DEFAULT_TEMPERATURE


class ImpactAnalysisAPIView(APIView):
    """
    POST /api/impact_analysis/analyze/

    Body JSON:
    {
      "instruction":   "<what analysis to perform>",
      "data":          "<raw data or narrative to analyze>",
      "model_name":    "<optional, LLM model to use>",
      "temperature":   <optional, sampling temperature>,
      "org_id":        "<optional, organization identifier>",
      "report_params": "<optional, extra instructions or sample report text>"
    }

    Returns 200:
    {
      "report": "<generated analysis narrative>",
      "meta": {
        "model_name":   "<used model>",
        "temperature":  <used temperature>,
        "org_id":       "<org id or null>",
        "report_params":"<echoed report_params>",
        "timing_sec": {
          "llm_generation": <llm call time>,
          "total":          <total request time>
        }
      }
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        start = time.time()

        instruction  = request.data.get("instruction", "").strip()
        data         = request.data.get("data")
        model_name   = request.data.get("model_name", DEFAULT_MODEL)
        report_params= request.data.get("report_params", "").strip()
        org_id       = request.data.get("org_id")

        # validate required fields
        if not instruction:
            return Response(
                {"detail": "The 'instruction' field is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if data is None or (isinstance(data, str) and not data.strip()):
            return Response(
                {"detail": "The 'data' field is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # parse temperature
        try:
            temperature = float(request.data.get("temperature", DEFAULT_TEMPERATURE))
        except (TypeError, ValueError):
            return Response(
                {"detail": "'temperature' must be a number."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # build prompt
        prompt_parts = []
        if org_id:
            prompt_parts.append(f"Organization ID: {org_id}")
        prompt_parts.append(f"Instruction: {instruction}")
        prompt_parts.append(f"Data:\n{data}")
        if report_params:
            prompt_parts.append(f"Report Parameters:\n{report_params}")
        prompt = "\n\n".join(prompt_parts) + "\n\nPlease generate the impact analysis report as instructed."

        # call LLM
        llm_start = time.time()
        llm_resp  = generate_gemini_response(prompt, model_name, temperature)
        report    = llm_resp.get("response", "[No response]")
        llm_time  = time.time() - llm_start

        total_time = time.time() - start

        return Response(
            {
                "report": report,
                "meta": {
                    "model_name":   model_name,
                    "temperature":  temperature,
                    "org_id":       org_id,
                    "report_params": report_params,
                    "timing_sec": {
                        "llm_generation": round(llm_time, 3),
                        "total":          round(total_time, 3),
                    }
                }
            },
            status=status.HTTP_200_OK
        )
