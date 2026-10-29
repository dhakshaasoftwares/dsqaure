"""
Django settings for the DSquare construction management app.

Everything that differs between a laptop install and a cloud server is read
from environment variables (see .env.example), so the same code runs anywhere.
"""

import os
from pathlib import Path

import dj_database_url
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEV_SECRET_KEY = "dev-only-insecure-key-change-me"
SECRET_KEY = os.environ.get("SECRET_KEY", DEV_SECRET_KEY)
DEBUG = env_bool("DEBUG", True)
if not DEBUG and SECRET_KEY in (DEV_SECRET_KEY, "change-me-to-a-long-random-string"):
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("Set a long random SECRET_KEY in .env before running with DEBUG=False.")
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.accounts",
    "apps.core",
    "apps.employees",
    "apps.attendance",
    "apps.payroll",
    "apps.inventory",
    "apps.progress",
    "apps.documents",
    "apps.billing",
    "apps.licensing",
    "apps.sharing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.UserLanguageMiddleware",
    "apps.licensing.middleware.LicenceMiddleware",
    "apps.core.middleware.CompanyMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
                "apps.core.context_processors.company",
                "apps.licensing.context_processors.licence",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite for quick local trials; set DATABASE_URL to PostgreSQL for real use.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600
    )
}

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
LANGUAGES = [("en", _("English")), ("ta", _("Tamil"))]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = os.environ.get("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Behind Cloudflare Tunnel the app sees plain HTTP; trust the forwarded scheme.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Turn on once everyone uses the https:// address. While staff still log in over
# plain http (http://localhost:8000 or the laptop's Wi-Fi IP) it must stay off,
# otherwise browsers drop the login cookie.
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = env_bool("SECURE_COOKIES", False)

DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000  # big attendance sheets and BOQs
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# Address used in links when there is no web request (e.g. https://selvam.example.com).
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")

# Licensing: days a new install works without a key, and how many users it allows meanwhile.
LICENCE_TRIAL_DAYS = int(os.environ.get("LICENCE_TRIAL_DAYS", 30))
LICENCE_TRIAL_USERS = int(os.environ.get("LICENCE_TRIAL_USERS", 10))

# Keep people logged in on their phones for 30 days.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
