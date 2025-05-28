from django.urls import path
from .views import EduJobChatAPIView

urlpatterns = [
    # path("chat/", chat_view, name="chat"),
    path("chat/", EduJobChatAPIView.as_view(), name="edujob_chat"),
]
