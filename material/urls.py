from django.urls import path

from .views import (
    DashboardStatsView,
    MaterialTrackDetail,
    MaterialTrackList,
    SendOTPView,
    VerifyOTPAndSubmitView,
)

urlpatterns = [
    path("material-tracks/", MaterialTrackList.as_view(), name="material-track-list"),
    path("material-tracks/<int:pk>/", MaterialTrackDetail.as_view(), name="material-track-detail"),
    path("material-tracks/send-otp/", SendOTPView.as_view(), name="send-otp"),
    path("material-tracks/verify-and-submit/", VerifyOTPAndSubmitView.as_view(), name="verify-and-submit"),
    path("dashboard/stats/", DashboardStatsView.as_view(), name="dashboard-stats"),
]
