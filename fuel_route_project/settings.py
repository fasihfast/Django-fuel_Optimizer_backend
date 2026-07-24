"""
Django settings for fuel_route_project.

Coming from Spring Boot: this file is the rough equivalent of
application.properties / application.yml + your @Configuration classes,
all in one plain Python module.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Security -----------------------------------------------------------
# In a real production app this would come from an environment variable.
# Hardcoding is fine for a take-home assessment running locally.
SECRET_KEY = "django-insecure-CHANGE-ME-this-is-fine-for-a-local-take-home-demo"

DEBUG = True

ALLOWED_HOSTS = ["*"]

# --- Apps ----------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",   # Django REST Framework - like adding spring-boot-starter-web
    "routing",           # our own app - like a package/module in a Spring Boot project
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "fuel_route_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "fuel_route_project.wsgi.application"

# --- Database --------------------------------------------------------------
# SQLite is fine here - it's a single file, zero setup, perfect for a
# take-home project. In Spring Boot terms this is like using H2 file mode
# instead of spinning up Postgres.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []  # not needed, no user-facing auth in this project

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Django REST Framework ------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",  # nice HTML explorer at the URL too
    ],
}

# --- Project specific settings ---------------------------------------------
VEHICLE_MAX_RANGE_MILES = 500
VEHICLE_MPG = 10

# Free, no-API-key routing service (OSRM public demo server).
OSRM_BASE_URL = "https://router.project-osrm.org"

# Free, no-API-key geocoding service (Open-Meteo). 
# see routing/services/geocode.py
# for details.
GEOCODE_API_URL = "https://geocoding-api.open-meteo.com/v1/search"
