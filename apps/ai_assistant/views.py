import os
import tempfile
import logging

from django.conf import settings
from django.db import DatabaseError, transaction
from django.db.models import Q
from rest_framework import generics, serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, inline_serializer

from common.permissions import CanManageAIAssistant
from .exceptions import AssistantError
from .models import AISettings, AISettingsAuditLog, AssistantQuestion
from .serializers import (
    AISettingsSerializer, AssistantChatSerializer, AssistantQuestionSerializer,
    TechnicalAnalysisSerializer,
)
from .services import AssistantService


logger = logging.getLogger(__name__)


class AssistantQuestionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    allowed_page_sizes = {10, 20, 50, 100}

    def get_page_size(self, request):
        raw = request.query_params.get(self.page_size_query_param)
        if raw in (None, ""):
            return self.page_size
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError({"page_size": "Use 10, 20, 50 or 100."}) from exc
        if value not in self.allowed_page_sizes:
            raise serializers.ValidationError({"page_size": "Use 10, 20, 50 or 100."})
        return value


def archive_question(user, question, client_message_id=""):
    try:
        if client_message_id:
            record, _ = AssistantQuestion.objects.get_or_create(
                user=user,
                client_message_id=client_message_id,
                defaults={"question": question},
            )
            return record
        return AssistantQuestion.objects.create(user=user, question=question)
    except (DatabaseError, ValueError, TypeError) as exc:
        logger.error(
            "Assistant question archive failed user_id=%s error_type=%s",
            user.pk,
            type(exc).__name__,
        )
        return None


def update_question_provider_status(record, *, succeeded, status_code=None):
    if not record:
        return
    try:
        AssistantQuestion.objects.filter(pk=record.pk).update(
            provider_succeeded=succeeded,
            provider_status_code=status_code,
        )
    except (DatabaseError, ValueError, TypeError) as exc:
        logger.error(
            "Assistant question status update failed record_id=%s error_type=%s",
            record.pk,
            type(exc).__name__,
        )


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
        messages = serializer.validated_data["messages"]
        question = next(
            (item["content"] for item in reversed(messages) if item["role"] == "user"),
            None,
        )
        record = archive_question(
            request.user,
            question,
            serializer.validated_data.get("client_message_id", ""),
        ) if question else None
        try:
            answer, usage = AssistantService.financial(request.user, messages)
        except AssistantError as exc:
            update_question_provider_status(
                record,
                succeeded=False,
                status_code=exc.provider_status_code,
            )
            raise
        update_question_provider_status(record, succeeded=True, status_code=200)
        return Response({"success": True, "answer": answer, "usage": usage})


class AssistantQuestionListView(generics.ListAPIView):
    permission_classes = [CanManageAIAssistant]
    serializer_class = AssistantQuestionSerializer
    pagination_class = AssistantQuestionPagination

    @extend_schema(parameters=[
        OpenApiParameter("page", int, required=False),
        OpenApiParameter("page_size", int, required=False, enum=[10, 20, 50, 100]),
        OpenApiParameter("search", str, required=False),
        OpenApiParameter("ordering", str, required=False, enum=["created_at", "-created_at"]),
    ])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = AssistantQuestion.objects.select_related("user")
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(question__icontains=search)
                | Q(user__username__icontains=search)
                | Q(user__phone__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )
        ordering = self.request.query_params.get("ordering", "-created_at")
        if ordering not in {"created_at", "-created_at"}:
            raise serializers.ValidationError(
                {"ordering": "Use created_at or -created_at."}
            )
        return queryset.order_by(ordering, "-id" if ordering.startswith("-") else "id")


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
