from django.urls import path

from . import views

app_name = "onboarding"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("verify-email/", views.verify_pending, name="verify_pending"),
    path("verify-email/<str:token>/", views.verify_email, name="verify_email"),
    path("verify-phone/", views.verify_phone, name="verify_phone"),
    path("onboarding/", views.start, name="start"),
    path("onboarding/<int:pk>/cancel/", views.cancel, name="cancel"),
    path("onboarding/<int:pk>/<slug:step>/", views.step, name="step"),
]
