"""
Base settings shared by all environments.

Environment-specific settings live in dev.py / prod.py, which import from here.
Configuration is read from the environment (see .env.example).
"""
from pathlib import Path

import environ

# backend/config/settings/base.py -> backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:5173"]),
    GJU_EMAIL_DOMAINS=(list, ["gju.edu.jo"]),
)

# Read .env if present (never committed).
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(env_file)

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Which email domains count as GJU members (checked at signup).
GJU_EMAIL_DOMAINS = env("GJU_EMAIL_DOMAINS")

# --- Applications ---------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
]

LOCAL_APPS = [
    "common",
    "accounts",
    "academics",
    "resources",
    "moderation",
    "integrations",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database -------------------------------------------------------------
# Defaults to local SQLite so the project runs with zero setup; docker-compose
# provides Postgres and sets DATABASE_URL.
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

# --- Auth -----------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

# Argon2 first: strongest built-in hasher, used for the local login hash.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- GJU credential verifier ---------------------------------------------
# At first-time signup, an unknown GJU email/password is checked against the
# MyGJU portal via a Playwright browser (see accounts/gju_verifier). MyGJU's
# WAF blocks browsers that carry an automation fingerprint; the verifier strips
# that fingerprint, which lets it run fully headless (no visible window, and no
# virtual display needed on a server). Set headless False only to watch it.
GJU_VERIFIER_ENABLED = env.bool("GJU_VERIFIER_ENABLED", default=True)
GJU_VERIFIER_HEADLESS = env.bool("GJU_VERIFIER_HEADLESS", default=True)
GJU_VERIFIER_TIMEOUT_MS = env.int("GJU_VERIFIER_TIMEOUT_MS", default=15000)
# Circuit breaker: after this many consecutive "unavailable" results the
# verifier stops making live attempts for the cooldown window, so a WAF block
# or portal outage can't burn the shared server IP across a burst of signups.
GJU_VERIFIER_BREAKER_THRESHOLD = env.int("GJU_VERIFIER_BREAKER_THRESHOLD", default=3)
GJU_VERIFIER_BREAKER_COOLDOWN_S = env.int("GJU_VERIFIER_BREAKER_COOLDOWN_S", default=1800)

# --- DRF ------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        # Only the ingest API (importer jobs running as separate processes,
        # with no session/CSRF of their own) actually accepts a token; every
        # other view's permission class still requires a real student login.
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    # Uploads are the expensive, abusable endpoint: each one reserves a row and
    # hands out a signed URL to write to the bucket.
    "DEFAULT_THROTTLE_RATES": {
        "upload": env("UPLOAD_THROTTLE_RATE", default="30/day"),
    },
}

# --- Internationalization -------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Amman"
USE_I18N = True
USE_TZ = True

# --- Object storage (S3-compatible) --------------------------------------
# MinIO in dev, Cloudflare R2 / AWS S3 in production. Only the endpoint and
# keys change between them; boto3 presigned URLs work identically against all.
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", default="http://localhost:9000")
S3_ACCESS_KEY = env("S3_ACCESS_KEY", default="minioadmin")
S3_SECRET_KEY = env("S3_SECRET_KEY", default="minioadmin")
S3_BUCKET = env("S3_BUCKET", default="gju-vault-dev")
S3_REGION = env("S3_REGION", default="us-east-1")
# Public base URL the *browser* uses to reach the bucket. Differs from
# S3_ENDPOINT_URL when Django talks to MinIO over a docker network name while
# the browser reaches it on localhost. Empty means "same as the endpoint".
S3_PUBLIC_ENDPOINT_URL = env("S3_PUBLIC_ENDPOINT_URL", default="")

# Presigned URL lifetimes, in seconds. Short by design: an upload URL only has
# to survive one PUT, and a download URL is shareable until it expires.
S3_UPLOAD_URL_TTL = env.int("S3_UPLOAD_URL_TTL", default=900)      # 15 min
S3_DOWNLOAD_URL_TTL = env.int("S3_DOWNLOAD_URL_TTL", default=300)  # 5 min

# --- Uploads --------------------------------------------------------------
MAX_UPLOAD_BYTES = env.int("MAX_UPLOAD_BYTES", default=50 * 1024 * 1024)  # 50 MB

# --- Static / media -------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- CORS -----------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
