from django import forms
from django.contrib import admin

from .crypto import encrypt_token
from .models import AISettings, AISettingsAuditLog, AIUsageLog


class AISettingsAdminForm(forms.ModelForm):
    new_api_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the current token.",
    )

    class Meta:
        model = AISettings
        exclude = ("api_token_encrypted",)


@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    form = AISettingsAdminForm
    list_display = ("provider", "model", "enabled", "updated_at")
    exclude = ("api_token_encrypted",)

    def save_model(self, request, obj, form, change):
        token = form.cleaned_data.get("new_api_token")
        if token:
            obj.api_token_encrypted = encrypt_token(token)
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        AISettingsAuditLog.objects.create(ai_settings=obj, actor=request.user, changed_fields=list(form.changed_data))

    def has_add_permission(self, request):
        return not AISettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AISettingsAuditLog)
class AISettingsAuditAdmin(admin.ModelAdmin):
    list_display = ("ai_settings", "actor", "created_at")
    readonly_fields = tuple(field.name for field in AISettingsAuditLog._meta.fields)

    def has_add_permission(self, request):
        return False


@admin.register(AIUsageLog)
class AIUsageAdmin(admin.ModelAdmin):
    list_display = ("user", "mode", "status", "input_tokens", "output_tokens", "latency_ms", "created_at")
    list_filter = ("mode", "status")
    readonly_fields = tuple(field.name for field in AIUsageLog._meta.fields)

    def has_add_permission(self, request):
        return False
