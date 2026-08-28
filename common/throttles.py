from rest_framework.throttling import (
    SimpleRateThrottle,
)


class LoginRateThrottle(
    SimpleRateThrottle
):
    scope = "login"

    def get_cache_key(
        self,
        request,
        view,
    ):
        ip_address = self.get_ident(
            request
        )

        username = str(
            request.data.get(
                "username",
                "",
            )
        ).strip().lower()

        identity = (
            f"{ip_address}:{username}"
        )

        return self.cache_format % {
            "scope": self.scope,
            "ident": identity,
        }


class RegisterRateThrottle(
    SimpleRateThrottle
):
    scope = "register"

    def get_cache_key(
        self,
        request,
        view,
    ):
        ip_address = self.get_ident(
            request
        )

        return self.cache_format % {
            "scope": self.scope,
            "ident": ip_address,
        }


class SupportMessageRateThrottle(SimpleRateThrottle):
    scope = "support_message"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


class RegistrationOTPRequestThrottle(SimpleRateThrottle):
    scope = "registration_otp_request"

    def get_cache_key(self, request, view):
        ip_address = self.get_ident(request)
        phone = str(request.data.get("phone", "")).strip()
        return self.cache_format % {
            "scope": self.scope,
            "ident": f"{ip_address}:{phone}",
        }
