from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import UserActivity
from .serializers import UserActivitySerializer


class RecentActivityListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserActivitySerializer
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return UserActivity.objects.none()
        return UserActivity.objects.filter(user=self.request.user)[:25]

