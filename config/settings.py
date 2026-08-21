import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "changeme")
DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = ["*"] if DEBUG else os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "stations",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "static/"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ] if DEBUG else ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "routing.exceptions.custom_exception_handler",
}

# --- Fuel route optimizer config ---
ROUTING_API_BASE_URL = os.environ.get(
    "ROUTING_API_BASE_URL", "https://router.project-osrm.org"
)
GEOCODING_BASE_URL = os.environ.get(
    "GEOCODING_BASE_URL", "https://nominatim.openstreetmap.org"
)
GEOCODING_USER_AGENT = os.environ.get(
    "GEOCODING_USER_AGENT", "fuel-route-optimizer (spotter-ai-takehome)"
)

VEHICLE_RANGE_MILES = 500
VEHICLE_MPG = 10
CORRIDOR_THRESHOLD_MILES = 5
CORRIDOR_WIDEN_STEPS_MILES = [5, 15, 30]
BBOX_PADDING_DEGREES = 0.6
DEFAULT_PRICE_SEARCH_RADIUS_MILES = 50

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "routing": {"handlers": ["console"], "level": "INFO"},
    },
}
