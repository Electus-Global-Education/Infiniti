# baserag/serializers.py
from rest_framework import serializers

class VectorQueryRequestSerializer(serializers.Serializer):
    """
    Validates the incoming request for the vector query test endpoint.
    """
    query = serializers.CharField(max_length=500, help_text="The text query to search for in the vector store.")

class VectorQueryResponseChunkSerializer(serializers.Serializer):
    """
    Represents a single chunk returned from the vector search.
    """
    score = serializers.FloatField()
    content = serializers.CharField()

class VectorQueryResponseSerializer(serializers.Serializer):
    """
    Represents the full response for the vector query test endpoint.
    """
    query = serializers.CharField()
    elapsed = serializers.CharField()
    results = VectorQueryResponseChunkSerializer(many=True)
