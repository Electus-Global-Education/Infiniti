# baserag/views.py
from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from .connection import vector_store, embedding_model
from .serializers import VectorQueryRequestSerializer, VectorQueryResponseSerializer
import time

@extend_schema(
    tags=['Baserag - Utilities'],
    request=VectorQueryRequestSerializer,
    responses=VectorQueryResponseSerializer,
    description="Test endpoint to perform a semantic search query against the vector store."
)
@api_view(["POST"])
@permission_classes([IsAuthenticated]) # Or IsAdminUser if it's a dev-only tool
def test_vector_query(request):
    request_serializer = VectorQueryRequestSerializer(data=request.data)
    if not request_serializer.is_valid():
        return Response(request_serializer.errors, status=400)

    query = request_serializer.validated_data.get("query")
    
    try:
        embedding = embedding_model.embed_documents([query])[0]
        if not embedding:
            return Response({"error": "Failed to generate embedding"}, status=400)

        start = time.time()
        results = vector_store.similarity_search_by_vector_with_score(embedding, k=5)
        elapsed = time.time() - start

        chunks = [
            {"score": score, "content": doc.page_content[:300]}
            for doc, score in results
        ]

        response_data = {
            "query": query,
            "elapsed": f"{elapsed:.2f}s",
            "results": chunks or []
        }
        
        response_serializer = VectorQueryResponseSerializer(data=response_data)
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.data)

    except Exception as e:
        return Response({"error": f"Vector store query failed: {str(e)}"}, status=500)
