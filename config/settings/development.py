"""
Django development settings for Coffee Shop Management System.

These settings extend base.py for local development.
"""

from .base import *  # noqa: F401, F403

# =============================================================================
# DEBUG
# =============================================================================

DEBUG = True


# =============================================================================
# ALLOWED HOSTS
# =============================================================================

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]


# =============================================================================
# INSTALLED APPS - Development extras
# =============================================================================

INSTALLED_APPS += [  # noqa: F405
    "django_extensions",
    "debug_toolbar",
]


# =============================================================================
# MIDDLEWARE - Development extras
# =============================================================================

MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405


# =============================================================================
# DEBUG TOOLBAR
# =============================================================================

INTERNAL_IPS = ["127.0.0.1", "localhost"]

DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
}


# =============================================================================
# DATABASE - SQLite for easy development (no PostgreSQL needed)
# =============================================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}


# =============================================================================
# EMAIL - Console backend for development
# =============================================================================

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# =============================================================================
# CACHING - Local memory for development
# =============================================================================

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}


# =============================================================================
# CHANNELS - In-memory for development (no Redis needed)
# =============================================================================

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}


# =============================================================================
# REST FRAMEWORK - Add browsable API for development
# =============================================================================

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]


# =============================================================================
# CORS - Allow all origins in development
# =============================================================================

CORS_ALLOW_ALL_ORIGINS = True


# =============================================================================
# LOGGING
# =============================================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
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
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
