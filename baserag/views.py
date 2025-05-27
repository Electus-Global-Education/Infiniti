from django.shortcuts import render

# Create your views here.
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from baserag.connection import vector_store, embedding_model
import time

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def test_vector_query(request):
    query = request.data.get("query", "").strip()
    if not query:
        return Response({"error": "Query is required"}, status=400)

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

        return Response({
            "query": query,
            "elapsed": f"{elapsed:.2f}s",
            "results": chunks or "No results found"
        })

    except Exception as e:
        return Response({"error": f"Vector store query failed: {str(e)}"}, status=500)