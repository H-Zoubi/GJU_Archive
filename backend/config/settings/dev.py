"""Development settings."""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True
# "backend" is the docker-compose service name: the frontend container's Vite
# proxy forwards /api requests to http://backend:8000 with changeOrigin,
# which rewrites the Host header to match -- without it here, every proxied
# request 400s with DisallowedHost.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "backend"]

# The Vite dev server (proxying /api) is a different origin than Django, so
# trust it for CSRF-protected requests in development. Extra origins (a LAN
# IP, a Cloudflare Tunnel hostname) can be added via env without touching
# this file, since they vary per contributor's machine.
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    *env.list("DJANGO_EXTRA_CSRF_TRUSTED_ORIGINS", default=[]),
]

# Verification / reset emails print to the console in dev.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

INTERNAL_IPS = ["127.0.0.1"]
