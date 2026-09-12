"""Production settings. Requires real secrets via the environment."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# Must be provided in production.
SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS", default=[])

# --- Security hardening ---------------------------------------------------
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# --- Email ----------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="GJU Archive <no-reply@gjuarchive.com>")

# --- Secrets that must never fall back to base.py's dev defaults ----------
# base.py defaults these to well-known dev-only values (minioadmin, an empty
# Vault token, etc.) so a fresh local checkout works with zero config. That
# same fallback in production would mean a forgotten env var silently
# degrades to an insecure default instead of failing loudly -- override each
# one here with no default so a missing var raises ImproperlyConfigured at
# startup instead.
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL")
S3_ACCESS_KEY = env("S3_ACCESS_KEY")
S3_SECRET_KEY = env("S3_SECRET_KEY")
S3_BUCKET = env("S3_BUCKET")

# Exactly one of these two must be set (never both) -- see
# accounts/vault_transit.py. Both empty is also invalid: whichever one this
# process actually needs will still be "" and fail at first use, so require
# at least one here to catch a misconfigured deployment at startup instead.
if not env("VAULT_ENCRYPT_TOKEN", default="") and not env("VAULT_DECRYPT_TOKEN", default=""):
    raise ImproperlyConfigured(
        "Set exactly one of VAULT_ENCRYPT_TOKEN / VAULT_DECRYPT_TOKEN in production."
    )
