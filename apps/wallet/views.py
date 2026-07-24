from django_filters.rest_framework import (
    DjangoFilterBackend,
)
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.filters import (
    OrderingFilter,
    SearchFilter,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import TransactionFilter
from .models import Transaction
from .serializers import (
    TransactionSerializer,
    WalletSerializer,
)
from .services import WalletService


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