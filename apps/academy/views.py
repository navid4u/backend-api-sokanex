from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from rest_framework.exceptions import PermissionDenied, Throttled
from rest_framework.permissions import AllowAny
from django.conf import settings
from django.core import signing
from django.http import StreamingHttpResponse
import os
from common.serializers import EmptySerializer

from apps.accounts.models import User
from apps.accounts.market_access import market_access_v2_enabled, resolve_market_access
from common.content_access import restrict_queryset_for_user
from common.permissions import CanTeachAcademy

from .models import Course, CourseEnrollment, CoursePurchase, CourseSession, SessionProgress, Quiz, QuizAttempt
from .serializers import (
    CourseListSerializer,
    CourseSessionSerializer,
    CourseWriteSerializer,
    CourseEnrollmentSerializer,
    SessionProgressSerializer,
    QuizAttemptSerializer,
    QuizPublicSerializer,
    QuizWriteSerializer,
    CoursePurchaseSerializer,
)
from apps.activity.models import UserActivity
from apps.activity.services import ActivityService
from apps.wallet.models import Payment, PaymentProvider
from apps.wallet.providers import ADAPTERS, PaymentProviderError
from apps.wallet.services import WalletService


def can_manage_all_academy(user):
    return user.has_platform_permission(
        User.Permission.ACADEMY_MANAGE
    )


def can_edit_academy(user):
    return can_manage_all_academy(user) or user.has_platform_permission(
        User.Permission.ACADEMY_TEACH
    )


def manageable_courses(user):
    queryset = Course.objects.select_related("instructor")
    if can_manage_all_academy(user):
        return queryset
    return queryset.filter(instructor=user)


def visible_courses(user):
    queryset = Course.objects.filter(
        status=Course.Status.PUBLISHED
    ).select_related("instructor")
    if market_access_v2_enabled():
        # Unclassified legacy courses fail closed until an administrator
        # explicitly assigns their market. Legacy per-item flags stay stored.
        return queryset.filter(market__in=resolve_market_access(user).effective_markets)
    return restrict_queryset_for_user(queryset, user)


def assert_course_market_access(user, course):
    if not market_access_v2_enabled():
        return
    if can_manage_all_academy(user) or (
        user.pk == course.instructor_id
        and user.has_platform_permission(User.Permission.ACADEMY_TEACH)
    ):
        return
    if course.market not in resolve_market_access(user).effective_markets:
        raise PermissionDenied(detail={
            "code": "MARKET_ACCESS_REQUIRED",
            "market": course.market or None,
            "detail": "Access to this course market is required.",
        })


def session_lock_reason(session, user):
    if can_edit_academy(user) and manageable_courses(user).filter(pk=session.course_id).exists():
        return ""
    enrollment = CourseEnrollment.objects.filter(user=user, course=session.course).first()
    if not session.course.is_free:
        purchased = CoursePurchase.objects.filter(user=user, course=session.course).exists()
        if not purchased or not enrollment:
            return "Purchase and enroll in this course to access its content."
    elif not session.is_preview and not enrollment:
        return "Enroll in this course to access its content."
    if session.is_preview:
        return ""
    now = timezone.now()
    unlock_at = session.unlock_at or session.available_at
    if unlock_at and unlock_at > now:
        return "This session is not available yet."
    if enrollment:
        weekly_limit = session.course.weekly_session_limit
        monthly_limit = session.course.monthly_session_limit
        if weekly_limit and enrollment.session_progress.filter(updated_at__gte=now - timedelta(days=7)).count() >= weekly_limit:
            return "Weekly session quota reached."
        if monthly_limit and enrollment.session_progress.filter(updated_at__gte=now - timedelta(days=30)).count() >= monthly_limit:
            return "Monthly session quota reached."
    previous = CourseSession.objects.filter(course=session.course, order__lt=session.order).order_by("-order").first()
    if previous and hasattr(previous, "quiz") and previous.quiz.is_active:
        if not QuizAttempt.objects.filter(quiz=previous.quiz, user=user, passed=True).exists():
            return "Pass the previous session quiz first."
    return ""


