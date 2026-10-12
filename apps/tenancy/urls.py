from django.urls import path

from . import views

app_name = "tenancy"

urlpatterns = [
    path("orgs/", views.choose_organization, name="choose"),
    path("invite/<str:token>/", views.accept_invite, name="accept_invite"),
]
