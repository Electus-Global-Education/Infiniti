from django.urls import path
from .views import test_vector_query
from django.urls import path
from .views import get_query_embedding_view as get_query_embedding
from .views import retrieve_top_chunks,YouTubeTranscriptAPIView, ProcessVideoChunksAPIView, CheckTaskStatusAPIView, ProcessBoclipsChunksAPIView, CheckBoclipsTaskStatusAPIView, UploadDocumentAPIView, CheckDocumentTaskStatusAPIView


urlpatterns = [
    #path("test-query/", test_vector_query, name="test_vector_query"),
    path("embedding/", get_query_embedding),
    path("chunks/", retrieve_top_chunks, name="retrieve_top_chunks"),
    path("get-YTtranscripts/", YouTubeTranscriptAPIView.as_view(), name="get-YTtranscripts"),
    # Enqueue chunking/embedding → returns Celery task IDs for processing:
    path("vector/YTprocess-chunks/", ProcessVideoChunksAPIView.as_view(), name="YTprocess-chunks"),
    # Check Celery task status by ID:
    path("vector/YTtask-status/", CheckTaskStatusAPIView.as_view(), name="YTtask-status"),
    path("vector/process-boclips-chunks/", ProcessBoclipsChunksAPIView.as_view(), name="process-boclips-chunks"),
    path("vector/boclips-task-status/", CheckBoclipsTaskStatusAPIView.as_view(), name="boclips-task-status"),
    path("vector/upload-document/", UploadDocumentAPIView.as_view(), name="upload-document"),
    path("vector/check-document-task/", CheckDocumentTaskStatusAPIView.as_view(), name="check-document-task"),
    
    
]
