"""
Django settings for config project.
Configuration DEV stable ESFE
"""

import os
import importlib.util
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# ==================================================
# BASE
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent
# Ubuntu receives its secrets through systemd EnvironmentFile. Never fill
# missing server variables from a developer's accidentally copied .env.
_environment_file = os.getenv("UFHOB_ENV_FILE", "").strip()
if _environment_file:
    load_dotenv(Path(_environment_file).expanduser())
elif os.getenv("DJANGO_SETTINGS_MODULE") not in {
    "config.settings_production", "config.settings_staging",
}:
    load_dotenv(BASE_DIR / ".env")

# URL absolue du site, utilisee par SEO, emails et securite CSRF.
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]

# ==================================================
# SECURITY
# ==================================================

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY must be set in .env — generate one with: python -c \"import secrets; print(secrets.token_urlsafe(50))\"")
DEBUG = env_bool("DEBUG", False)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", BASE_URL)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "127.0.0.1,localhost")
ENABLE_BROWSER_RELOAD = DEBUG and env_bool("ENABLE_BROWSER_RELOAD", True)
ENABLE_WEBSOCKETS = env_bool("ENABLE_WEBSOCKETS", True)
REDIS_URL = os.getenv("REDIS_URL", "").strip()

# ==================================================
# APPLICATIONS
# ==================================================

INSTALLED_APPS = [

    # 🔥 django-components
    "django_components",
    # Composants de la nouvelle vitrine publique (migration progressive).
    "config.cotton.CottonCompatConfig",
    "daphne",
    "channels",
    "axes",
    # Django core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sitemaps",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # UI / Core
    "ui.apps.UiConfig",
    "core.apps.CoreConfig",
    "notifier.apps.NotifierConfig",
    "notification_center.apps.NotificationCenterConfig",
    "communications.apps.CommunicationsConfig",
    "marketing.apps.MarketingConfig",

    # ✅ CKEditor 5 (UNIQUEMENT celui-ci)
    "django_ckeditor_5",
    'superadmin',
    # Métier
    "admissions.apps.AdmissionsConfig",
    "inscriptions.apps.InscriptionsConfig",
    "payments.apps.PaymentsConfig",
    "academic_cycle.apps.AcademicCycleConfig",
    "students",
    "formations",
    "branches",
    "academics",
    "shop.apps.ShopConfig",
    # Contenu
    "blog.apps.BlogConfig",
    "news",
    "community.apps.CommunityConfig",
    "accounts.apps.AccountsConfig",
    "portal.apps.PortalConfig",
    "secretary",
    "memoires.apps.MemoiresConfig",
    "coupons.apps.CouponsConfig",
]

if ENABLE_BROWSER_RELOAD and importlib.util.find_spec("django_browser_reload"):
    INSTALLED_APPS.append("django_browser_reload")

# ==================================================
# DJANGO-COMPONENTS CONFIG
# ==================================================

COMPONENTS = {
    "template_cache_size": 128,
}

# ==================================================
# MIDDLEWARE
# ==================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "accounts.middleware.PresenceMiddleware",
    "accounts.middleware.AccessContextMiddleware",
    "accounts.middleware.SystemSessionSecurityMiddleware",
    "accounts.middleware.MandatoryPasswordChangeMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

if ENABLE_BROWSER_RELOAD and importlib.util.find_spec("django_browser_reload"):
    MIDDLEWARE.append("django_browser_reload.middleware.BrowserReloadMiddleware")

MIDDLEWARE.append("axes.middleware.AxesMiddleware")

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# ==================================================
# DJANGO-AXES (protection brute-force connexion)
# ==================================================
# La configuration par defaut d'Axes est basee uniquement sur l'adresse IP.
# Dans une annexe, plusieurs personnes partagent souvent la meme connexion :
# les erreurs d'un compte ne doivent donc jamais bloquer les autres comptes.
# Le verrouillage est temporaire et cible le couple compte + adresse IP.
AXES_FAILURE_LIMIT = 5
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_RESET_ON_SUCCESS = True
AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False
AXES_COOLOFF_MESSAGE = (
    "Trop de tentatives pour ce compte. Reessayez dans 15 minutes ou contactez "
    "l'informaticien de votre annexe."
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "ignore_client_cancelled": {
            "()": "core.logging.IgnoreClientCancelledError",
        },
    },
    "loggers": {
        "django.request": {
            "filters": ["ignore_client_cancelled"],
        },
        "django.server": {
            "filters": ["ignore_client_cancelled"],
        },
        "django.core.handlers.asgi": {
            "filters": ["ignore_client_cancelled"],
        },
        "asgiref": {
            "filters": ["ignore_client_cancelled"],
        },
        "uvicorn.error": {
            "filters": ["ignore_client_cancelled"],
        },
        "uvicorn.access": {
            "filters": ["ignore_client_cancelled"],
        },
        "daphne.server": {
            "filters": ["ignore_client_cancelled"],
        },
        "daphne.http_protocol": {
            "filters": ["ignore_client_cancelled"],
        },
        "channels.server": {
            "filters": ["ignore_client_cancelled"],
        },
    },
}

