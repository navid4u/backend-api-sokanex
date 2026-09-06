from rest_framework.throttling import SimpleRateThrottle


class FrontendLogThrottle(SimpleRateThrottle):
    scope = "frontend_logs"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        identity = f"user:{user.pk}" if getattr(user, "is_authenticated", False) else f"ip:{self.get_ident(request)}"
        return self.cache_format % {"scope": self.scope, "ident": identity}
