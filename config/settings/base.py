"""Shared settings. Every environment-specific value comes from `.env` (see .env.example)."""

import json
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# Process environment values win over the file (overwrite=False is the default).
environ.Env.read_env(str(BASE_DIR / ".env"))

# --- Product & platform ------------------------------------------------------
# The product name, domains and the platform company are settings so they can change without code edits.
PRODUCT_NAME = env("PRODUCT_NAME", default="Pamoja")
PRODUCT_TAGLINE = env("PRODUCT_TAGLINE", default="Your whole business, together")
PLATFORM_DOMAIN = env("PLATFORM_DOMAIN", default="domain.co.ke")
# Host of the staff app. Tenants live under it at /<org-slug>/ (TENANT_ROUTING=path).
APP_HOST = env("APP_HOST", default=f"app.{PLATFORM_DOMAIN}")
# Extra hosts that also serve the staff app (local development, the test client).
APP_HOST_ALIASES = env.list("APP_HOST_ALIASES", default=["localhost", "127.0.0.1", "testserver"])
# Domain under which public sites get <org-slug>.<PUBLIC_DOMAIN> when WILDCARD_SUBDOMAINS is on.
PUBLIC_DOMAIN = env("PUBLIC_DOMAIN", default=PLATFORM_DOMAIN)
# Off until the host provides a wildcard DNS record and wildcard TLS certificate for *.PUBLIC_DOMAIN.
# While off, public sites are served at https://APP_HOST/s/<org-slug>/ (custom domains work either way).
WILDCARD_SUBDOMAINS = env.bool("WILDCARD_SUBDOMAINS", default=False)
# "path": staff app at APP_HOST/<org-slug>/…  ·  "subdomain": staff app at <org-slug>.APP_HOST/…
TENANT_ROUTING = env("TENANT_ROUTING", default="path")
SUPPORT_EMAIL = env("SUPPORT_EMAIL", default=f"support@{PLATFORM_DOMAIN}")

# The platform company (bills tenants for their subscriptions). Placeholders until the real details are given.
PLATFORM_COMPANY = {
    "legal_name": env("PLATFORM_LEGAL_NAME", default="[PLATFORM LEGAL NAME] Ltd"),
    "kra_pin": env("PLATFORM_KRA_PIN", default="P000000000X"),
    "vat_registered": env.bool("PLATFORM_VAT_REGISTERED", default=False),
    "paybill": env("PLATFORM_PAYBILL", default="000000"),
    "address": env("PLATFORM_ADDRESS", default="Nairobi, Kenya"),
}

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DEBUG", default=False)
# Custom domains are added by tenants at run time, so Django's host check is replaced by
# apps.tenancy.middleware.TenantMiddleware, which answers 400 for any host it does not know.
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
SITE_URL = env("SITE_URL", default="http://localhost:8000").rstrip("/")

INSTALLED_APPS = [
    "apps.core.admin_config.PlatformAdminConfig",  # Django admin, platform staff only
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Third party
    "django_htmx",
    "django_filters",
    "rest_framework",
    "simple_history",
    # Platform
    "apps.core",
    "apps.tenancy",
    "apps.accounts",
    "apps.billing",
    "apps.industries",
    "apps.integrations",
    "apps.onboarding",
    "apps.orgsettings",
    "apps.platformadmin",
    "apps.website",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.tenancy.middleware.TenantMiddleware",  # host/path → organization, URLconf and script prefix
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.accounts.middleware.TwoFactorMiddleware",
    "apps.accounts.middleware.SessionTimeoutMiddleware",
    "apps.tenancy.middleware.MembershipMiddleware",  # staff URLs need an active membership in the org
    "apps.tenancy.middleware.OrganizationStatusMiddleware",  # suspended / read-only organizations
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "apps.core.middleware.CurrentUserMiddleware",
]

ROOT_URLCONF = "config.urls"  # platform pages; tenant and public requests switch URLConf in TenantMiddleware
TENANT_URLCONF = "config.urls_tenant"
PUBLIC_URLCONF = "config.urls_public"
WSGI_APPLICATION = "config.wsgi.application"

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
                "apps.core.context_processors.app_shell",
            ],
            "builtins": ["apps.core.templatetags.core_tags"],
        },
    },
]

# --- Database: selected only through DATABASE_URL ----------------------------
if env("DB_MYSQL_DRIVER", default="") == "pymysql":
    import pymysql

    pymysql.install_as_MySQLdb()

DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}
_db_options = json.loads(env("DB_OPTIONS", default="{}") or "{}")
for _db in DATABASES.values():
    _db["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
    _db["CONN_HEALTH_CHECKS"] = env.bool("DB_CONN_HEALTH_CHECKS", default=True)
    _db.setdefault("OPTIONS", {}).update(_db_options)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Auth ------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailBackend"]
# Plain paths (not URL names): tenant requests use another URLConf, where these names don't exist.
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/orgs/"
LOGOUT_REDIRECT_URL = "/accounts/login/"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_RESET_TIMEOUT = 60 * 60 * 3  # reset links work for 3 hours
# "Keep me signed in" keeps installed-app users signed in for 30 days (shorter for roles that handle money, see Role).
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=60 * 60 * 24 * 30)
LOGIN_RATE_LIMIT = env.int("LOGIN_RATE_LIMIT", default=5)  # failed attempts per 15 min per IP + email
SIGNUP_RATE_LIMIT = env.int("SIGNUP_RATE_LIMIT", default=5)  # sign-ups per hour per IP
EMAIL_VERIFICATION_DAYS = 3

