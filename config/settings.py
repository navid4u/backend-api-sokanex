from datetime import timedelta
from pathlib import Path

from decouple import config


BASE_DIR = Path(__file__).resolve().parent.parent


def get_list_setting(name, default=""):
    """
    Convert a comma-separated environment variable
    into a clean Python list.
    """
    return [
        item.strip()
        for item in config(
            name,
            default=default,
        ).split(",")
        if item.strip()
    ]


# --------------------------------------------------
# Core settings
# --------------------------------------------------

SECRET_KEY = config("SECRET_KEY")

DEBUG = config(
    "DEBUG",
    default=False,
    cast=bool,
)

ALLOWED_HOSTS = get_list_setting(
    "ALLOWED_HOSTS",
    "127.0.0.1,localhost,api.sokanex.com",
)


# --------------------------------------------------
# Applications
# --------------------------------------------------

INSTALLED_APPS = [
    "daphne",
    # Local user model
    "apps.accounts",
    "apps.activity",

    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "corsheaders",
    "django_filters",
    "rest_framework",
    "drf_spectacular",
    (
    "rest_framework_simplejwt."
        "token_blacklist"
    ),
    "channels",

    # Project apps
    "apps.dashboard",
    "apps.signals",
    "apps.wallet",
    "apps.articles",
    "apps.videos",
    "apps.brokers",
    "apps.chat",
    "apps.livestream",
    "apps.notifications",
    "apps.academy",
    "apps.market",
    "apps.content_channels",
    "apps.platform_settings",
    "landing",
]


# --------------------------------------------------
# Middleware
# --------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",

    # Must remain before CommonMiddleware
    "corsheaders.middleware.CorsMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    (
        "django.contrib.auth.middleware."
        "AuthenticationMiddleware"
    ),
    (
        "django.contrib.messages.middleware."
        "MessageMiddleware"
    ),
    (
        "django.middleware.clickjacking."
        "XFrameOptionsMiddleware"
    ),
]


ROOT_URLCONF = "config.urls"


# --------------------------------------------------
# Templates
# --------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": (
            "django.template.backends.django."
            "DjangoTemplates"
        ),
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                (
                    "django.template."
                    "context_processors.request"
                ),
                (
                    "django.contrib.auth."
                    "context_processors.auth"
                ),
                (
                    "django.contrib.messages."
                    "context_processors.messages"
                ),
            ],
        },
    },
]


WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# --------------------------------------------------
# Database
# --------------------------------------------------

DB_ENGINE = config(
    "DB_ENGINE",
    default="sqlite",
).strip().lower()


if DB_ENGINE == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": (
                "django.db.backends.postgresql"
            ),
            "NAME": config("DB_NAME"),
            "USER": config("DB_USER"),
            "PASSWORD": config(
                "DB_PASSWORD"
            ),
            "HOST": config(
                "DB_HOST",
                default="127.0.0.1",
            ),
            "PORT": config(
                "DB_PORT",
                default="5432",
            ),
            "CONN_MAX_AGE": config(
                "DB_CONN_MAX_AGE",
                default=60,
                cast=int,
            ),
        }
    }

    if config(
        "DB_SSL_REQUIRE",
        default=False,
        cast=bool,
    ):
        DATABASES["default"]["OPTIONS"] = {
            "sslmode": "require",
        }

elif DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": (
                "django.db.backends.sqlite3"
            ),
            "NAME": (
                BASE_DIR / "db.sqlite3"
            ),
        }
    }

else:
    raise ValueError(
        "DB_ENGINE must be either "
        "'sqlite' or 'postgresql'."
    )


# --------------------------------------------------
# Custom user model
# --------------------------------------------------

AUTH_USER_MODEL = "accounts.User"


# --------------------------------------------------
# Password validation
# --------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth."
            "password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth."
            "password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth."
            "password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth."
            "password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# --------------------------------------------------
# Internationalization
# --------------------------------------------------

LANGUAGE_CODE = "en-us"

# API timestamps are stored consistently in UTC.
TIME_ZONE = "UTC"

