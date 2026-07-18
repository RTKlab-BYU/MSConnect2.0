import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "core",
    "ingest",
    "ui",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "msconnect.urls"

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
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "msconnect.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("SQLITE_PATH", str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {
            "timeout": int(os.environ.get("SQLITE_TIMEOUT_SECONDS", "20")),
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "America/Denver")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = os.environ.get("STATIC_ROOT", str(BASE_DIR / "staticfiles"))

MEDIA_URL = "media/"
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", str(BASE_DIR / "media"))

RAW_FILE_STORAGE_ROOT = os.environ.get("RAW_FILE_STORAGE_ROOT", str(BASE_DIR / "raw-storage"))
INCOMING_RAW_ROOT = os.environ.get("INCOMING_RAW_ROOT", str(BASE_DIR / "incoming"))
RESULTS_ROOT = os.environ.get("RESULTS_ROOT", "/data/results")
OBJECT_STORAGE_UPLOAD_BASE_URL = os.environ.get("OBJECT_STORAGE_UPLOAD_BASE_URL", "https://object-storage.invalid/msconnect")
OBJECT_STORAGE_SIGNED_URL_TTL_SECONDS = int(os.environ.get("OBJECT_STORAGE_SIGNED_URL_TTL_SECONDS", "3600"))

MSCONNECT_WATCHER_TOKEN = os.environ.get("MSCONNECT_WATCHER_TOKEN", "")
MSCONNECT_PROCESSOR_TOKEN = os.environ.get("MSCONNECT_PROCESSOR_TOKEN", "")
MSCONNECT_API_BASE_URL = os.environ.get("MSCONNECT_API_BASE_URL", "http://web:8000/api")
MSCONNECT_AGENT_NAME = os.environ.get("MSCONNECT_AGENT_NAME", "")
MSCONNECT_AGENT_TOKEN = os.environ.get("MSCONNECT_AGENT_TOKEN", "")
MSCONNECT_AGENT_HEARTBEAT_SECONDS = int(os.environ.get("MSCONNECT_AGENT_HEARTBEAT_SECONDS", "30"))
WATCHER_INTERVAL_SECONDS = int(os.environ.get("WATCHER_INTERVAL_SECONDS", "60"))
PROCESSOR_POLL_INTERVAL_SECONDS = int(os.environ.get("PROCESSOR_POLL_INTERVAL_SECONDS", "15"))
MSCONNECT_IMAGE = os.environ.get("MSCONNECT_IMAGE", "msconnect:local")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "core.agent_auth.AgentTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
