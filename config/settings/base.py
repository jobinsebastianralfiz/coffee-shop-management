"""
Django base settings for Coffee Shop Management System.

These settings are shared across all environments.
"""

from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# =============================================================================
# CORE SETTINGS
# =============================================================================

SECRET_KEY = config("SECRET_KEY", default="django-insecure-change-me-in-production")

DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())


# =============================================================================
# APPLICATION DEFINITION
# =============================================================================

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "channels",
    "django_celery_beat",
    "drf_spectacular",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.menu",
    "apps.tables",
    "apps.orders",
    "apps.payments",
    "apps.kitchen",
    "apps.inventory",
    "apps.reports",
    "apps.notifications",
    "apps.dashboard",
    "apps.ordering",
    "apps.finance",
    "apps.waiter",
    "apps.printing",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# =============================================================================
# MIDDLEWARE
# =============================================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.OutletContextMiddleware",  # Add outlet context to requests
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.NoCacheMiddleware",  # Prevent back button after logout
]


# =============================================================================
# URLS
# =============================================================================

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"

ASGI_APPLICATION = "config.asgi.application"


# =============================================================================
# TEMPLATES
# =============================================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Custom context processors
                "apps.core.context_processors.business_settings",
                "apps.core.context_processors.app_settings",
            ],
        },
    },
]


# =============================================================================
# DATABASE
# =============================================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="coffeeshop"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD", default="postgres"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
    }
}


# =============================================================================
# AUTHENTICATION
# =============================================================================

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# =============================================================================
# INTERNATIONALIZATION
# =============================================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = config("TIME_ZONE", default="Asia/Kolkata")

USE_I18N = True

USE_TZ = True


# =============================================================================
# STATIC FILES
# =============================================================================

STATIC_URL = "/static/"

STATICFILES_DIRS = [BASE_DIR / "static"]

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# =============================================================================
# MEDIA FILES
# =============================================================================

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"


# =============================================================================
# DEFAULT PRIMARY KEY
# =============================================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# =============================================================================
# REDIS
# =============================================================================

REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")


# =============================================================================
# CHANNELS (WebSocket)
# =============================================================================

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}


# =============================================================================
# CELERY
# =============================================================================

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL)

CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_URL)

CELERY_ACCEPT_CONTENT = ["json"]

CELERY_TASK_SERIALIZER = "json"

CELERY_RESULT_SERIALIZER = "json"

CELERY_TIMEZONE = TIME_ZONE

CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"


# =============================================================================
# REST FRAMEWORK
# =============================================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "EXCEPTION_HANDLER": "rest_framework.views.exception_handler",
}


# =============================================================================
# JWT SETTINGS
# =============================================================================

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("JWT_ACCESS_TOKEN_LIFETIME", default=60, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        minutes=config("JWT_REFRESH_TOKEN_LIFETIME", default=1440, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}


# =============================================================================
# DRF SPECTACULAR (API Documentation)
# =============================================================================

SPECTACULAR_SETTINGS = {
    "TITLE": "Coffee Shop Management System API",
    "DESCRIPTION": "API documentation for the Coffee Shop Management System",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
}


# =============================================================================
# CORS SETTINGS
# =============================================================================

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000",
    cast=Csv(),
)


# =============================================================================
# PAYMENT SETTINGS
# =============================================================================

RAZORPAY_KEY_ID = config("RAZORPAY_KEY_ID", default="")

RAZORPAY_KEY_SECRET = config("RAZORPAY_KEY_SECRET", default="")


# =============================================================================
# NOTIFICATION SETTINGS
# =============================================================================

TWILIO_ACCOUNT_SID = config("TWILIO_ACCOUNT_SID", default="")

TWILIO_AUTH_TOKEN = config("TWILIO_AUTH_TOKEN", default="")

TWILIO_PHONE_NUMBER = config("TWILIO_PHONE_NUMBER", default="")


# =============================================================================
# BUSINESS DEFAULTS
# =============================================================================

DEFAULT_CURRENCY = config("DEFAULT_CURRENCY", default="INR")

DEFAULT_CURRENCY_SYMBOL = config("DEFAULT_CURRENCY_SYMBOL", default="₹")

DEFAULT_TAX_RATE = config("DEFAULT_TAX_RATE", default=5.0, cast=float)


# =============================================================================
# VENDOR PLAN SETTINGS (Only developer can configure via .env)
# =============================================================================

# Plan name for display purposes
PLAN_NAME = config("PLAN_NAME", default="Basic")

# Maximum outlets allowed (0 = unlimited)
MAX_OUTLETS = config("MAX_OUTLETS", default=1, cast=int)

# Maximum staff per outlet (0 = unlimited)
MAX_STAFF_PER_OUTLET = config("MAX_STAFF_PER_OUTLET", default=0, cast=int)

# Maximum tables per outlet (0 = unlimited)
MAX_TABLES_PER_OUTLET = config("MAX_TABLES_PER_OUTLET", default=0, cast=int)

# Plan features list (comma-separated for .env)
PLAN_FEATURES = config(
    "PLAN_FEATURES",
    default="POS System,Menu Management,Order Management,Table Management,Basic Reports",
    cast=Csv(),
)


# =============================================================================
# LOGIN SETTINGS
# =============================================================================

LOGIN_URL = "dashboard:login"

LOGIN_REDIRECT_URL = "dashboard:home"

LOGOUT_REDIRECT_URL = "dashboard:login"