USE_I18N = True
USE_TZ = True


# --------------------------------------------------
# Static and media files
# --------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
FILE_UPLOAD_PERMISSIONS = 0o644
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o755


# --------------------------------------------------
# Django REST Framework
# --------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        (
            "rest_framework_simplejwt."
            "authentication."
            "JWTAuthentication"
        ),
    ),

    "DEFAULT_PERMISSION_CLASSES": (
        (
            "rest_framework.permissions."
            "IsAuthenticated"
        ),
    ),

    "DEFAULT_PAGINATION_CLASS": (
        "common.pagination.DefaultPagination"
    ),

    "DEFAULT_FILTER_BACKENDS": [
        (
            "django_filters.rest_framework."
            "DjangoFilterBackend"
        ),
        (
            "rest_framework.filters."
            "SearchFilter"
        ),
        (
            "rest_framework.filters."
            "OrderingFilter"
        ),
    ],

    "EXCEPTION_HANDLER": (
        "common.exceptions."
        "custom_exception_handler"
    ),

    "DEFAULT_SCHEMA_CLASS": (
        "drf_spectacular.openapi."
        "AutoSchema"
    ),

    "DEFAULT_THROTTLE_RATES": {
        "login": config(
            "LOGIN_THROTTLE_RATE",
            default="5/minute",
        ),
        "register": config(
            "REGISTER_THROTTLE_RATE",
            default="3/hour",
        ),
        "otp_request": config("OTP_REQUEST_THROTTLE_RATE", default="3/10min"),
        "support_message": config("SUPPORT_MESSAGE_THROTTLE_RATE", default="30/minute"),
        "market_quotes": config("MARKET_QUOTES_THROTTLE_RATE", default="60/minute"),
        "market_news": config("MARKET_NEWS_THROTTLE_RATE", default="30/minute"),
        "market_charts": config("MARKET_CHARTS_THROTTLE_RATE", default="60/minute"),
    },
}


# --------------------------------------------------
# JWT
# --------------------------------------------------

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config(
            "JWT_ACCESS_MINUTES",
            default=30,
            cast=int,
        )
    ),

    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config(
            "JWT_REFRESH_DAYS",
            default=30,
            cast=int,
        )
    ),

    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,

    "UPDATE_LAST_LOGIN": True,

    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,

    "AUTH_HEADER_TYPES": (
        "Bearer",
    ),

    "AUTH_HEADER_NAME": (
        "HTTP_AUTHORIZATION"
    ),

    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",

    "TOKEN_TYPE_CLAIM": "token_type",
}


# --------------------------------------------------
# React / CORS / CSRF
# --------------------------------------------------

CORS_ALLOWED_ORIGINS = get_list_setting(
    "CORS_ALLOWED_ORIGINS",
    (
        "http://localhost:3000,"
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "https://sokanex.com,"
        "https://www.sokanex.com"
        ",https://app.sokanex.com"
    ),
)

CSRF_TRUSTED_ORIGINS = get_list_setting(
    "CSRF_TRUSTED_ORIGINS",
    (
        "http://localhost:3000,"
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "https://sokanex.com,"
        "https://www.sokanex.com"
        ",https://app.sokanex.com"
    ),
)

# React sends JWT in the Authorization header.
CORS_ALLOW_CREDENTIALS = False

