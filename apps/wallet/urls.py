from django.urls import path

from .views import (
    WalletDetailView,
    TransactionListView,
    BankCardDeleteView,
    BankCardListCreateView,
    PaymentCreateView,
    WithdrawalListCreateView,
)


urlpatterns = [
    path(
        "",
        WalletDetailView.as_view(),
        name="wallet-detail",
    ),

    path(
        "transactions/",
        TransactionListView.as_view(),
        name="transaction-list",
    ),
    path("bank-cards/", BankCardListCreateView.as_view(), name="bank-card-list"),
    path("bank-cards/<int:pk>/", BankCardDeleteView.as_view(), name="bank-card-delete"),
    path("deposits/", PaymentCreateView.as_view(), name="wallet-deposit"),
    path("withdrawals/", WithdrawalListCreateView.as_view(), name="withdrawal-list"),
]
