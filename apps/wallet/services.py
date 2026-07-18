from .models import Wallet


class WalletService:

    @staticmethod
    def get_wallet(user):
        wallet, _ = Wallet.objects.get_or_create(
            user=user,
        )

        return wallet

    @staticmethod
    def list_transactions(user):
        wallet = WalletService.get_wallet(user)

        return wallet.transactions.all()