PAYAMITO_ENABLED = config("PAYAMITO_ENABLED", default=False, cast=bool)
PAYAMITO_USERNAME = config("PAYAMITO_USERNAME", default="")
PAYAMITO_API_KEY = config("PAYAMITO_API_KEY", default="")
PAYAMITO_FROM_NUMBER = config("PAYAMITO_FROM_NUMBER", default="9981803296")
PAYAMITO_TIMEOUT_SECONDS = config("PAYAMITO_TIMEOUT_SECONDS", default=15, cast=int)
PAYAMITO_OTP_MESSAGE_TEMPLATE = config(
    "PAYAMITO_OTP_MESSAGE_TEMPLATE",
    default="کد ورود شما به سوکانکس: {code}\nاین کد تا ۲ دقیقه معتبر است.",
)
PAYAMITO_NOTIFICATION_MESSAGE_TEMPLATE = config(
    "PAYAMITO_NOTIFICATION_MESSAGE_TEMPLATE",
    default="{title}\n{message}\n{target_url}",
).replace("\\n", "\n")
PAYAMITO_NOTIFICATION_LINK_BASE_URL = config(
    "PAYAMITO_NOTIFICATION_LINK_BASE_URL", default="https://app.sokanex.com"
)
PAYAMITO_NOTIFICATION_SMS_MAX_LENGTH = config(
    "PAYAMITO_NOTIFICATION_SMS_MAX_LENGTH", default=500, cast=int
)
PAYAMITO_SMS_RETRY_LIMIT = config("PAYAMITO_SMS_RETRY_LIMIT", default=3, cast=int)
PAYAMITO_SMS_SEND_INLINE = config("PAYAMITO_SMS_SEND_INLINE", default=False, cast=bool)
PAYMENT_PROVIDER_TIMEOUT_SECONDS = config("PAYMENT_PROVIDER_TIMEOUT_SECONDS", default=15, cast=int)
PAYMENT_PROVIDER_RETRY_LIMIT = config("PAYMENT_PROVIDER_RETRY_LIMIT", default=1, cast=int)
PAYMENT_CALLBACK_BASE_URL = config("PAYMENT_CALLBACK_BASE_URL", default="https://api.sokanex.com")
ZARINPAL_MERCHANT_ID = config("ZARINPAL_MERCHANT_ID", default="")
IDPAY_API_KEY = config("IDPAY_API_KEY", default="")
IDPAY_SANDBOX = config("IDPAY_SANDBOX", default=False, cast=bool)
MARKET_DATA_PROVIDER = config("MARKET_DATA_PROVIDER", default="")
MARKET_DATA_PROVIDER_URL = config("MARKET_DATA_PROVIDER_URL", default="")
MARKET_DATA_API_KEY = config("MARKET_DATA_API_KEY", default="")
MARKET_DATA_TIMEOUT_SECONDS = config("MARKET_DATA_TIMEOUT_SECONDS", default=8, cast=int)
MARKET_DATA_CACHE_SECONDS = config("MARKET_DATA_CACHE_SECONDS", default=60, cast=int)
MARKET_DATA_STALE_SECONDS = config("MARKET_DATA_STALE_SECONDS", default=86400, cast=int)
MARKET_DATA_RETRY_COUNT = config("MARKET_DATA_RETRY_COUNT", default=1, cast=int)
MARKET_CHART_TIMEOUT_SECONDS = config("MARKET_CHART_TIMEOUT_SECONDS", default=6, cast=int)
MARKET_CHART_CRYPTO_TTL = config("MARKET_CHART_CRYPTO_TTL", default=90, cast=int)
MARKET_CHART_FOREX_TTL = config("MARKET_CHART_FOREX_TTL", default=600, cast=int)
MARKET_CHART_STALE_TTL = config("MARKET_CHART_STALE_TTL", default=86400, cast=int)
MARKET_CHART_ALLOWED_INTERVALS = ("5m", "15m", "1h", "4h", "1d")
FOREX_CHART_PROVIDER_URL = config("FOREX_CHART_PROVIDER_URL", default="")
FOREX_CHART_PROVIDER_KEY = config("FOREX_CHART_PROVIDER_KEY", default="")
GOLD_CHART_PROVIDER_URL = config("GOLD_CHART_PROVIDER_URL", default="")
GOLD_CHART_PROVIDER_KEY = config("GOLD_CHART_PROVIDER_KEY", default="")
MARKET_CIRCUIT_BREAKER_FAILURES = config("MARKET_CIRCUIT_BREAKER_FAILURES", default=3, cast=int)
MARKET_CIRCUIT_BREAKER_SECONDS = config("MARKET_CIRCUIT_BREAKER_SECONDS", default=60, cast=int)
BRSAPI_API_KEY = config("BRSAPI_API_KEY", default="")
BRSAPI_PRICES_IN_RIAL = config("BRSAPI_PRICES_IN_RIAL", default=False, cast=bool)
TGJU_ENABLED = config("TGJU_ENABLED", default=False, cast=bool)
TGJU_API_URL = config("TGJU_API_URL", default="https://call5.tgju.org/ajax.json")
MARKET_HTTP_USER_AGENT = config("MARKET_HTTP_USER_AGENT", default="SokanexBackend/2.0 (+https://sokanex.com)")
MARKET_NEWS_TIMEOUT_SECONDS = config("MARKET_NEWS_TIMEOUT_SECONDS", default=8, cast=int)
MARKET_NEWS_MAX_BYTES = config("MARKET_NEWS_MAX_BYTES", default=2097152, cast=int)
MARKET_NEWS_ITEMS_PER_SOURCE = config("MARKET_NEWS_ITEMS_PER_SOURCE", default=50, cast=int)
ECONOMIC_CALENDAR_PROVIDER = config("ECONOMIC_CALENDAR_PROVIDER", default="")
ECONOMIC_CALENDAR_API_KEY = config("ECONOMIC_CALENDAR_API_KEY", default="")
CHANNEL_TICKET_TTL_SECONDS = config("CHANNEL_TICKET_TTL_SECONDS", default=60, cast=int)
SUPPORT_USERNAME = config("SUPPORT_USERNAME", default="support")
REDIS_URL = config("REDIS_URL", default="")
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer" if REDIS_URL else "channels.layers.InMemoryChannelLayer",
        **({"CONFIG": {"hosts": [REDIS_URL]}} if REDIS_URL else {}),
    }
}
MEDIA_MAX_IMAGE_MB = config("MEDIA_MAX_IMAGE_MB", default=10, cast=int)
MEDIA_MAX_AUDIO_MB = config("MEDIA_MAX_AUDIO_MB", default=50, cast=int)
MEDIA_MAX_VIDEO_MB = config("MEDIA_MAX_VIDEO_MB", default=1024, cast=int)


