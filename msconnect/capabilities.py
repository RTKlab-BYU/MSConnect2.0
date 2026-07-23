from importlib import import_module
from types import ModuleType

from django.conf import settings
from django.urls import include, path


def capability_urlpatterns():
    patterns = []
    for app_path in settings.MSCONNECT_CAPABILITY_APPS:
        slug = app_path.rsplit(".", 1)[-1].replace("_", "-")
        api_module = _optional_module(f"{app_path}.api_urls")
        if api_module is not None:
            patterns.append(path(f"api/capabilities/{slug}/", include(api_module)))

        web_module = _optional_module(f"{app_path}.urls")
        if web_module is not None:
            patterns.append(path(f"capabilities/{slug}/", include(web_module)))
    return patterns


def _optional_module(module_path: str) -> ModuleType | None:
    try:
        return import_module(module_path)
    except ModuleNotFoundError as exc:
        if exc.name == module_path:
            return None
        raise
