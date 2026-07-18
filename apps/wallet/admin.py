from django.contrib import admin

from .models import Wallet, Transaction


class TransactionInline(admin.TabularInline):

    model = Transaction
    extra = 0
    can_delete = False

    fields = (
        "reference",
        "transaction_type",
        "status",
        "amount",
        "balance_after",
        "created_at",
    )

    readonly_fields = fields


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "balance",
        "currency",
        "updated_at",
    )

    search_fields = (
        "user__username",
        "user__email",
    )

    readonly_fields = (
        "balance",
        "created_at",
        "updated_at",
    )

    inlines = [
        TransactionInline,
    ]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):

    list_display = (
        "reference",
        "wallet",
        "transaction_type",
        "status",
        "amount",
        "created_at",
    )

    list_filter = (
        "transaction_type",
        "status",
    )

    search_fields = (
        "reference",
        "wallet__user__username",
    )

    readonly_fields = (
        "wallet",
        "reference",
        "transaction_type",
        "status",
        "amount",
        "balance_after",
        "description",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False