# --------------------------------------------------
# Upload limits
# --------------------------------------------------

# Files larger than this value are streamed to
# temporary files instead of remaining in memory.
FILE_UPLOAD_MAX_MEMORY_SIZE = (
    5 * 1024 * 1024
)

# Allows chat attachments up to serializer limits.
DATA_UPLOAD_MAX_MEMORY_SIZE = config(
    "DATA_UPLOAD_MAX_MEMORY_SIZE",
    default=550 * 1024 * 1024,
    cast=int,
)


# --------------------------------------------------
# Security
# --------------------------------------------------

SECURE_CONTENT_TYPE_NOSNIFF = True

X_FRAME_OPTIONS = "DENY"

SECURE_REFERRER_POLICY = (
    "strict-origin-when-cross-origin"
)

SECURE_SSL_REDIRECT = config(
    "SECURE_SSL_REDIRECT",
    default=False,
    cast=bool,
)

SESSION_COOKIE_SECURE = config(
    "SESSION_COOKIE_SECURE",
    default=False,
    cast=bool,
)

CSRF_COOKIE_SECURE = config(
    "CSRF_COOKIE_SECURE",
    default=False,
    cast=bool,
)

SECURE_HSTS_SECONDS = config(
    "SECURE_HSTS_SECONDS",
    default=0,
    cast=int,
)

SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=False,
    cast=bool,
)

SECURE_HSTS_PRELOAD = config(
    "SECURE_HSTS_PRELOAD",
    default=False,
    cast=bool,
)

if config(
    "USE_X_FORWARDED_PROTO",
    default=False,
    cast=bool,
):
    SECURE_PROXY_SSL_HEADER = (
        "HTTP_X_FORWARDED_PROTO",
        "https",
    )


# --------------------------------------------------
# API documentation
# --------------------------------------------------

