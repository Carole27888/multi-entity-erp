"""Local development: `python manage.py runserver` runs everything."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool("DEBUG", default=True)

# Serve from app static folders without collectstatic (no staticfiles/ dir needed).
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True
