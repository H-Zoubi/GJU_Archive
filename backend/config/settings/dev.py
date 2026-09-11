"""Development settings."""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# The Vite dev server (proxying /api) is a different origin than Django, so
# trust it for CSRF-protected requests in development.
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# Verification / reset emails print to the console in dev.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

INTERNAL_IPS = ["127.0.0.1"]
