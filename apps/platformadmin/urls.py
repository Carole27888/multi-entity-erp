from django.urls import path

from . import views

app_name = "platformadmin"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("orgs/<int:pk>/", views.org_detail, name="org_detail"),
    path("orgs/<int:pk>/suspend/", views.org_suspend, name="org_suspend"),
    path("orgs/<int:pk>/restore/", views.org_restore, name="org_restore"),
    path("orgs/<int:pk>/impersonate/<int:membership_pk>/", views.impersonate, name="impersonate"),
    path("impersonation/stop/", views.stop_impersonating, name="stop_impersonating"),
]
