from django_filters.rest_framework import (
    DjangoFilterBackend,
)
from drf_spectacular.utils import extend_schema
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.filters import (
    OrderingFilter,
    SearchFilter,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import TransactionFilter
from .models import BankCard, Payment, PaymentAuditLog, PaymentProvider, Transaction, UpgradePlan, Withdrawal
from .serializers import (
    TransactionSerializer,
    WalletSerializer,
    BankCardSerializer, PaymentCreateSerializer, PaymentProviderSerializer,
    PaymentVerifySerializer, UpgradePlanSerializer, WithdrawalSerializer,
)
from .services import WalletService
from .providers import ADAPTERS, PaymentProviderError
from common.permissions import CanManagePlatform


class WalletDetailView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=WalletSerializer)
    def get(self, request):
        wallet = WalletService.get_wallet(
            request.user
        )

        serializer = WalletSerializer(wallet)

        return Response(serializer.data)


class TransactionListView(
    generics.ListAPIView
):

    permission_classes = [IsAuthenticated]

    serializer_class = TransactionSerializer

    filterset_class = TransactionFilter

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    search_fields = [
        "reference",
        "description",
    ]

    ordering_fields = [
        "created_at",
        "updated_at",
        "amount",
        "balance_after",
        "status",
        "transaction_type",
    ]

    ordering = [
        "-created_at",
    ]

    def get_queryset(self):
        if getattr(
            self,
            "swagger_fake_view",
            False,
        ):
            return Transaction.objects.none()

        return WalletService.list_transactions(
            self.request.user
        )


class BankCardListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BankCardSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return BankCard.objects.none()
        return BankCard.objects.filter(user=self.request.user).order_by("-created_at")


class BankCardDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BankCardSerializer

    def get_queryset(self):
        return BankCard.objects.filter(user=self.request.user)


class WithdrawalListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WithdrawalSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Withdrawal.objects.none()
        return Withdrawal.objects.filter(user=self.request.user).order_by("-created_at")

    @transaction.atomic
    def perform_create(self, serializer):
        from apps.platform_settings.models import PlatformSettings
        card = serializer.validated_data["bank_card"]
        amount = serializer.validated_data["amount_irt"]
        financial = PlatformSettings.load()
        if amount < financial.minimum_withdrawal_irt or amount > financial.maximum_withdrawal_irt:
            raise serializers.ValidationError({"amount_irt": "Amount is outside the configured withdrawal limits."})
        if card.user_id != self.request.user.id or not card.is_verified:
            raise serializers.ValidationError({"bank_card": "A verified card or IBAN owned by you is required."})
        wallet = WalletService.get_wallet(self.request.user)
        if WalletService.balance_irt(wallet) < amount:
            raise serializers.ValidationError({"amount_irt": "Insufficient wallet balance."})
        ledger = WalletService.post(wallet, amount, "WITHDRAWAL_HOLD", credit_wallet=False, counterparty="WITHDRAWAL_HOLD")
        serializer.save(user=self.request.user, ledger_transaction=ledger)


class PaymentProviderListView(generics.ListAPIView):
    permission_classes = [CanManagePlatform]
    serializer_class = PaymentProviderSerializer
    queryset = PaymentProvider.objects.order_by("sort_order", "id")
    pagination_class = None


class PaymentProviderUpdateView(generics.UpdateAPIView):
    permission_classes = [CanManagePlatform]
    serializer_class = PaymentProviderSerializer
    queryset = PaymentProvider.objects.all()


class UpgradePlanListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UpgradePlanSerializer
    queryset = UpgradePlan.objects.filter(active=True).order_by("sort_order", "level")
    pagination_class = None


