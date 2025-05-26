from django.urls import path
from .views import test_vector_query

urlpatterns = [
    path("test-query/", test_vector_query, name="test_vector_query"),
]
