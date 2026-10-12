from django.urls import path

from . import views

app_name = "orgsettings"

urlpatterns = [
    path("", views.index, name="index"),
    path("profile/", views.profile, name="profile"),
    path("modules/", views.modules_view, name="modules"),
    path("team/", views.members, name="members"),
    path("team/<int:pk>/", views.member_edit, name="member_edit"),
    path("invitations/<int:pk>/revoke/", views.invitation_revoke, name="invitation_revoke"),
    path("invitations/<int:pk>/resend/", views.invitation_resend, name="invitation_resend"),
    path("roles/", views.roles, name="roles"),
    path("roles/new/", views.role_new, name="role_new"),
    path("roles/<int:pk>/", views.role_view, name="role_view"),
    path("roles/<int:pk>/edit/", views.role_edit, name="role_edit"),
    path("roles/<int:pk>/delete/", views.role_delete, name="role_delete"),
    path("departments/", views.departments, name="departments"),
    path("departments/<int:pk>/delete/", views.department_delete, name="department_delete"),
]