class PaymentCreateView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentCreateSerializer

    def post(self, request):
        payload = request.data.copy()
        if request.resolver_match and request.resolver_match.url_name == "wallet-deposit":
            payload["purpose"] = Payment.Purpose.WALLET_DEPOSIT
        serializer = PaymentCreateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["purpose"] == Payment.Purpose.COURSE_PURCHASE:
            from apps.academy.models import Course
            course = Course.objects.filter(slug=data.get("metadata", {}).get("course_slug"), status=Course.Status.PUBLISHED).first()
            if not course or course.is_free or course.price != data["amount_irt"]:
                raise serializers.ValidationError({"metadata": "Course and server-side price do not match."})
        elif data["purpose"] == Payment.Purpose.LEVEL_UPGRADE:
            plan = UpgradePlan.objects.filter(level=data.get("metadata", {}).get("level"), active=True).first()
            if not plan or plan.level <= request.user.access_level or plan.price_irt != data["amount_irt"]:
                raise serializers.ValidationError({"metadata": "Upgrade plan and server-side price do not match."})
        if data["purpose"] == Payment.Purpose.WALLET_DEPOSIT:
            from apps.platform_settings.models import PlatformSettings
            if data["amount_irt"] < PlatformSettings.load().minimum_deposit_irt:
                raise serializers.ValidationError({"amount_irt": "Amount is below the configured minimum deposit."})
        payment, created = Payment.objects.get_or_create(
            user=request.user, idempotency_key=data["idempotency_key"],
            defaults={"provider": data["provider"], "amount_irt": data["amount_irt"], "purpose": data["purpose"], "metadata": data.get("metadata", {})},
        )
        if not created:
            if payment.amount_irt != data["amount_irt"] or payment.purpose != data["purpose"]:
                raise serializers.ValidationError({"idempotency_key": "This key was used for different payment data."})
            return Response({"id": payment.id, "status": payment.status, "payment_url": payment.metadata.get("payment_url")})
        PaymentAuditLog.objects.create(payment=payment, event="CREATED")
        callback = f"{settings.PAYMENT_CALLBACK_BASE_URL.rstrip('/')}/api/billing/payments/verify/"
        try:
            authority, payment_url = ADAPTERS[payment.provider.code].create(payment, callback)
        except PaymentProviderError as exc:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            PaymentAuditLog.objects.create(payment=payment, event="REQUEST_FAILED", detail={"error": str(exc)[:300]})
            raise serializers.ValidationError({"provider": str(exc)})
        payment.authority, payment.status = authority, Payment.Status.PENDING
        payment.metadata = {**payment.metadata, "payment_url": payment_url}
        payment.save(update_fields=["authority", "status", "metadata", "updated_at"])
        PaymentAuditLog.objects.create(payment=payment, event="REDIRECT_CREATED")
        return Response({"id": payment.id, "status": payment.status, "payment_url": payment_url}, status=status.HTTP_201_CREATED)


class PaymentVerifyView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentVerifySerializer

    @transaction.atomic
    def post(self, request):
        serializer = PaymentVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payment = Payment.objects.select_for_update().get(pk=data["payment_id"], user=request.user)
        if payment.status == Payment.Status.VERIFIED:
            PaymentAuditLog.objects.create(payment=payment, event="VERIFY_REPLAY")
            return Response({"id": payment.id, "status": payment.status, "reference": payment.provider_reference})
        if data.get("status", "").upper() in ("NOK", "FAILED", "CANCELLED"):
            payment.status = Payment.Status.CANCELLED
            payment.save(update_fields=["status", "updated_at"])
            return Response({"id": payment.id, "status": payment.status})
        if data["authority"] != payment.authority:
            raise serializers.ValidationError({"authority": "Authority does not match this payment."})
        try:
            reference = ADAPTERS[payment.provider.code].verify(payment, payment.authority)
        except PaymentProviderError as exc:
            raise serializers.ValidationError({"payment": str(exc)})
        if payment.purpose == Payment.Purpose.WALLET_DEPOSIT:
            payment.ledger_transaction = WalletService.post(WalletService.get_wallet(request.user), payment.amount_irt, "WALLET_DEPOSIT", metadata={"payment_id": str(payment.id)})
        elif payment.purpose == Payment.Purpose.COURSE_PURCHASE:
            from apps.academy.models import Course, CourseEnrollment, CoursePurchase
            course = Course.objects.select_for_update().get(slug=payment.metadata["course_slug"])
            purchase, _ = CoursePurchase.objects.get_or_create(
                user=request.user, course=course,
                defaults={"amount_irt": payment.amount_irt, "payment_method": CoursePurchase.Method.GATEWAY, "payment": payment},
            )
            CourseEnrollment.objects.get_or_create(user=request.user, course=course)
        elif payment.purpose == Payment.Purpose.LEVEL_UPGRADE:
            from apps.accounts.models import UpgradeRequest
            plan = UpgradePlan.objects.select_for_update().get(level=payment.metadata["level"], active=True)
            UpgradeRequest.objects.get_or_create(
                user=request.user, status=UpgradeRequest.Status.PENDING,
                defaults={
                    "request_type": UpgradeRequest.Type.UPGRADE,
                    "requested_level": plan.level, "plan": plan,
                    "price_snapshot_irt": plan.price_irt,
                },
            )
        payment.status, payment.provider_reference, payment.verified_at = Payment.Status.VERIFIED, reference, timezone.now()
        payment.save(update_fields=["ledger_transaction", "status", "provider_reference", "verified_at", "updated_at"])
        PaymentAuditLog.objects.create(payment=payment, event="VERIFIED", detail={"reference": reference})
        return Response({"id": payment.id, "status": payment.status, "reference": reference})
