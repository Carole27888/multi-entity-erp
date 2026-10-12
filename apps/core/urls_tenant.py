"""Core URLs inside an organization."""

from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("checklist/<slug:key>/", views.checklist_tick, name="checklist_tick"),
    path("files/<int:pk>/", views.attachment_download, name="attachment"),
]
