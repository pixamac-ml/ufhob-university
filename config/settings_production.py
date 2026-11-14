"""Production profile: DJANGO_SETTINGS_MODULE=config.settings_production."""

from urllib.parse import urlsplit

from .settings import *  # noqa: F403


def require_production(condition, message):
    if not condition:
        raise ImproperlyConfigured(message)


require_production(not DEBUG, "Production requires DEBUG=False.")
require_production(
    len(SECRET_KEY) >= 50 and len(set(SECRET_KEY)) >= 5
    and not SECRET_KEY.startswith("django-insecure-")
    and not SECRET_KEY.startswith("generate-"),
    "Production requires a strong, unique SECRET_KEY (at least 50 characters).",
)
require_production(
    len(CARD_SIGNING_KEY) >= 50 and len(set(CARD_SIGNING_KEY)) >= 5
    and not CARD_SIGNING_KEY.startswith("generate-")
    and CARD_SIGNING_KEY != SECRET_KEY,
    "Production requires a distinct CARD_SIGNING_KEY (at least 50 characters).",
)
require_production(
    DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
    and DATABASES["default"]["NAME"] == "ufhob_db",
    "UFHOB production must target the PostgreSQL database ufhob_db.",
)
require_production(
    DATABASES["default"].get("USER") == "ufhob_app",
    "UFHOB production requires the dedicated PostgreSQL role ufhob_app.",
)
require_production(
    ALLOWED_HOSTS and "*" not in ALLOWED_HOSTS
    and all(host not in {"localhost", "127.0.0.1", "[::1]"} for host in ALLOWED_HOSTS),
    "Production requires explicit public ALLOWED_HOSTS.",
)
public_url = urlsplit(BASE_URL)
require_production(
    public_url.scheme == "https" and public_url.hostname
    and not public_url.username and not public_url.password
    and not public_url.query and not public_url.fragment
    and public_url.path in {"", "/"},
    "Production requires BASE_URL=https://your-public-domain (without a path).",
)
require_production(
    any(public_url.hostname == host or (
        host.startswith(".") and (
            public_url.hostname == host[1:] or public_url.hostname.endswith(host)
        )
    ) for host in ALLOWED_HOSTS),
    "The BASE_URL hostname must be covered by ALLOWED_HOSTS.",
)
require_production(
    all(urlsplit(origin).scheme == "https" and urlsplit(origin).hostname
        for origin in CSRF_TRUSTED_ORIGINS),
    "Production CSRF_TRUSTED_ORIGINS must use HTTPS.",
)
require_production(
    SECURE_SSL_REDIRECT and SESSION_COOKIE_SECURE and CSRF_COOKIE_SECURE,
    "Production requires HTTPS redirects and secure session/CSRF cookies.",
)
require_production(
    not SYSTEM_SESSION_MANUAL_TEST_MODE and not ONLINE_CLASSROOM_TIME_BYPASS,
    "Disable session and classroom manual test modes in production.",
)

# Django recommends no persistent connections for ASGI; each worker uses Redis
# for the existing cross-worker realtime events, including session revocations.
DATABASES["default"]["CONN_MAX_AGE"] = 0
USE_X_FORWARDED_HOST = False

# Namespaces remain distinct even when other applications share Redis.
ENVIRONMENT = os.getenv("UFHOB_ENVIRONMENT", "production").strip()
require_production(ENVIRONMENT in {"production", "staging"}, "Invalid UFHOB_ENVIRONMENT.")
require_production(bool(REDIS_URL), "Production requires a private Redis URL.")
if ENABLE_WEBSOCKETS:
    CHANNEL_LAYERS["default"]["CONFIG"]["prefix"] = f"ufhob:{ENVIRONMENT}:channels"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("CACHE_REDIS_URL", REDIS_URL),
        "KEY_PREFIX": f"ufhob:{ENVIRONMENT}",
    },
}

require_production(
    EMAIL_BACKEND in {
        "django.core.mail.backends.smtp.EmailBackend",
        "core.mail_backends.StableSMTPEmailBackend",
    } and bool(EMAIL_HOST) and bool(EMAIL_HOST_USER) and bool(EMAIL_HOST_PASSWORD),
    "Production requires configured SMTP delivery for authentication emails.",
)
require_production(
    bool(EMAIL_USE_TLS) != bool(EMAIL_USE_SSL),
    "Production SMTP must use either STARTTLS or implicit TLS.",
)

# Do not impose HSTS on other subdomains or request preload at first deployment.
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)

LOGGING["handlers"] = {"console": {"class": "logging.StreamHandler"}}
LOGGING["root"] = {"handlers": ["console"], "level": "INFO"}
LOGGING["loggers"]["django"] = {
    "handlers": ["console"], "level": "INFO", "propagate": False,
}
