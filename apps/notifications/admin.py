from django.contrib import admin

from .models import (
    Notification, NotificationRead, NotificationSMSDelivery,
    SMSAutomationRule, SMSAutomationDelivery, SMSBroadcast,
)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "notification_type",
        "priority",
        "recipient",
        "target_role",
        "is_active",
        "created_at",
    )
    list_filter = (
        "notification_type",
        "priority",
        "target_role",
        "is_active",
        "created_at",
    )
    search_fields = (
        "title",
        "message",
        "recipient__username",
        "recipient__email",
    )
    list_select_related = (
        "recipient",
        "created_by",
    )
    readonly_fields = (
        "created_by",
        "created_at",
        "updated_at",
    )
    ordering = (
        "-created_at",
    )
    date_hierarchy = "created_at"

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(NotificationRead)
class NotificationReadAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "notification",
        "user",
        "read_at",
    )
    list_filter = ("read_at",)
    search_fields = (
        "notification__title",
        "user__username",
        "user__email",
    )
    list_select_related = ("notification", "user")
    readonly_fields = ("notification", "user", "read_at")
    ordering = ("-read_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(NotificationSMSDelivery)
class NotificationSMSDeliveryAdmin(admin.ModelAdmin):
    list_display = ("id", "notification", "user", "phone", "status", "attempts", "sent_at")
    list_filter = ("status", "created_at", "sent_at")
    search_fields = ("notification__title", "user__username", "phone", "provider_message_id")
    readonly_fields = (
        "notification", "user", "phone", "status", "attempts", "provider_message_id",
        "provider_code", "error_message", "sent_at", "created_at", "updated_at",
    )
    list_select_related = ("notification", "user")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SMSAutomationRule)
class SMSAutomationRuleAdmin(admin.ModelAdmin):
    list_display = ("slot", "market", "enabled", "trial_day", "send_time_utc", "delay_minutes", "updated_at")
    list_filter = ("event", "market", "enabled")
    readonly_fields = ("slot", "event", "market", "enabled_at", "updated_by", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj and obj.event == SMSAutomationRule.Event.TRIAL:
            return (*fields, "delay_minutes")
        return (*fields, "trial_day", "send_time_utc")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser or request.user.role == "SUPER_ADMIN")

    def save_model(self, request, obj, form, change):
        from django.utils import timezone
        from .sms_automation import validate_template
        validate_template(obj.text)
        if obj.enabled and change:
            original = SMSAutomationRule.objects.get(pk=obj.pk)
            if not original.enabled:
                obj.enabled_at = timezone.now()
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SMSAutomationDelivery)
class SMSAutomationDeliveryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "event", "status", "scheduled_at", "sent_at")
    list_filter = ("status", "event")
    search_fields = ("user__username", "phone")
    readonly_fields = (
        "user", "rule", "broadcast", "event_key", "event", "phone", "text", "status",
        "scheduled_at", "claimed_at", "sent_at", "provider_message_id", "failure_code",
        "attempts", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SMSBroadcast)
class SMSBroadcastAdmin(admin.ModelAdmin):
    list_display = ("id", "created_by", "market", "recipient_count", "created_at")
    readonly_fields = ("created_by", "membership_tiers", "market", "text", "recipient_count", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

