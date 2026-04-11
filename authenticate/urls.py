from django.urls import path

from .views import (
    EngineerDetailView,
    EngineerListCreateView,
    EngineersListView,
    LoginView,
    ManagerDetailView,
    ManagerListCreateView,
    MeView,
    RefreshView,
    RegisterView,
    SubAdminDetailView,
    SubAdminListCreateView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="token-refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("sub-admins/", SubAdminListCreateView.as_view(), name="sub-admin-list"),
    path("sub-admins/<int:pk>/", SubAdminDetailView.as_view(), name="sub-admin-detail"),
    # Manager management
    path("managers/", ManagerListCreateView.as_view(), name="manager-list"),
    path("managers/<int:pk>/", ManagerDetailView.as_view(), name="manager-detail"),
    # Engineer management
    path("engineers/", EngineerListCreateView.as_view(), name="engineer-list"),
    path("engineers/<int:pk>/", EngineerDetailView.as_view(), name="engineer-detail"),
]
