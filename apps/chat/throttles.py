from rest_framework.throttling import SimpleRateThrottle


class SocialWriteThrottle(SimpleRateThrottle):
    scope = "social_write"
    rate = "30/minute"

    def get_rate(self):
        return self.rate

    def get_cache_key(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS") or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": str(request.user.pk)}


class SocialReportThrottle(SocialWriteThrottle):
    scope = "social_report"
    rate = "5/minute"


class RoomInviteThrottle(SocialWriteThrottle):
    scope = "room_invite"
    rate = "10/minute"
