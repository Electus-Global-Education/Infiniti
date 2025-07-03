from django.urls import path
from .views import EduJobChatAPIView, EduJobChatResultAPIView, ChatBotAPIView

urlpatterns = [
    # path("chat/", chat_view, name="chat"),
    path("chat/", ChatBotAPIView.as_view(), name="chat"),
    path("generate/", EduJobChatAPIView.as_view(), name="edujob_chat"),
    path('generate-result/', EduJobChatResultAPIView.as_view(), name='edujob-chat-result'),
]
