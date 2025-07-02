from django.urls import path
from baserag.views import get_query_embedding_view as get_query_embedding
from .views import  FiniLLMChatView, TTSStatusView, VoiceQuerySubmitView, VoiceQueryStatusView, EdujobRecommendationAPIView

urlpatterns = [
    path("rag_chat/", FiniLLMChatView.as_view(), name="fini_chat_api"),
    path("tts-status/", TTSStatusView.as_view(), name="tts-status"),
    path('voice-query/', VoiceQuerySubmitView.as_view(), name='fini-voice-query'),
    path('voice-query-status/', VoiceQueryStatusView.as_view(), name='fini-voice-query-status'),
    path("edujob-rec/",EdujobRecommendationAPIView.as_view(),name="recommend-edujobs"),

]
