"""
Configuration Django du projet Kènèya Sô.

Application de gestion hospitalière intelligente — contexte Mali.
Référence : docs/Kenya_So_Cahier_des_charges_enrichi.docx

La configuration est pilotée par variables d'environnement (fichier .env) via
django-environ, pour séparer le code des secrets et faciliter le déploiement
(CDC 7.5 — maintenabilité).
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------- #
# Environnement
# --------------------------------------------------------------------------- #
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_SECURE_SSL_REDIRECT=(bool, False),
    DJANGO_SESSION_COOKIE_SECURE=(bool, False),
    DJANGO_CSRF_COOKIE_SECURE=(bool, False),
    DJANGO_CORS_ALLOWED_ORIGINS=(list, []),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-key-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# --------------------------------------------------------------------------- #
# Applications
# --------------------------------------------------------------------------- #
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
]

# Une application Django par module métier (CDC 7.5 — architecture modulaire).
LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.patients",
    # --- Modules métier ajoutés au fil du planning (CDC 11.2) ---
    "apps.consultations",   # phase 3
    "apps.pharmacie",       # phase 3
    "apps.hospitalisation",  # phase 4
    "apps.bloc_operatoire",  # phases 5-6 (module détaillé CDC section 5)
    "apps.laboratoire",     # phase 7 (analyses biologiques + imagerie)
    "apps.facturation",     # phase 6
    "apps.assurances",      # phase 6
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# --------------------------------------------------------------------------- #
# Middleware
# --------------------------------------------------------------------------- #
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",  # bascule de langue (CDC 4.11)
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------- #
# Base de données (CDC 8 — PostgreSQL cible ; repli SQLite en développement)
# --------------------------------------------------------------------------- #
DATABASES = {
    "default": env.db("DATABASE_URL", default="sqlite:///" + str(BASE_DIR / "db.sqlite3")),
}

# --------------------------------------------------------------------------- #
# Authentification et modèle utilisateur (CDC 4.10, 7.1 — RBAC)
# --------------------------------------------------------------------------- #
AUTH_USER_MODEL = "accounts.Utilisateur"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

# --------------------------------------------------------------------------- #
# Internationalisation — 6 langues (CDC 4.11)
# --------------------------------------------------------------------------- #
from django.utils.translation import gettext_lazy as _  # noqa: E402

LANGUAGE_CODE = env("DJANGO_LANGUAGE_CODE", default="fr")
TIME_ZONE = env("DJANGO_TIME_ZONE", default="Africa/Bamako")
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("fr", _("Français")),
    ("en", _("Anglais")),
    ("ar", _("Arabe")),
    ("bm", _("Bambara")),
    ("ff", _("Peulh (fulfulde)")),
    ("snk", _("Soninké")),
]

LOCALE_PATHS = [BASE_DIR / "locale"]

# Le bambara, le peulh et le soninké ne figurent pas dans la table de langues
# de Django : on les y injecte pour éviter les KeyError de get_language_info
# (utilisé par les templates i18n et l'admin).  L'arabe (RTL) est déjà connu.
from django.conf.locale import LANG_INFO  # noqa: E402

LANG_INFO.setdefault("bm", {"bidi": False, "code": "bm", "name": "Bambara", "name_local": "Bamanankan"})
LANG_INFO.setdefault("ff", {"bidi": False, "code": "ff", "name": "Fulah", "name_local": "Fulfulde"})
LANG_INFO.setdefault("snk", {"bidi": False, "code": "snk", "name": "Soninke", "name_local": "Sooninkanxanne"})

# --------------------------------------------------------------------------- #
# Fichiers statiques et médias
# --------------------------------------------------------------------------- #
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        # Manifeste (hachage + compression) uniquement hors développement :
        # évite d'exiger un collectstatic préalable en local et pour les tests.
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------- #
# Django REST Framework + documentation d'API (CDC 8 — API REST / DRF)
# --------------------------------------------------------------------------- #
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "API Kènèya Sô",
    "DESCRIPTION": "API de la plateforme de gestion hospitalière Kènèya Sô.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Le champ « role » existe sur l'utilisateur et sur un membre d'équipe de bloc :
    # on nomme explicitement les énumérations pour éviter une collision de composant.
    "ENUM_NAME_OVERRIDES": {
        "RoleUtilisateurEnum": "apps.accounts.models.Utilisateur.Role",
        "RoleMembreEquipeEnum": "apps.bloc_operatoire.models.MembreEquipe.Role",
    },
}

# --------------------------------------------------------------------------- #
# Sécurité (CDC 7.1) — durci via variables d'environnement en production
# --------------------------------------------------------------------------- #
SECURE_SSL_REDIRECT = env("DJANGO_SECURE_SSL_REDIRECT")
SESSION_COOKIE_SECURE = env("DJANGO_SESSION_COOKIE_SECURE")
CSRF_COOKIE_SECURE = env("DJANGO_CSRF_COOKIE_SECURE")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

CSRF_TRUSTED_ORIGINS = [
    f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")
]

CORS_ALLOWED_ORIGINS = env("DJANGO_CORS_ALLOWED_ORIGINS")

# --------------------------------------------------------------------------- #
# Journalisation (CDC 7.1 — audit trail applicatif complété par apps.core)
# --------------------------------------------------------------------------- #
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "keneya": {"handlers": ["console"], "level": "DEBUG" if DEBUG else "INFO", "propagate": False},
    },
}
