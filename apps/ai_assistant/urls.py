from django.urls import path

from .views import AISettingsView, AssistantChatView, TechnicalAnalysisView

urlpatterns = [
    path("admin/settings/", AISettingsView.as_view(), name="assistant-admin-settings"),
    path("chat/", AssistantChatView.as_view(), name="assistant-chat"),
    path("technical-analysis/", TechnicalAnalysisView.as_view(), name="assistant-technical-analysis"),
]
