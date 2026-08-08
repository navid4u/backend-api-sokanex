from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from .models import UserDevice


class DeviceAwareTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        old_token = RefreshToken(attrs["refresh"])
        old_jti = str(old_token["jti"])
        device = UserDevice.objects.filter(refresh_jti=old_jti).first()
        if device and device.revoked_at is not None:
            raise AuthenticationFailed("This device session has been revoked.")

        data = super().validate(attrs)
        rotated_value = data.get("refresh")
        if device and rotated_value:
            rotated = RefreshToken(rotated_value)
            device.refresh_jti = str(rotated["jti"])
            device.revoked_at = None
            device.last_seen_at = timezone.now()
            device.save(update_fields=("refresh_jti", "revoked_at", "last_seen_at"))
        return data


class DeviceAwareTokenRefreshView(TokenRefreshView):
    serializer_class = DeviceAwareTokenRefreshSerializer
