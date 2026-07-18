from .models import Broker


class BrokerService:

    @staticmethod
    def active_brokers():
        return Broker.objects.filter(
            is_active=True
        )

    @staticmethod
    def all_brokers():
        return Broker.objects.all()