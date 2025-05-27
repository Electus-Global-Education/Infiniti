# fini/views.py
# from .models import Prompt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
import time

from fini.utils import generate_query_embedding  # import from utils
from fini.utils import generate_query_embedding, retrieve_chunks_by_embedding #generate_llm_response_from_chunks

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def get_query_embedding_view(request):
    query = request.data.get("query", "").strip()

    try:
        start = time.time()
        embedding = generate_query_embedding(query)
        elapsed = time.time() - start

        return Response({
            "query": query,
            "embedding": embedding,
            "elapsed": f"{elapsed:.2f} seconds"
        })
    except ValueError as ve:
        return Response({"error": str(ve)}, status=400)
    except Exception as e:
        return Response({"error": f"Unexpected error: {str(e)}"}, status=500)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def retrieve_top_chunks(request):
    """
    Accepts a user query, generates embeddings, performs a similarity search,
    and returns top relevant context chunks.
    """
    query = request.data.get("query", "").strip()
    if not query:
        return Response({"error": "Query is required."}, status=400)

    try:
        # Step 1: Generate embedding
        embedding = generate_query_embedding(query)
        if not embedding:
            return Response({"error": "Failed to generate embedding."}, status=500)

        # Step 2: Retrieve chunks
        elapsed, results = retrieve_chunks_by_embedding(embedding)

        # Format response
        chunks = [
            {"score": score, "content": doc.page_content[:500]}
            for doc, score in results
        ]

        return Response({
            "query": query,
            "elapsed": f"{elapsed:.2f} seconds",
            "results": chunks or "No relevant chunks found."
        })

    except Exception as e:
        return Response({"error": str(e)}, status=500)


# @api_view(["POST"])
# @permission_classes([IsAuthenticated])
# def query_with_llm_response(request):
#     """
#     Generates a response from LLM using user query, role, base prompt, and retrieved chunks.
#     """
#     query = request.data.get("query", "").strip()
#     # user_role = request.data.get("role", "").strip()
#     user_role = "Student"  # For testing, hardcoded role

#     if not query or not user_role:
#         return Response({"error": "Both query and role are required."}, status=400)

#     try:
#         # Step 1: Generate embedding
#         embedding = generate_query_embedding(query)

#         # Step 2: Retrieve context
#         _, chunks = retrieve_chunks_by_embedding(embedding)

#         # Step 3: Fetch base prompt from DB
#         try:
#             # base_prompt = Prompt.objects.get(role=user_role).text
#             base_prompt = "You are a helpful assistant. Please answer the user's question based on the provided context."
#         except Prompt.DoesNotExist:
#             return Response({"error": f"No base prompt configured for role '{user_role}'."}, status=404)

#         # Step 4: Generate LLM response
#         llm_response = generate_llm_response_from_chunks(base_prompt, query, user_role, chunks)

#         return Response({
#             "query": query,
#             "role": user_role,
#             "response": llm_response,
#             "context_used": [doc.page_content[:300] for doc, _ in chunks]
#         })

#     except Exception as e:
#         return Response({"error": str(e)}, status=500)