"""
Django production settings for Coffee Shop Management System.

These settings extend base.py for production deployment.
"""

import dj_database_url

from .base import *  # noqa: F401, F403

# =============================================================================
# DEBUG - Must be False in production
# =============================================================================

DEBUG = False


# =============================================================================
# SECURITY SETTINGS
# =============================================================================

# HTTPS Settings (Railway handles SSL at edge, so we disable redirect)
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)  # noqa: F405
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS Settings
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Content Security
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# CSRF Trusted Origins for Railway
CSRF_TRUSTED_ORIGINS = config(  # noqa: F405
    "CSRF_TRUSTED_ORIGINS",
    default="https://*.railway.app,https://*.up.railway.app",
    cast=Csv(),  # noqa: F405
)


# =============================================================================
# DATABASE - Railway PostgreSQL with DATABASE_URL support
# =============================================================================

DATABASE_URL = config("DATABASE_URL", default="")  # noqa: F405

if DATABASE_URL:
    DATABASES["default"] = dj_database_url.config(  # noqa: F405
        default=DATABASE_URL,
        conn_max_age=60,
        ssl_require=True,
    )
else:
    DATABASES["default"]["CONN_MAX_AGE"] = 60  # noqa: F405


# =============================================================================
# CACHING - Redis for production (optional on Railway)
# =============================================================================

REDIS_URL_PROD = config("REDIS_URL", default="")  # noqa: F405

if REDIS_URL_PROD:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL_PROD,
        }
    }
else:
    # Fallback to local memory cache if no Redis
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }


# =============================================================================
# EMAIL - Production SMTP
# =============================================================================

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")  # noqa: F405
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)  # noqa: F405
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")  # noqa: F405
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")  # noqa: F405
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@coffeeshop.com")  # noqa: F405


# =============================================================================
# STATIC FILES - Use WhiteNoise in production
# =============================================================================

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# =============================================================================
# LOGGING - Production logging
# =============================================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


# =============================================================================
# SENTRY (Error Monitoring) - Optional
# =============================================================================

SENTRY_DSN = config("SENTRY_DSN", default="")  # noqa: F405

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment="production",
    )
