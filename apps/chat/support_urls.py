from django.urls import path

from .views import (
    SupportConversationView, SupportConversationMessageView,
    SupportConversationReadView, SupportQueueView,
    SupportTicketView, SupportConversationDetailView,
)

urlpatterns = [
    path("conversation/", SupportConversationView.as_view(), name="support-conversation"),
    path("conversations/", SupportQueueView.as_view(), name="support-queue"),
    path("conversations/<int:pk>/", SupportConversationDetailView.as_view(), name="support-conversation-detail"),
    path("conversations/<int:pk>/messages/", SupportConversationMessageView.as_view(), name="support-conversation-messages"),
    path("conversations/<int:pk>/read/", SupportConversationReadView.as_view(), name="support-conversation-read"),
    path("conversations/<int:pk>/ticket/", SupportTicketView.as_view(), name="support-ticket"),
]
