from rest_framework import serializers

from .models import Wallet, Transaction


class WalletSerializer(serializers.ModelSerializer):

    class Meta:
        model = Wallet

        fields = (
            "id",
            "balance",
            "currency",
            "updated_at",
        )

        read_only_fields = fields


class TransactionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Transaction

        fields = (
            "id",
            "reference",
            "transaction_type",
            "status",
            "amount",
            "balance_after",
            "description",
            "created_at",
        )

        read_only_fields = fields