# ==================================================
# URLS / WSGI / ASGI
# ==================================================

ROOT_URLCONF = "config.urls"

# WSGI (HTTP classique)
WSGI_APPLICATION = "config.wsgi.application"

# ASGI (WebSockets / temps réel)
ASGI_APPLICATION = "config.asgi.application"

# ==================================================
# TEMPLATES
# ==================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates", BASE_DIR / "ui" / "templates"],
        "APP_DIRS": False,
        "OPTIONS": {
            "loaders": [
                (
                    "django.template.loaders.cached.Loader",
                    [
                        "django_cotton.cotton_loader.Loader",
                        "django.template.loaders.filesystem.Loader",
                        "django.template.loaders.app_directories.Loader",
                    ],
                )
            ],
            "builtins": ["django_cotton.templatetags.cotton"],
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.seo_defaults",
                "core.context_processors.public_legal_links",
                "core.context_processors.branding",
                "notification_center.context_processors.notification_widget",
            ],
        },
    },
]

# ==================================================
# DATABASE
# ==================================================

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=int(os.getenv("DB_CONN_MAX_AGE", "60")),
            ssl_require=env_bool("DB_SSL_REQUIRE", not DEBUG),
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "ufhob_db"),
            "USER": os.getenv("DB_USER", "ufhob_app"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        }
    }


# ==================================================
# DJANGO CHANNELS (WebSockets)
# ==================================================

HAS_CHANNELS_REDIS = importlib.util.find_spec("channels_redis") is not None
FEATURE_SMS_NOTIFICATIONS = env_bool("FEATURE_SMS_NOTIFICATIONS", False)

if ENABLE_WEBSOCKETS and REDIS_URL and HAS_CHANNELS_REDIS:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [REDIS_URL],
                "prefix": os.getenv("CHANNEL_REDIS_PREFIX", "ufhob:channels"),
            },
        }
    }
else:
    if ENABLE_WEBSOCKETS and not REDIS_URL and not DEBUG:
        raise ImproperlyConfigured(
            "REDIS_URL is required when WebSockets are enabled in production; "
            "an in-memory channel layer cannot propagate session revocations across workers."
        )
    if ENABLE_WEBSOCKETS and REDIS_URL and not HAS_CHANNELS_REDIS and not DEBUG:
        raise ImproperlyConfigured(
            "REDIS_URL is configured but channels_redis is not installed. "
            "Install channels_redis or unset REDIS_URL."
        )
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

# ==================================================
# PASSWORD VALIDATION
# ==================================================

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ==================================================
# INTERNATIONALIZATION
# ==================================================

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ==================================================
# STATIC FILES
# ==================================================
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_MAX_AGE = int(os.getenv("WHITENOISE_MAX_AGE", "31536000" if not DEBUG else "0"))

# ==================================================
# MEDIA FILES
# ==================================================

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ==================================================
# STOCKAGE PRIVÉ — APP MEMOIRES
# ==================================================
# Bucket S3 privé pour les mémoires (sources PDF + pages rendues). Si les
# variables S3_* ne sont pas renseignées, memoires.storage retombe sur un
# répertoire local non exposé par config.urls (dev/test sans fournisseur S3).

MEMOIRES_S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "").strip()
MEMOIRES_S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
MEMOIRES_S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "").strip()
MEMOIRES_S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "").strip()
MEMOIRES_S3_CONFIGURED = bool(
    MEMOIRES_S3_BUCKET and MEMOIRES_S3_ACCESS_KEY and MEMOIRES_S3_SECRET_KEY
)
MEMOIRES_PRIVATE_ROOT = BASE_DIR / "private_media" / "memoires"

