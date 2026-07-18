from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, HttpResponse
from django.urls import include, path, re_path
from django.views.generic import RedirectView


def app_shell(_request, _path=""):
    index_path = settings.BASE_DIR / "ui" / "static" / "app" / "index.html"
    if not index_path.exists():
        return HttpResponse(
            "The React app has not been built yet. Run `npm install && npm run build` from `frontend/`.",
            status=503,
            content_type="text/plain",
        )
    return FileResponse(index_path.open("rb"), content_type="text/html")


urlpatterns = [
    path("", RedirectView.as_view(url="/ui/projects", permanent=False)),
    path("app/", app_shell),
    re_path(r"^app/(?P<_path>.*)$", app_shell),
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
    path("api-auth/", include("rest_framework.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("ui/", include("ui.urls")),
]