class CourseListCreateView(generics.ListCreateAPIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]
    filterset_fields = ["status", "instructor"]
    search_fields = ["title", "description", "instructor__username"]
    ordering_fields = ["created_at", "updated_at", "title"]

    def get_permissions(self):
        permissions = [IsAuthenticated()]
        if self.request.method == "POST":
            permissions.append(CanTeachAcademy())
        return permissions

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CourseWriteSerializer
        return CourseListSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Course.objects.none()
        market = self.request.query_params.get("market")
        if market is not None and market not in User.MarketType.values:
            raise serializers.ValidationError({"market": "Choose internal, forex or crypto."})
        queryset = visible_courses(self.request.user)
        return queryset.filter(market=market) if market else queryset

    def perform_create(self, serializer):
        serializer.save(instructor=self.request.user)


class CourseManagementListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, CanTeachAcademy]
    serializer_class = CourseListSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status"]
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "updated_at", "title"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Course.objects.none()
        return manageable_courses(self.request.user)


class CourseDetailView(generics.RetrieveUpdateDestroyAPIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    lookup_field = "slug"

    def get_permissions(self):
        permissions = [IsAuthenticated()]
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            permissions.append(CanTeachAcademy())
        return permissions

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return CourseWriteSerializer
        return CourseListSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Course.objects.none()
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            return manageable_courses(self.request.user)

        visible = visible_courses(self.request.user)
        if can_edit_academy(self.request.user):
            return (visible | manageable_courses(self.request.user)).distinct()
        return visible

    def get_object(self):
        if self.request.method == "GET" and market_access_v2_enabled():
            candidate = get_object_or_404(Course, slug=self.kwargs["slug"])
            assert_course_market_access(self.request.user, candidate)
        return super().get_object()


class CourseSessionListCreateView(generics.ListCreateAPIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = CourseSessionSerializer

    def get_permissions(self):
        permissions = [IsAuthenticated()]
        if self.request.method == "POST":
            permissions.append(CanTeachAcademy())
        return permissions

    def get_course(self):
        if hasattr(self, "_course"):
            return self._course
        if self.request.method == "POST":
            queryset = manageable_courses(self.request.user)
        else:
            queryset = visible_courses(self.request.user)
            if can_edit_academy(self.request.user):
                queryset = (queryset | manageable_courses(self.request.user)).distinct()
        if self.request.method != "POST" and market_access_v2_enabled():
            candidate = get_object_or_404(Course, slug=self.kwargs["slug"])
            assert_course_market_access(self.request.user, candidate)
        self._course = get_object_or_404(
            queryset,
            slug=self.kwargs["slug"],
        )
        return self._course

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CourseSession.objects.none()
        queryset = CourseSession.objects.filter(course=self.get_course())
        if (
            self.request.method == "GET"
            and not (can_edit_academy(self.request.user) and manageable_courses(self.request.user).filter(
                pk=self.get_course().pk
            ).exists())
        ):
            queryset = queryset.filter(is_published=True)
        return queryset

    def perform_create(self, serializer):
        serializer.save(course=self.get_course())


class CourseSessionDetailView(
    generics.RetrieveUpdateDestroyAPIView
):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = CourseSessionSerializer

    def get_permissions(self):
        permissions = [IsAuthenticated()]
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            permissions.append(CanTeachAcademy())
        return permissions

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CourseSession.objects.none()
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            courses = manageable_courses(self.request.user)
            return CourseSession.objects.filter(
                course__in=courses
            ).select_related("course")
        public = CourseSession.objects.filter(
            course__in=visible_courses(self.request.user), is_published=True
        )
        managed = CourseSession.objects.filter(
            course__in=manageable_courses(self.request.user)
        ) if can_edit_academy(self.request.user) else CourseSession.objects.none()
        return (public | managed).distinct().select_related("course")

    def get_object(self):
        if self.request.method == "GET" and market_access_v2_enabled():
            candidate = get_object_or_404(CourseSession.objects.select_related("course"), pk=self.kwargs["pk"])
            assert_course_market_access(self.request.user, candidate.course)
        obj = super().get_object()
        if self.request.method == "GET":
            reason = session_lock_reason(obj, self.request.user)
            if reason:
                raise PermissionDenied(detail={"code": "SESSION_LOCKED", "lock_reason": reason})
        return obj


class EnrollCourseView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=CourseEnrollmentSerializer)
    def post(self, request, slug):
        if market_access_v2_enabled():
            assert_course_market_access(request.user, get_object_or_404(Course, slug=slug))
        course = get_object_or_404(visible_courses(request.user), slug=slug, enrollment_open=True)
        if not course.is_free or course.purchase_required:
            raise PermissionDenied("Purchase this course before enrollment.")
        enrollment, created = CourseEnrollment.objects.get_or_create(
            user=request.user, course=course
        )
        if created:
            ActivityService.record(request.user, UserActivity.Type.COURSE_ENROLL, "Course enrollment")
        return Response(CourseEnrollmentSerializer(enrollment, context={"request": request}).data)


class CoursePurchaseView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CoursePurchaseSerializer

    @transaction.atomic
    def post(self, request, slug):
        course = get_object_or_404(
            Course.objects.select_for_update().filter(status=Course.Status.PUBLISHED),
            slug=slug, enrollment_open=True,
        )
        assert_course_market_access(request.user, course)
        serializer = CoursePurchaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if CoursePurchase.objects.filter(user=request.user, course=course).exists():
            raise serializers.ValidationError({"course": "This course was already purchased."})
        if course.is_free:
            enrollment, _ = CourseEnrollment.objects.get_or_create(user=request.user, course=course)
            return Response({"status": "ENROLLED", "enrollment_id": enrollment.pk})
        method = serializer.validated_data["payment_method"]
        if method == "WALLET":
            wallet = WalletService.get_wallet(request.user)
            if WalletService.balance_irt(wallet) < course.price:
                raise serializers.ValidationError({"wallet": "Insufficient wallet balance."})
            ledger = WalletService.post(wallet, course.price, "COURSE_PURCHASE", credit_wallet=False, counterparty="COURSE_REVENUE", metadata={"course": course.slug})
            purchase = CoursePurchase.objects.create(user=request.user, course=course, amount_irt=course.price, payment_method=method, ledger_transaction=ledger)
            enrollment = CourseEnrollment.objects.create(user=request.user, course=course)
            return Response({"status": "PURCHASED", "purchase_id": purchase.pk, "enrollment_id": enrollment.pk})
        provider = get_object_or_404(PaymentProvider, code=serializer.validated_data.get("provider"), is_active=True)
        key = serializer.validated_data.get("idempotency_key")
        if not key:
            raise serializers.ValidationError({"idempotency_key": "Required for gateway payments."})
        payment, created = Payment.objects.get_or_create(
            user=request.user, idempotency_key=key,
            defaults={"provider": provider, "amount_irt": course.price, "purpose": Payment.Purpose.COURSE_PURCHASE, "metadata": {"course_slug": course.slug}},
        )
        if created:
            callback = f"{settings.PAYMENT_CALLBACK_BASE_URL.rstrip('/')}/api/billing/payments/verify/"
            try:
                authority, payment_url = ADAPTERS[provider.code].create(payment, callback)
            except PaymentProviderError as exc:
                raise serializers.ValidationError({"provider": str(exc)})
            payment.authority, payment.status = authority, Payment.Status.PENDING
            payment.metadata = {**payment.metadata, "payment_url": payment_url}
            payment.save(update_fields=["authority", "status", "metadata", "updated_at"])
        return Response({"status": payment.status, "payment_id": payment.pk, "payment_url": payment.metadata.get("payment_url")})


class CoursePurchaseStatusView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CoursePurchaseSerializer

    def get(self, request, slug):
        course = get_object_or_404(Course, slug=slug)
        assert_course_market_access(request.user, course)
        purchase = CoursePurchase.objects.filter(user=request.user, course=course).select_related("payment").first()
        enrollment = CourseEnrollment.objects.filter(user=request.user, course=course).first()
        return Response({
            "purchased": bool(purchase), "enrolled": bool(enrollment),
            "payment_status": purchase.payment.status if purchase and purchase.payment_id else None,
        })


class MyEnrollmentListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CourseEnrollmentSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CourseEnrollment.objects.none()
        queryset = CourseEnrollment.objects.filter(user=self.request.user)
        if market_access_v2_enabled():
            queryset = queryset.filter(course__market__in=resolve_market_access(self.request.user).effective_markets)
        return queryset.select_related("course", "course__instructor")


class SessionProgressView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SessionProgressSerializer

    def get_object(self):
        session = get_object_or_404(CourseSession, pk=self.kwargs["pk"])
        assert_course_market_access(self.request.user, session.course)
        enrollment = get_object_or_404(
            CourseEnrollment, user=self.request.user, course=session.course
        )
        progress, _ = SessionProgress.objects.get_or_create(
            enrollment=enrollment, session=session
        )
        return progress

    def perform_update(self, serializer):
        completed_at = timezone.now() if serializer.validated_data.get("progress_percent") == 100 else None
        progress = serializer.save(completed_at=completed_at)
        ActivityService.record(
            self.request.user,
            UserActivity.Type.COURSE_SESSION_VIEW,
            "Course session progress updated",
            target_type="course_session",
            target_id=progress.session_id,
            metadata={"progress_percent": progress.progress_percent},
        )


class SessionQuizView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = QuizPublicSerializer

    def get_object(self):
        if market_access_v2_enabled():
            candidate = get_object_or_404(CourseSession.objects.select_related("course"), pk=self.kwargs["pk"])
            assert_course_market_access(self.request.user, candidate.course)
        session = get_object_or_404(CourseSession, pk=self.kwargs["pk"], course__in=visible_courses(self.request.user))
        reason = session_lock_reason(session, self.request.user)
        if reason:
            raise PermissionDenied(detail={"code": "SESSION_LOCKED", "lock_reason": reason})
        return get_object_or_404(Quiz.objects.prefetch_related("questions__options"), session=session, is_active=True)


class QuizAttemptCreateView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = QuizAttemptSerializer

    @transaction.atomic
    def post(self, request, pk):
        quiz = get_object_or_404(Quiz.objects.select_related("session__course").prefetch_related("questions__options"), pk=pk, is_active=True)
        assert_course_market_access(request.user, quiz.session.course)
        if not CourseEnrollment.objects.filter(user=request.user, course=quiz.session.course).exists():
            raise PermissionDenied("Enroll in the course first.")
        previous = QuizAttempt.objects.select_for_update().filter(quiz=quiz, user=request.user).first()
        if previous and previous.passed:
            return Response(QuizAttemptSerializer(previous).data)
        if previous and previous.next_attempt_at and previous.next_attempt_at > timezone.now():
            raise Throttled(wait=(previous.next_attempt_at - timezone.now()).total_seconds())
        attempt_number = QuizAttempt.objects.filter(quiz=quiz, user=request.user).count() + 1
        if attempt_number > quiz.max_attempts:
            raise PermissionDenied("Maximum quiz attempts reached.")
        answers = request.data.get("answers")
        if not isinstance(answers, dict):
            raise serializers.ValidationError({"answers": "Use an object mapping question IDs to option IDs."})
        questions = list(quiz.questions.all())
        correct = 0
        for question in questions:
            selected = str(answers.get(str(question.pk), answers.get(question.pk, "")))
            if question.options.filter(pk=selected, is_correct=True).exists():
                correct += 1
        score = round((correct / len(questions)) * 100, 2) if questions else 0
        passed = score >= quiz.required_score
        next_attempt_at = None if passed else timezone.now() + timedelta(minutes=quiz.retry_delay_minutes)
        attempt = QuizAttempt.objects.create(
            quiz=quiz, user=request.user, answers=answers, score=score, passed=passed,
            attempt_number=attempt_number, next_attempt_at=next_attempt_at,
        )
        return Response(QuizAttemptSerializer(attempt).data, status=201)


class MyQuizAttemptListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = QuizAttemptSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return QuizAttempt.objects.none()
        queryset = QuizAttempt.objects.filter(quiz_id=self.kwargs["pk"], user=self.request.user)
        if market_access_v2_enabled():
            queryset = queryset.filter(quiz__session__course__market__in=resolve_market_access(self.request.user).effective_markets)
        return queryset.select_related("quiz")


class QuizManagementCreateView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated, CanTeachAcademy]
    serializer_class = QuizWriteSerializer

    def perform_create(self, serializer):
        session = serializer.validated_data["session"]
        if not manageable_courses(self.request.user).filter(pk=session.course_id).exists():
            raise PermissionDenied()
        serializer.save()