# --- Two-factor login --------------------------------------------------------
# Built-in Owner, Admin and Finance roles (and custom roles with "two-factor required") must use an authenticator
# app. Set TWO_FACTOR_ENFORCED=False only for a local demo; anyone who turned it on for themselves is still asked.
TWO_FACTOR_ENFORCED = env.bool("TWO_FACTOR_ENFORCED", default=True)
TWO_FACTOR_ISSUER = env("TWO_FACTOR_ISSUER", default=PRODUCT_NAME)

# --- Locale ----------------------------------------------------------------
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Nairobi"  # platform default; each organization has its own time zone
USE_I18N = True
USE_TZ = True
DEFAULT_CURRENCY = "KES"
DEFAULT_COUNTRY = "KE"

# --- Static & media --------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(env("STATIC_ROOT", default=str(BASE_DIR / "staticfiles")))
# Uploaded files are stored under MEDIA_ROOT/<org-id>/… and are NEVER served by URL: only by permission-checked
# views (apps.core.files). Keep MEDIA_ROOT outside public_html on cPanel.
MEDIA_URL = "/_media_not_served/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))
FILE_UPLOAD_MAX_MB = env.int("FILE_UPLOAD_MAX_MB", default=10)
DATA_UPLOAD_MAX_MEMORY_SIZE = FILE_UPLOAD_MAX_MB * 1024 * 1024
# Apache with mod_xsendfile can stream permission-checked files itself (set to True only if it is enabled).
USE_X_SENDFILE = env.bool("USE_X_SENDFILE", default=False)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# --- Cache & email ---------------------------------------------------------
# Shared by every Passenger process, so rate limits and cached counters hold across processes.
# The database cache needs no extra service; `createcachetable` runs from post_migrate.
CACHES = {"default": env.cache("CACHE_URL", default="dbcache://platform_cache")}
EMAIL_CONFIG = env.email("EMAIL_URL", default="consolemail://")
vars().update(EMAIL_CONFIG)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=f"{PRODUCT_NAME} <no-reply@{PLATFORM_DOMAIN}>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
ADMINS = [tuple(a.split(":", 1)) for a in env.list("ADMINS", default=[]) if ":" in a]

# --- Background jobs -------------------------------------------------------
JOBS_BACKEND = env("JOBS_BACKEND", default="sync")  # sync (inline) | cron (manage.py run_jobs every 5 minutes)
JOBS_MAX_ATTEMPTS = 3
JOBS_RUN_TIME_LIMIT = env.int("JOBS_RUN_TIME_LIMIT", default=240)  # seconds per run_jobs invocation

# --- PWA -------------------------------------------------------------------
PWA_VERSION = env("PWA_VERSION", default="1")
BRAND_COLOUR = env("BRAND_COLOUR", default="#4F46E5")  # platform colour; each organization sets its own

# --- Trial & plans -----------------------------------------------------------
TRIAL_DAYS = env.int("TRIAL_DAYS", default=14)
TRIAL_PLAN = env("TRIAL_PLAN", default="growth")  # a trial gets this plan's features

# --- Integrations (mock services are used while credentials are empty) ----
INTEGRATIONS = {
    "SMS_PROVIDER": env("SMS_PROVIDER", default="mock"),  # mock | africastalking
    "AT_USERNAME": env("AT_USERNAME", default=""),
    "AT_API_KEY": env("AT_API_KEY", default=""),
    "AT_SENDER_ID": env("AT_SENDER_ID", default=""),
}
# Encrypts stored credentials, TOTP secrets and confidential fields (Fernet). Defaults to SECRET_KEY.
# Changing it makes stored secrets unreadable.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")

# --- REST API --------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

# --- Monitoring ---------------------------------------------------------------
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=SENTRY_DSN, environment=env("SENTRY_ENVIRONMENT", default="production"),
                        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0), send_default_pii=False)
    except ImportError:  # pragma: no cover
        pass

# --- Logging ---------------------------------------------------------------
LOG_DIR = Path(env("LOG_DIR", default=str(BASE_DIR / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"verbose": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        "django_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "django.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "jobs_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "jobs.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "mail_admins": {"class": "django.utils.log.AdminEmailHandler", "level": "ERROR"},
    },
    "loggers": {
        "django": {"handlers": ["console", "django_file"], "level": "INFO"},
        "django.request": {"handlers": ["mail_admins", "django_file"], "level": "ERROR", "propagate": False},
        "apps.core.jobs": {"handlers": ["console", "jobs_file"], "level": "INFO", "propagate": False},
    },
}
