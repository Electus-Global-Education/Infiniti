
from django.urls import path
from .views import ImpactAnalysisAPIView, ImpactAnalysisResultAPIView

urlpatterns = [
    path('analyze/',ImpactAnalysisAPIView.as_view(),name='impact-analysis'),
    path('analyze/result/',ImpactAnalysisResultAPIView.as_view(),name='impact-analysis-result'),

]
