"""OpenAPI mapping for the project's JWT subclass."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class PremiumStateJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.PremiumStateJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}


class FixedIngestionKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "common.ingestion.FixedIngestionKeyAuthentication"
    name = "sokanexIngestKey"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "header", "name": "X-Sokanex-Ingest-Key"}


class FixedSignalChannelKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "common.ingestion.FixedSignalChannelKeyAuthentication"
    name = "sokanexSignalKey"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "header", "name": "X-Sokanex-Signal-Key"}