MEMOIRE_UPLOAD_MAX_MB = int(os.getenv("MEMOIRE_UPLOAD_MAX_MB", "50"))
MEMOIRE_RENDER_DPI = int(os.getenv("MEMOIRE_RENDER_DPI", "130"))

# Ressources pédagogiques : Backblaze B2 est traité comme un provider S3 privé.
# Sans ces variables, le développement utilise un répertoire hors MEDIA_ROOT.
COURSE_MEDIA_S3_ENDPOINT_URL = os.getenv("B2_ENDPOINT_URL", os.getenv("COURSE_MEDIA_S3_ENDPOINT_URL", "")).strip()
COURSE_MEDIA_S3_BUCKET = os.getenv("B2_BUCKET_NAME", os.getenv("COURSE_MEDIA_S3_BUCKET", "")).strip()
COURSE_MEDIA_S3_ACCESS_KEY = os.getenv("B2_ACCESS_KEY_ID", os.getenv("COURSE_MEDIA_S3_ACCESS_KEY", "")).strip()
COURSE_MEDIA_S3_SECRET_KEY = os.getenv("B2_SECRET_ACCESS_KEY", os.getenv("COURSE_MEDIA_S3_SECRET_KEY", "")).strip()
COURSE_MEDIA_S3_REGION = os.getenv("B2_REGION", os.getenv("COURSE_MEDIA_S3_REGION", "us-east-1")).strip()
COURSE_MEDIA_S3_CONFIGURED = bool(COURSE_MEDIA_S3_BUCKET and COURSE_MEDIA_S3_ACCESS_KEY and COURSE_MEDIA_S3_SECRET_KEY)
COURSE_MEDIA_PRIVATE_ROOT = BASE_DIR / "private_media" / "courses"
COURSE_MEDIA_SIGNED_URL_SECONDS = int(os.getenv("COURSE_MEDIA_SIGNED_URL_SECONDS", "300"))
COURSE_MEDIA_UPLOAD_URL_SECONDS = int(os.getenv("COURSE_MEDIA_UPLOAD_URL_SECONDS", "900"))
COURSE_MEDIA_MAX_UPLOAD_BYTES = int(os.getenv("COURSE_MEDIA_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024 * 1024)))

# Enregistrements de classes virtuelles.  Ce bucket est distinct des ressources
# de cours afin de permettre une politique de rétention dédiée.  La
# configuration reste optionnelle : BBB continue à fonctionner sans B2.
B2_RECORDINGS_BUCKET = os.getenv("B2_RECORDINGS_BUCKET", "").strip()
B2_RECORDINGS_ENDPOINT = os.getenv("B2_RECORDINGS_ENDPOINT", "").strip()
B2_RECORDINGS_REGION = os.getenv("B2_RECORDINGS_REGION", "").strip()
B2_RECORDINGS_ACCESS_KEY_ID = os.getenv("B2_RECORDINGS_ACCESS_KEY_ID", "").strip()
B2_RECORDINGS_SECRET_ACCESS_KEY = os.getenv("B2_RECORDINGS_SECRET_ACCESS_KEY", "").strip()
B2_RECORDINGS_CONFIGURED = bool(
    B2_RECORDINGS_BUCKET
    and B2_RECORDINGS_ENDPOINT
    and B2_RECORDINGS_REGION
    and B2_RECORDINGS_ACCESS_KEY_ID
    and B2_RECORDINGS_SECRET_ACCESS_KEY
)
B2_RECORDINGS_SIGNED_URL_SECONDS = int(os.getenv("B2_RECORDINGS_SIGNED_URL_SECONDS", "300"))

# ==================================================
# DEFAULT PK
# ==================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ==================================================
# URLS ABSOLUES (EMAILS / LIENS EXTERNES)
# ==================================================

EMAIL_LOGO_PATH = os.getenv("EMAIL_LOGO_PATH", "static/images/students/logo-ubhob.png")
PUBLIC_CAMPAIGN_PHONE = os.getenv("PUBLIC_CAMPAIGN_PHONE", "+223 76 88 24 79")
PUBLIC_WHATSAPP_URL = os.getenv("PUBLIC_WHATSAPP_URL", "https://wa.me/22376882479")
# Coordonnées publiques valides (campagne 2026-2027) : source unique du site.
PUBLIC_WEBSITE_URL = os.getenv("PUBLIC_WEBSITE_URL", "https://www.ufhob-mali.ml").rstrip("/")
PUBLIC_SOCIAL_HANDLE = os.getenv("PUBLIC_SOCIAL_HANDLE", "@ufhob_officiel")
# Aucune adresse e-mail publique tant qu'une adresse sur le domaine actuel n'est pas validée.
PUBLIC_CONTACT_EMAIL = os.getenv("PUBLIC_CONTACT_EMAIL", "")
SCHOOL_CONTACT_PHONES = {code: os.getenv(f"{code}_CONTACT_PHONE", "") for code in ("ESGA", "FATEC", "ESMED")}
# Historical fees remain stored; publication requires a separate institutional decision.
PUBLIC_FEES_ENABLED = False
# Exception validée par la direction : frais publics pour ces écoles uniquement.
PUBLIC_FEES_SCHOOL_CODES = ("ESMED", "FATEC", "ESGA")

if BASE_URL and BASE_URL not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(BASE_URL)

# ==================================================
# EMAIL (DEV)
# ==================================================

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "core.mail_backends.StableSMTPEmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").strip().lower() in {"1", "true", "yes", "on"}
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").strip().lower() in {"1", "true", "yes", "on"}
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "noreply@localhost")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "UFHOB")
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "20"))
EMAIL_LOCAL_HOSTNAME = os.getenv("EMAIL_LOCAL_HOSTNAME", "localhost")
COMMUNICATION_EMAIL_PROVIDER = os.getenv("COMMUNICATION_EMAIL_PROVIDER", "brevo")
COMMUNICATION_EMAIL_PROVIDER_MODE = os.getenv("COMMUNICATION_EMAIL_PROVIDER_MODE", "smtp")
NOTIFIER_EMAIL_PROVIDER = os.getenv("NOTIFIER_EMAIL_PROVIDER", "brevo")
NOTIFIER_EMAIL_PROVIDER_MODE = os.getenv("NOTIFIER_EMAIL_PROVIDER_MODE", "smtp")

