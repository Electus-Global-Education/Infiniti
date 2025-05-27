from django.urls import path
from .views import get_query_embedding_view as get_query_embedding
from .views import retrieve_top_chunks

urlpatterns = [
    path("embedding/", get_query_embedding),
    path("chunks/", retrieve_top_chunks, name="retrieve_top_chunks"),
]
