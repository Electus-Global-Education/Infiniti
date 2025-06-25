
from django.urls import path
from .views import ImpactAnalysisAPIView

urlpatterns = [
    path('analyze/',ImpactAnalysisAPIView.as_view(),name='impact-analysis'),
]
