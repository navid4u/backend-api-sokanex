from django.contrib import admin

from .models import (
    BankCard,
    LedgerEntry,
    LedgerTransaction,
    Payment,
    PaymentAuditLog,
    PaymentProvider,
    Transaction,
    UpgradePlan,
    Wallet,
    Withdrawal,
)


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


@admin.register(PaymentProvider)
class PaymentProviderAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "is_active", "sandbox", "sort_order", "updated_at")
    readonly_fields = ("code", "updated_at")


@admin.register(UpgradePlan)
class UpgradePlanAdmin(admin.ModelAdmin):
    list_display = ("level", "title", "price_irt", "active", "sort_order")
    list_editable = ("price_irt", "active", "sort_order")


@admin.register(BankCard)
class BankCardAdmin(admin.ModelAdmin):
    list_display = ("user", "card_last4", "iban", "is_verified", "created_at")
    list_filter = ("is_verified",)
    search_fields = ("user__username", "card_last4", "iban")
    readonly_fields = ("user", "card_last4", "card_hash", "iban", "created_at")


@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "amount_irt", "status", "bank_card", "created_at")
    list_filter = ("status",)
    search_fields = ("user__username", "bank_card__card_last4", "bank_card__iban")
    readonly_fields = ("user", "bank_card", "amount_irt", "status", "ledger_transaction", "created_at", "updated_at")
    actions = ("approve_selected", "reject_selected", "mark_selected_paid")

    @admin.action(description="Approve selected pending withdrawals")
    def approve_selected(self, request, queryset):
        from .services import WalletService
        updated = 0
        for withdrawal in queryset:
            try:
                WalletService.review_withdrawal(withdrawal, Withdrawal.Status.APPROVED)
                updated += 1
            except ValueError:
                continue
        self.message_user(request, f"{updated} withdrawal(s) approved.")

    @admin.action(description="Reject selected pending withdrawals and release funds")
    def reject_selected(self, request, queryset):
        from .services import WalletService
        updated = 0
        for withdrawal in queryset:
            try:
                WalletService.review_withdrawal(withdrawal, Withdrawal.Status.REJECTED)
                updated += 1
            except ValueError:
                continue
        self.message_user(request, f"{updated} withdrawal(s) rejected.")

    @admin.action(description="Mark selected approved withdrawals as paid")
    def mark_selected_paid(self, request, queryset):
        updated = queryset.filter(status=Withdrawal.Status.APPROVED).update(
            status=Withdrawal.Status.PAID
        )
        self.message_user(request, f"{updated} withdrawal(s) marked paid.")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "provider", "amount_irt", "purpose", "status", "created_at")
    list_filter = ("provider", "purpose", "status")
    search_fields = ("id", "user__username", "authority", "provider_reference")
    readonly_fields = [field.name for field in Payment._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for immutable_model in (LedgerTransaction, LedgerEntry, PaymentAuditLog):
    admin.site.register(
        immutable_model,
        type(
            f"{immutable_model.__name__}Admin",
            (admin.ModelAdmin,),
            {
                "readonly_fields": [field.name for field in immutable_model._meta.fields],
                "has_add_permission": lambda self, request: False,
                "has_delete_permission": lambda self, request, obj=None: False,
            },
        ),
    )
