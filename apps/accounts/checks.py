from django.conf import settings
from django.core.checks import Error, register


@register()
def payamito_configuration_check(app_configs, **kwargs):
    if not settings.PAYAMITO_ENABLED:
        return []
    missing = [
        name for name in (
            "PAYAMITO_USERNAME", "PAYAMITO_API_KEY", "PAYAMITO_FROM_NUMBER",
            "PAYAMITO_OTP_MESSAGE_TEMPLATE", "PAYAMITO_NOTIFICATION_MESSAGE_TEMPLATE",
        )
        if not getattr(settings, name, "")
    ]
    if not missing:
        return []
    return [Error(
        "Payamito SMS is enabled but required settings are missing.",
        hint="Set: " + ", ".join(missing),
        id="accounts.E001",
    )]