# ==================================================
# AUTH REDIRECTS
# ==================================================

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "accounts_portal:portal_dashboard"
LOGOUT_REDIRECT_URL = "core:home"

# Migration progressive du système d'accès. Ces flags restent inactifs tant que
# les décisions V2 n'ont pas été comparées et validées en mode shadow.
AUTH_ACCESS_CONTEXT_V2_ENABLED = env_bool("AUTH_ACCESS_CONTEXT_V2_ENABLED", False)
AUTH_POLICY_V2_ENABLED = env_bool("AUTH_POLICY_V2_ENABLED", False)
AUTH_POLICY_V2_SHADOW_ENABLED = env_bool("AUTH_POLICY_V2_SHADOW_ENABLED", False)
AUTH_PORTAL_ROUTING_V2_ENABLED = env_bool("AUTH_PORTAL_ROUTING_V2_ENABLED", False)

# Sessions institutionnelles. Les valeurs sont en secondes et restent
# centralisees afin qu'aucun dashboard ne porte son propre nombre magique.
SYSTEM_SESSION_IDLE_TIMEOUTS = {
    "student": 30 * 60,
    "teacher": 30 * 60,
    "secretary": 15 * 60,
    "admissions": 15 * 60,
    "academic_supervisor": 15 * 60,
    "director_of_studies": 15 * 60,
    "annex_manager": 10 * 60,
    "branch_manager": 10 * 60,
    "it_support": 10 * 60,
    "marketing_manager": 15 * 60,
    "executive_director": 10 * 60,
    "deputy_executive_director": 10 * 60,
    "super_admin": 10 * 60,
    "payment_agent": 10 * 60,
    "finance_manager": 10 * 60,
}
SYSTEM_SESSION_DEFAULT_IDLE_TIMEOUT = int(os.getenv("SYSTEM_SESSION_DEFAULT_IDLE_TIMEOUT", "900"))
SYSTEM_SESSION_WARNING_SECONDS = int(os.getenv("SYSTEM_SESSION_WARNING_SECONDS", "120"))
SYSTEM_SESSION_ABSOLUTE_TIMEOUT = int(os.getenv("SYSTEM_SESSION_ABSOLUTE_TIMEOUT", str(12 * 60 * 60)))
SYSTEM_SESSION_ACTIVITY_THROTTLE_SECONDS = int(os.getenv("SYSTEM_SESSION_ACTIVITY_THROTTLE_SECONDS", "30"))
SYSTEM_SESSION_MANUAL_TEST_MODE = env_bool("SYSTEM_SESSION_MANUAL_TEST_MODE", False)
if SYSTEM_SESSION_MANUAL_TEST_MODE:
    SYSTEM_SESSION_IDLE_TIMEOUTS = {key: 3 * 60 for key in SYSTEM_SESSION_IDLE_TIMEOUTS}
    SYSTEM_SESSION_DEFAULT_IDLE_TIMEOUT = 3 * 60
    SYSTEM_SESSION_WARNING_SECONDS = 60

