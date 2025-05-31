from django.urls import path
from .views import get_query_embedding_view as get_query_embedding
from .views import retrieve_top_chunks, FiniLLMChatView, YouTubeTranscriptAPIView

urlpatterns = [
    path("embedding/", get_query_embedding),
    path("chunks/", retrieve_top_chunks, name="retrieve_top_chunks"),
    path("rag_chat/", FiniLLMChatView.as_view(), name="fini_chat_api"),
    path("get-YTtranscripts/", YouTubeTranscriptAPIView.as_view(), name="get-YTtranscripts"),
]
