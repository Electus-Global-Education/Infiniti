from django.urls import path
from .views import get_query_embedding_view as get_query_embedding
from .views import retrieve_top_chunks, FiniLLMChatView, YouTubeTranscriptAPIView, ProcessVideoChunksAPIView, CheckTaskStatusAPIView

urlpatterns = [
    path("embedding/", get_query_embedding),
    path("chunks/", retrieve_top_chunks, name="retrieve_top_chunks"),
    path("rag_chat/", FiniLLMChatView.as_view(), name="fini_chat_api"),
    path("get-YTtranscripts/", YouTubeTranscriptAPIView.as_view(), name="get-YTtranscripts"),
    # Enqueue chunking/embedding → returns Celery task IDs for processing:
    path("YTprocess-chunks/", ProcessVideoChunksAPIView.as_view(), name="YTprocess-chunks"),
    # Check Celery task status by ID:
    path("YTtask-status/", CheckTaskStatusAPIView.as_view(), name="YTtask-status"),
]
