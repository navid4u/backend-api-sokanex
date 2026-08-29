from rest_framework.exceptions import APIException


class AssistantError(APIException):
    status_code = 503
    default_detail = "سرویس دستیار هوشمند موقتاً در دسترس نیست."
    machine_code = "ASSISTANT_UNAVAILABLE"

    def __init__(self, detail=None, code=None, status_code=None):
        if status_code:
            self.status_code = status_code
        self.machine_code = code or self.machine_code
        super().__init__(detail)
