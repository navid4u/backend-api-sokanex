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
    "127.0.0.1,localhost",
)


# --------------------------------------------------
# Applications
# --------------------------------------------------

INSTALLED_APPS = [
    # Local user model
    "apps.accounts",

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
        "rest_framework.pagination."
        "PageNumberPagination"
    ),

    "PAGE_SIZE": 20,

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
    },
}


# --------------------------------------------------
# JWT
# --------------------------------------------------

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config(
            "JWT_ACCESS_MINUTES",
            default=15,
            cast=int,
        )
    ),

    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config(
            "JWT_REFRESH_DAYS",
            default=7,
            cast=int,
        )
    ),

    # Logout blacklisting is performed explicitly
    # by LogoutSerializer.
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,

    "UPDATE_LAST_LOGIN": False,

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
        "http://localhost:5173"
    ),
)

CSRF_TRUSTED_ORIGINS = get_list_setting(
    "CSRF_TRUSTED_ORIGINS",
    (
        "http://localhost:3000,"
        "http://localhost:5173"
    ),
)

# React sends JWT in the Authorization header.
CORS_ALLOW_CREDENTIALS = False


# --------------------------------------------------
# Upload limits
# --------------------------------------------------

# Files larger than this value are streamed to
# temporary files instead of remaining in memory.
FILE_UPLOAD_MAX_MEMORY_SIZE = (
    5 * 1024 * 1024
)

# Allows chat attachments up to serializer limits.
DATA_UPLOAD_MAX_MEMORY_SIZE = (
    25 * 1024 * 1024
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
        "ContentStatusEnum": [
            (
                "DRAFT",
                "Draft",
            ),
            (
                "PUBLISHED",
                "Published",
            ),
        ],

        "SignalStatusEnum": [
            (
                "draft",
                "Draft",
            ),
            (
                "pending",
                "Pending",
            ),
            (
                "approved",
                "Approved",
            ),
            (
                "rejected",
                "Rejected",
            ),
        ],

        "LiveEventStatusEnum": [
            (
                "SCHEDULED",
                "Scheduled",
            ),
            (
                "LIVE",
                "Live",
            ),
            (
                "ENDED",
                "Ended",
            ),
            (
                "CANCELLED",
                "Cancelled",
            ),
        ],

        "TransactionStatusEnum": [
            (
                "PENDING",
                "Pending",
            ),
            (
                "COMPLETED",
                "Completed",
            ),
            (
                "FAILED",
                "Failed",
            ),
        ],
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