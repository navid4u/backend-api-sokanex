from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User

from .models import FieldDefinition, Platform, PlatformChangeAudit
from .serializers import FieldDefinitionSerializer, PlatformReadSerializer, PlatformWriteSerializer


class CanManagePlatforms(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.has_platform_permission(
            User.Permission.CONTENT_MANAGE,
        ))


class PlatformPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _platform_queryset(request, *, manage=False):
    query = Platform.objects.filter(deleted_at__isnull=True)
    if not manage:
        query = query.filter(is_active=True)
    params = request.query_params
    kind = params.get("platform_type")
    if kind is not None:
        if kind not in Platform.Type.values:
            raise serializers.ValidationError({"platform_type": "Choose BROKER or EXCHANGE."})
        query = query.filter(platform_type=kind)
    search = params.get("search", "").strip()
    if search:
        query = query.filter(Q(name__icontains=search) | Q(subtitle__icontains=search) | Q(description__icontains=search))
    if "is_popular" in params:
        value = params["is_popular"].lower()
        if value not in ("true", "false"):
            raise serializers.ValidationError({"is_popular": "Use true or false."})
        query = query.filter(is_popular=value == "true")
    if manage and "is_active" in params:
        value = params["is_active"].lower()
        if value not in ("true", "false"):
            raise serializers.ValidationError({"is_active": "Use true or false."})
        query = query.filter(is_active=value == "true")
    ordering = params.get("ordering", "sort_order,-rating")
    allowed = {
        "sort_order,-rating": ("sort_order", F("rating").desc(nulls_last=True), "id"),
        "-rating,sort_order": (F("rating").desc(nulls_last=True), "sort_order", "id"),
        "name": ("name", "id"),
    }
    if ordering not in allowed:
        raise serializers.ValidationError({"ordering": "Unknown ordering."})
    return query.order_by(*allowed[ordering])


def _field_rows(request, *, manage=False):
    kind = request.query_params.get("platform_type")
    if kind not in Platform.Type.values:
        raise serializers.ValidationError({"platform_type": "Choose BROKER or EXCHANGE."})
    rows = FieldDefinition.objects.filter(platform_type=kind)
    if not manage:
        rows = rows.filter(is_active=True)
    search = request.query_params.get("search", "").strip()
    if search and manage:
        rows = rows.filter(Q(key__icontains=search) | Q(label__icontains=search))
    return rows.order_by("sort_order", "id")


def _audit(request, action, *, platform=None, field=None, changed_fields=()):
    PlatformChangeAudit.objects.create(actor=request.user, action=action, platform=platform,
                                       field_definition=field, changed_fields=list(changed_fields),
                                       object_type="PLATFORM" if platform else "FIELD",
                                       object_id=platform.pk if platform else field.pk)


class PlatformPublicListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PlatformReadSerializer
    pagination_class = PlatformPagination

    def get_queryset(self):
        return _platform_queryset(self.request)


class PlatformPublicDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PlatformReadSerializer

    def get_queryset(self):
        return Platform.objects.filter(is_active=True, deleted_at__isnull=True)


class PlatformCompareView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        raw = request.query_params.get("ids", "")
        values = raw.split(",")
        if len(values) not in (2, 3) or any(
            not value.isascii() or not value.isdecimal() or len(value) > 19
            for value in values
        ):
            raise serializers.ValidationError({"ids": "Provide two or three numeric IDs."})
        ids = [int(value) for value in values]
        if any(value > 9223372036854775807 for value in ids):
            raise serializers.ValidationError({"ids": "ID is out of range."})
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError({"ids": "IDs must be unique."})
        rows = {item.pk: item for item in Platform.objects.filter(
            pk__in=ids, is_active=True, deleted_at__isnull=True,
        )}
        if len(rows) != len(ids):
            from rest_framework.exceptions import NotFound
            raise NotFound("One or more platforms are unavailable.")
        platforms = [rows[pk] for pk in ids]
        kind = platforms[0].platform_type
        if any(item.platform_type != kind for item in platforms):
            raise serializers.ValidationError({"ids": "Platforms must have the same type."})
        fields = FieldDefinition.objects.filter(platform_type=kind, is_active=True).order_by("sort_order", "id")
        return Response({
            "platform_type": kind,
            "fields": FieldDefinitionSerializer(fields, many=True).data,
            "platforms": PlatformReadSerializer(platforms, many=True, context={"request": request}).data,
        })


class PlatformFieldListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = list(_field_rows(request))
        return Response({"count": len(rows), "results": FieldDefinitionSerializer(rows, many=True).data})


class PlatformManageListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, CanManagePlatforms]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    pagination_class = PlatformPagination

    def get_queryset(self):
        return _platform_queryset(self.request, manage=True)

    def get_serializer_class(self):
        return PlatformWriteSerializer if self.request.method == "POST" else PlatformReadSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "manage": True}

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = PlatformWriteSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        platform = serializer.save()
        _audit(request, "CREATE", platform=platform, changed_fields=serializer._changed_fields)
        return Response(PlatformReadSerializer(platform, context=self.get_serializer_context()).data,
                        status=status.HTTP_201_CREATED)


class PlatformManageDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, CanManagePlatforms]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return Platform.objects.filter(deleted_at__isnull=True)

    def get_serializer_class(self):
        return PlatformWriteSerializer if self.request.method in ("PATCH", "PUT") else PlatformReadSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "manage": True}

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        platform = self.get_object()
        serializer = PlatformWriteSerializer(platform, data=request.data, partial=True,
                                             context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        platform = serializer.save()
        if serializer._changed_fields:
            _audit(request, "UPDATE", platform=platform, changed_fields=serializer._changed_fields)
        return Response(PlatformReadSerializer(platform, context=self.get_serializer_context()).data)

    def update(self, request, *args, **kwargs):
        raise serializers.ValidationError({"method": "Use PATCH for partial changes."})

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        platform = self.get_object()
        platform.is_active = False
        platform.deleted_at = timezone.now()
        platform.save(update_fields=("is_active", "deleted_at", "updated_at"))
        _audit(request, "DELETE", platform=platform, changed_fields=("is_active", "deleted_at"))
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlatformManageFieldsView(APIView):
    permission_classes = [IsAuthenticated, CanManagePlatforms]

    def get(self, request):
        rows = list(_field_rows(request, manage=True))
        return Response({"count": len(rows), "results": FieldDefinitionSerializer(rows, many=True).data})

    def post(self, request):
        serializer = FieldDefinitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                field = serializer.save()
                _audit(request, "FIELD_CREATE", field=field, changed_fields=serializer.validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError({"key": "This key already exists for this platform type."}) from exc
        return Response(FieldDefinitionSerializer(field).data, status=status.HTTP_201_CREATED)


class PlatformManageFieldDetailView(APIView):
    permission_classes = [IsAuthenticated, CanManagePlatforms]

    @transaction.atomic
    def patch(self, request, pk):
        field = get_object_or_404(FieldDefinition, pk=pk)
        serializer = FieldDefinitionSerializer(field, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changed = [key for key, value in serializer.validated_data.items() if getattr(field, key) != value]
        if changed:
            serializer.save()
            _audit(request, "FIELD_UPDATE", field=field, changed_fields=changed)
        return Response(FieldDefinitionSerializer(field).data)

    @transaction.atomic
    def delete(self, request, pk):
        field = get_object_or_404(FieldDefinition, pk=pk)
        if any((details or {}).get(field.key) for details in Platform.objects.filter(
            platform_type=field.platform_type,
        ).values_list("details", flat=True).iterator()):
            return Response({"key": ["This field contains platform data; deactivate it instead."]},
                            status=status.HTTP_409_CONFLICT)
        _audit(request, "FIELD_DELETE", field=field, changed_fields=("id",))
        field.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