SPECTACULAR_SETTINGS = {
    "TITLE": "Trading Platform API",

    "DESCRIPTION": (
        "REST API for the Trading Platform "
        "React dashboard."
    ),

    "VERSION": "1.0.0",

    "SERVE_INCLUDE_SCHEMA": False,

    "COMPONENT_SPLIT_REQUEST": True,

    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayRequestDuration": True,
    },

        "ENUM_NAME_OVERRIDES": {
        "UserRoleEnum": (
            "apps.accounts.models."
            "User.Role"
        ),
        "UserAccessLevelEnum": (
            "apps.accounts.models."
            "User.AccessLevel"
        ),
        "PlatformPermissionEnum": (
            "apps.accounts.models."
            "User.Permission"
        ),
        "UpgradeRequestTypeEnum": (
            "apps.accounts.models."
            "UpgradeRequest.Type"
        ),
        "UpgradeRequestStatusEnum": (
            "apps.accounts.models."
            "UpgradeRequest.Status"
        ),

        "ContentStatusEnum": (
            "apps.articles.models."
            "Article.Status"
        ),

        "SignalStatusEnum": (
            "apps.signals.models."
            "SignalStatus"
        ),

        "SignalMarketEnum": (
            "apps.signals.models."
            "MarketType"
        ),

        "SignalDirectionEnum": (
            "apps.signals.models."
            "Direction"
        ),

        "LiveEventStatusEnum": (
            "apps.livestream.models."
            "LiveEvent.Status"
        ),
        "NotificationTypeEnum": (
            "apps.notifications.models."
            "Notification.Type"
        ),

        "ChatMembershipRoleEnum": (
            "apps.chat.models."
            "RoomMembership.Role"
        ),
        "InternalAnalysisScopeEnum": (
            "apps.content_channels.models."
            "ChannelPost.Scope"
        ),
        "InternalAnalysisStatusEnum": (
            "apps.content_channels.models."
            "ChannelPost.Status"
        ),
        "SupportConversationStatusEnum": (
            "apps.chat.models."
            "SupportThread.Status"
        ),
        "SupportConversationPriorityEnum": (
            "apps.chat.models."
            "SupportThread.Priority"
        ),

        "TransactionTypeEnum": (
            "apps.wallet.models."
            "Transaction.Type"
        ),

        "TransactionStatusEnum": (
            "apps.wallet.models."
            "Transaction.Status"
        ),
    },
}


DEFAULT_AUTO_FIELD = (
    "django.db.models.BigAutoField"
)
# --------------------------------------------------
# Logging
# --------------------------------------------------

LOGGING = {
    "version": 1,

    "disable_existing_loggers": False,

    "formatters": {
        "verbose": {
            "format": (
                "{levelname} "
                "{asctime} "
                "{name} "
                "{module} "
                "{process:d} "
                "{thread:d} "
                "{message}"
            ),
            "style": "{",
        },

        "simple": {
            "format": (
                "{levelname} "
                "{asctime} "
                "{name}: "
                "{message}"
            ),
            "style": "{",
        },
    },

    "handlers": {
        "console": {
            "class": (
                "logging.StreamHandler"
            ),
            "formatter": (
                "verbose"
                if DEBUG
                else "simple"
            ),
        },
    },

    "root": {
        "handlers": [
            "console",
        ],
        "level": (
            "INFO"
            if DEBUG
            else "WARNING"
        ),
    },

    "loggers": {
        "django": {
            "handlers": [
                "console",
            ],
            "level": (
                "INFO"
                if DEBUG
                else "WARNING"
            ),
            "propagate": False,
        },

        "django.request": {
            "handlers": [
                "console",
            ],
            "level": "ERROR",
            "propagate": False,
        },

        "django.security": {
            "handlers": [
                "console",
            ],
            "level": "WARNING",
            "propagate": False,
        },

        "django.db.backends": {
            "handlers": [
                "console",
            ],
            "level": "WARNING",
            "propagate": False,
        },

        "apps": {
            "handlers": [
                "console",
            ],
            "level": (
                "DEBUG"
                if DEBUG
                else "INFO"
            ),
            "propagate": False,
        },

        "common": {
            "handlers": [
                "console",
            ],
            "level": (
                "DEBUG"
                if DEBUG
                else "INFO"
            ),
            "propagate": False,
        },
    },
}