# ==================================================
# CKEDITOR 5 CONFIG
# ==================================================

CKEDITOR_5_CONFIGS = {
    "default": {
        "toolbar": [
            "heading", "|",
            "bold", "italic", "link",
            "bulletedList", "numberedList",
            "blockQuote", "|",
            "insertImage", "insertTable", "|",
            "undo", "redo"
        ],
        "height": 400,
        "width": "100%",
    }
}

# ==================================================
# CUSTOM
# ==================================================

# The Google Workspace adapter is intentionally disabled until professional
# credentials and domain policy are configured outside the repository.
GOOGLE_WORKSPACE_ENABLED = env_bool("GOOGLE_WORKSPACE_ENABLED", False)

# Classes virtuelles. Le secret BBB reste exclusivement cote serveur.
ONLINE_CLASSROOM_PROVIDER = os.getenv("ONLINE_CLASSROOM_PROVIDER", "bigbluebutton").strip().lower()
BBB_API_URL = os.getenv("BBB_API_URL", "").strip()
BBB_SECRET = os.getenv("BBB_SECRET", "").strip()
BBB_API_TIMEOUT = int(os.getenv("BBB_API_TIMEOUT", "10"))
BBB_MEETING_ID_PREFIX = os.getenv("BBB_MEETING_ID_PREFIX", "ufhob").strip()
# Local-only switch for a short acceptance-test window.  The service also
# requires DEBUG, so an accidentally enabled environment variable cannot
# bypass the production schedule.
ONLINE_CLASSROOM_TIME_BYPASS = env_bool("ONLINE_CLASSROOM_TIME_BYPASS", False)
ONLINE_CLASSROOM_END_GRACE_MINUTES = int(os.getenv("ONLINE_CLASSROOM_END_GRACE_MINUTES", "10"))
ONLINE_CLASSROOM_RECORDING_ENABLED = env_bool("ONLINE_CLASSROOM_RECORDING_ENABLED", False)
COURSE_CHECKIN_GRACE_MINUTES = int(os.getenv("COURSE_CHECKIN_GRACE_MINUTES", "10"))
COURSE_END_WARNING_MINUTES = int(os.getenv("COURSE_END_WARNING_MINUTES", "15"))

STUDENT_LOGIN_URL = os.getenv("STUDENT_LOGIN_URL", f"{BASE_URL}/student/login/")
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")

# Clé dédiée à la signature HMAC des cartes étudiantes.
# Distincte de SECRET_KEY pour rotation indépendante.
# Générer : python -c "import secrets; print(secrets.token_urlsafe(50))"
CARD_SIGNING_KEY = os.getenv("CARD_SIGNING_KEY", "")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = env_bool("USE_X_FORWARDED_HOST", not DEBUG)
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", not DEBUG)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = os.getenv("SECURE_REFERRER_POLICY", "strict-origin-when-cross-origin")
# Le dashboard integre certains contenus (PDF, previews) via iframe.
# SAMEORIGIN garde la protection clickjacking tout en autorisant l'integration interne.
X_FRAME_OPTIONS = os.getenv("X_FRAME_OPTIONS", "SAMEORIGIN")
# SAMEORIGIN est intentionnel pour les aperçus internes de documents.
SILENCED_SYSTEM_CHECKS = ["security.W019"]

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 28800  # 8 heures
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

if DEBUG:
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False


# Optional public campaign pixel. Empty means no Meta code is rendered.
META_PIXEL_ID = os.getenv("META_PIXEL_ID", "").strip()
