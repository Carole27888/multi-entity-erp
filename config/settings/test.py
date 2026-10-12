"""Test settings: fast hashing, inline jobs, in-memory cache and email."""

from .base import *  # noqa: F401,F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
JOBS_BACKEND = "sync"
TWO_FACTOR_ENFORCED = False  # individual tests switch it on
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
APP_HOST = "app.testplatform.co.ke"
PUBLIC_DOMAIN = "testplatform.co.ke"
APP_HOST_ALIASES = ["testserver", "localhost"]
SITE_URL = "http://testserver"
INTEGRATIONS = {**INTEGRATIONS, "SMS_PROVIDER": "mock"}  # noqa: F405

# Serve from app static folders without collectstatic (no staticfiles/ dir needed).
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True
