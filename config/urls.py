"""Platform URLs: sign-in, sign-up and onboarding, organization chooser, platform admin, PWA files, health.

Organizations' staff pages use config.urls_tenant and public sites config.urls_public; TenantMiddleware picks.
"""

from django.contrib import admin
from django.urls import include, path

handler400 = "apps.core.views.error_400"
handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"

urlpatterns = [
    path("", include("apps.core.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.tenancy.urls")),
    path("", include("apps.onboarding.urls")),
    path("platform/", include("apps.platformadmin.urls")),
    path("django-admin/", admin.site.urls),
]