class QuizManagementView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, CanTeachAcademy]
    serializer_class = QuizWriteSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Quiz.objects.none()
        return Quiz.objects.filter(session__course__in=manageable_courses(self.request.user)).prefetch_related("questions__options")


class SessionMediaTicketView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    def post(self, request, pk):
        if market_access_v2_enabled():
            candidate = get_object_or_404(CourseSession.objects.select_related("course"), pk=pk)
            assert_course_market_access(request.user, candidate.course)
        session = get_object_or_404(CourseSession, pk=pk, course__in=visible_courses(request.user))
        reason = session_lock_reason(session, request.user)
        if reason:
            raise PermissionDenied(detail={"code": "SESSION_LOCKED", "lock_reason": reason})
        media = request.data.get("media", session.media_type)
        if media not in ("video", "audio"):
            raise serializers.ValidationError({"media": "Only video or audio can be streamed."})
        ticket = signing.dumps({"user_id": request.user.pk, "session_id": session.pk, "media": media}, salt="academy-media", compress=True)
        return Response({"url": f"/api/academy/sessions/{session.pk}/media/?ticket={ticket}", "expires_in": settings.CHANNEL_TICKET_TTL_SECONDS})


class SessionMediaStreamView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = EmptySerializer

    def get(self, request, pk):
        try:
            payload = signing.loads(request.query_params.get("ticket", ""), salt="academy-media", max_age=settings.CHANNEL_TICKET_TTL_SECONDS)
        except signing.BadSignature as exc:
            raise PermissionDenied("Invalid or expired media ticket.") from exc
        if payload.get("session_id") != pk:
            raise PermissionDenied("Ticket does not match this session.")
        session = get_object_or_404(CourseSession, pk=pk)
        user = get_object_or_404(User, pk=payload.get("user_id"), is_active=True)
        assert_course_market_access(user, session.course)
        reason = session_lock_reason(session, user)
        if reason:
            raise PermissionDenied(detail={"code": "SESSION_LOCKED", "lock_reason": reason})
        media_field = session.video_file if payload.get("media") == "video" else session.audio_file
        if not media_field:
            from rest_framework.exceptions import NotFound
            raise NotFound("Media file is unavailable.")
        path = media_field.path
        size = os.path.getsize(path)
        start, end = 0, size - 1
        range_header = request.headers.get("Range", "")
        status_code = 200
        if range_header.startswith("bytes="):
            value = range_header.removeprefix("bytes=").split(",", 1)[0]
            first, _, last = value.partition("-")
            start = int(first or 0)
            end = min(int(last) if last else size - 1, size - 1)
            if start > end or start >= size:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"range": "Invalid byte range."})
            status_code = 206
        length = end - start + 1

        def chunks():
            with open(path, "rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining:
                    block = handle.read(min(64 * 1024, remaining))
                    if not block:
                        break
                    remaining -= len(block)
                    yield block

        response = StreamingHttpResponse(chunks(), status=status_code, content_type="application/octet-stream")
        response["Accept-Ranges"] = "bytes"
        response["Content-Length"] = str(length)
        if status_code == 206:
            response["Content-Range"] = f"bytes {start}-{end}/{size}"
        response["Cache-Control"] = "private, no-store"
        return response
