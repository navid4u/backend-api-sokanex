from django.urls import path

from .views import (
    WalletDetailView,
    TransactionListView,
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
]