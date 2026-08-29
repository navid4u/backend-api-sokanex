import os
import tempfile

from django.conf import settings
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer

from common.permissions import CanManageAIAssistant
from .models import AISettings, AISettingsAuditLog
from .serializers import AISettingsSerializer, AssistantChatSerializer, TechnicalAnalysisSerializer
from .services import AssistantService


class AISettingsView(APIView):
    permission_classes = [CanManageAIAssistant]

    @extend_schema(responses={200: AISettingsSerializer, 401: None, 403: None})
    def get(self, request):
        return Response(AISettingsSerializer(AISettings.load()).data)

    @extend_schema(request=AISettingsSerializer, responses={200: AISettingsSerializer, 400: None, 401: None, 403: None})
    def patch(self, request):
        instance = AISettings.load()
        serializer = AISettingsSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            changed = list(serializer.validated_data)
            updated = serializer.save(updated_by=request.user)
            if changed:
                AISettingsAuditLog.objects.create(ai_settings=updated, actor=request.user, changed_fields=changed)
        return Response(AISettingsSerializer(updated).data)


class AssistantChatView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "assistant_chat"

    @extend_schema(
        request=AssistantChatSerializer,
        responses={200: inline_serializer(name="AssistantChatResponse", fields={"success": serializers.BooleanField(), "answer": serializers.CharField(), "usage": serializers.DictField()}), 400: None, 401: None, 429: None, 502: None, 503: None},
        examples=[OpenApiExample("Financial question", value={"messages": [{"role": "user", "content": "چطور ریسک را مدیریت کنم؟"}]}, request_only=True)],
    )
    def post(self, request):
        serializer = AssistantChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        answer, usage = AssistantService.financial(request.user, serializer.validated_data["messages"])
        return Response({"success": True, "answer": answer, "usage": usage})


class TechnicalAnalysisView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "assistant_image"

    @extend_schema(request=TechnicalAnalysisSerializer, responses={200: inline_serializer(name="TechnicalAnalysisResponse", fields={"success": serializers.BooleanField(), "analysis": serializers.CharField(), "usage": serializers.DictField()}), 400: None, 401: None, 413: None, 422: None, 429: None, 502: None, 503: None})
    def post(self, request):
        serializer = TechnicalAnalysisSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image = serializer.validated_data["image"]
        os.makedirs(settings.ASSISTANT_TEMP_DIR, mode=0o700, exist_ok=True)
        path = None
        try:
            with tempfile.NamedTemporaryFile(dir=settings.ASSISTANT_TEMP_DIR, suffix=".upload", delete=False) as tmp:
                path = tmp.name
                for chunk in image.chunks():
                    tmp.write(chunk)
            with open(path, "rb") as stored:
                analysis, usage = AssistantService.technical(request.user, stored.read(), image.content_type)
        finally:
            if path and os.path.exists(path):
                os.remove(path)
        return Response({"success": True, "analysis": analysis, "usage": usage})
