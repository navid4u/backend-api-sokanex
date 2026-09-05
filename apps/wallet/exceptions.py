from rest_framework.exceptions import APIException


class PremiumPurchaseError(APIException):
    status_code = 400
    default_detail = "خرید اشتراک ویژه انجام نشد."
    machine_code = "PREMIUM_PURCHASE_FAILED"

    def __init__(self, detail=None, code=None, status_code=None, **extra):
        if status_code is not None:
            self.status_code = status_code
        self.machine_code = code or self.machine_code
        self.extra_payload = extra
        super().__init__(detail or self.default_detail)
