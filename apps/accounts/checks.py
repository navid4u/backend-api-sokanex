from django.conf import settings
from django.core.checks import Error, register


@register()
def payamito_configuration_check(app_configs, **kwargs):
    if not settings.PAYAMITO_ENABLED:
        return []
    missing = [
        name for name in ("PAYAMITO_USERNAME", "PAYAMITO_API_KEY", "PAYAMITO_FROM_NUMBER")
        if not getattr(settings, name, "")
    ]
    if not missing:
        return []
    return [Error(
        "Payamito OTP is enabled but required credentials are missing.",
        hint="Set: " + ", ".join(missing),
        id="accounts.E001",
    )]
