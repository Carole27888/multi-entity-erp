"""Staff app of one organization, served under /<org-slug>/ (or <org-slug>.APP_HOST with subdomain routing).

Every app with tenant pages adds one include here. The tenant-isolation test walks this URLConf.
"""

from django.urls import include, path

handler400 = "apps.core.views.error_400"
handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"

urlpatterns = [
    path("", include("apps.core.urls_tenant")),
    path("settings/", include("apps.orgsettings.urls")),
]
