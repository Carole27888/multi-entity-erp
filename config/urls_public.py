"""An organization's public website (and, from phase 5, its customer portal)."""

from django.urls import include, path

handler400 = "apps.core.views.error_400"
handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"

urlpatterns = [
    path("", include("apps.website.urls")),
]
