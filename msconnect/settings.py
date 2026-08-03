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

def env_csv(name: str, default: str = "") -> list[str]:
    value = os.environ.get(name, default).strip()
    if not value:
        value = default
    return [item.strip() for item in value.split(",") if item.strip()]


def discover_capability_apps() -> list[str]:
    if not env_bool("MSCONNECT_AUTO_DISCOVER_CAPABILITIES", True):
        return []
    capabilities_root = BASE_DIR / "capabilities"
    if not capabilities_root.exists():
        return []
    apps = []
    for child in sorted(capabilities_root.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if (child / "apps.py").exists() and (child / "__init__.py").exists():
            apps.append(f"capabilities.{child.name}")
    return apps


ALLOWED_HOSTS = env_csv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")

CSRF_TRUSTED_ORIGINS = env_csv(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000,http://localhost:8080,http://127.0.0.1:8080",
)

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
]

LOCAL_APPS = [
    "core",
    "ingest",
    "ui",
]

MSCONNECT_CAPABILITY_APPS = [*discover_capability_apps(), *env_csv("MSCONNECT_EXTRA_APPS")]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS + MSCONNECT_CAPABILITY_APPS

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

_db_engine = os.environ.get("DJANGO_DB_ENGINE", "django.db.backends.sqlite3")
if _db_engine == "django.db.backends.postgresql":
    DATABASES = {
        "default": {
            "ENGINE": _db_engine,
            "NAME": os.environ.get("DJANGO_DB_NAME", "msconnect"),
            "USER": os.environ.get("DJANGO_DB_USER", "msconnect"),
            "PASSWORD": os.environ.get("DJANGO_DB_PASSWORD", ""),
            "HOST": os.environ.get("DJANGO_DB_HOST", "localhost"),
            "PORT": os.environ.get("DJANGO_DB_PORT", "5432"),
            "OPTIONS": {"sslmode": os.environ.get("DJANGO_DB_SSLMODE", "prefer")},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": _db_engine,
            "NAME": os.environ.get("SQLITE_PATH", os.environ.get("DJANGO_DB_NAME", str(BASE_DIR / "db.sqlite3"))),
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
PROCESSOR_SHARED_STORAGE_ROOT = os.environ.get("PROCESSOR_SHARED_STORAGE_ROOT", RESULTS_ROOT)
MSCONNECT_ARCHIVE_ROOTS = env_csv("MSCONNECT_ARCHIVE_ROOTS", str(BASE_DIR / "archives"))
MSCONNECT_BACKUP_ROOTS = env_csv("MSCONNECT_BACKUP_ROOTS")
MSCONNECT_STORAGE_WARN_PERCENT = int(os.environ.get("MSCONNECT_STORAGE_WARN_PERCENT", "80"))
MSCONNECT_STORAGE_BLOCK_PERCENT = int(os.environ.get("MSCONNECT_STORAGE_BLOCK_PERCENT", "95"))
OBJECT_STORAGE_UPLOAD_BASE_URL = os.environ.get("OBJECT_STORAGE_UPLOAD_BASE_URL", "https://object-storage.invalid/msconnect")
OBJECT_STORAGE_SIGNED_URL_TTL_SECONDS = int(os.environ.get("OBJECT_STORAGE_SIGNED_URL_TTL_SECONDS", "3600"))
MSCONNECT_DEFAULT_FACILITY_SLUG = os.environ.get("MSCONNECT_DEFAULT_FACILITY_SLUG", "")

MSCONNECT_WATCHER_TOKEN = os.environ.get("MSCONNECT_WATCHER_TOKEN", "")
MSCONNECT_PROCESSOR_TOKEN = os.environ.get("MSCONNECT_PROCESSOR_TOKEN", "")
MSCONNECT_API_BASE_URL = os.environ.get("MSCONNECT_API_BASE_URL", "http://web:8000/api")
MSCONNECT_AGENT_NAME = os.environ.get("MSCONNECT_AGENT_NAME", "")
MSCONNECT_AGENT_TOKEN = os.environ.get("MSCONNECT_AGENT_TOKEN", "")
MSCONNECT_AGENT_HEARTBEAT_SECONDS = int(os.environ.get("MSCONNECT_AGENT_HEARTBEAT_SECONDS", "30"))
MSCONNECT_AGENT_HEALTH_DIR = os.environ.get("MSCONNECT_AGENT_HEALTH_DIR", str(BASE_DIR / "data" / "agent-health"))
MSCONNECT_PROCESSOR_ENGINE = os.environ.get("MSCONNECT_PROCESSOR_ENGINE", "processor")
MSCONNECT_PROCESSOR_ENGINE_VERSION = os.environ.get("MSCONNECT_PROCESSOR_ENGINE_VERSION", "")
MSCONNECT_PROCESSOR_ENGINE_PROFILE = os.environ.get("MSCONNECT_PROCESSOR_ENGINE_PROFILE", "")
MSCONNECT_API_DISCOVERY_BASE_URLS = env_csv("MSCONNECT_API_DISCOVERY_BASE_URLS")
MSCONNECT_API_DISCOVERY_HOSTS = env_csv("MSCONNECT_API_DISCOVERY_HOSTS", "web,server,msconnect-web,django,msconnect")
WATCHER_INTERVAL_SECONDS = int(os.environ.get("WATCHER_INTERVAL_SECONDS", "60"))
PROCESSOR_POLL_INTERVAL_SECONDS = int(os.environ.get("PROCESSOR_POLL_INTERVAL_SECONDS", "15"))
MSCONNECT_IMAGE = os.environ.get("MSCONNECT_IMAGE", "msconnect:local")
MSCONNECT_AUTO_QUEUE_SPECTRA_CONVERSION = env_bool("MSCONNECT_AUTO_QUEUE_SPECTRA_CONVERSION", False)
MSCONNECT_MSCONVERT_EXECUTABLE = os.environ.get("MSCONNECT_MSCONVERT_EXECUTABLE", "msconvert")
MSCONNECT_MSCONVERT_OUTPUT_FORMAT = os.environ.get("MSCONNECT_MSCONVERT_OUTPUT_FORMAT", "mzML")
MSCONNECT_PWIZ_VERSION = os.environ.get("MSCONNECT_PWIZ_VERSION", "site-configured")
MSCONNECT_PRTC_SKYLINE_PIPELINE_ID = os.environ.get("MSCONNECT_PRTC_SKYLINE_PIPELINE_ID", "")
MSCONNECT_FINDINGS_WORKSPACE_ROOT = os.environ.get("MSCONNECT_FINDINGS_WORKSPACE_ROOT", str(BASE_DIR / "findings_workspaces"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_REDIRECT_URL = "/app/dashboard"
LOGOUT_REDIRECT_URL = "/accounts/login/"

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
