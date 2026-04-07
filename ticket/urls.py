from django.urls import path

from .views import (
    AvailableTransitionsView,
    BreachedTicketsView,
    MyQueueView,
    SendOTPView,
    TicketDetailView,
    TicketListCreateView,
    TicketTimelineView,
    TicketTransitionView,
    VerifyOTPAndSubmitView,
)
from .analytics import (
    DashboardOverviewView,
    DelayHeatmapView,
    EngineerPerformanceView,
    ManagerApprovalView,
    RegionComparisonView,
    SLABreachesView,
    TicketAgingView,
)

urlpatterns = [
    # Dashboard & Analytics
    path("dashboard/overview/", DashboardOverviewView.as_view()),
    path("dashboard/sla-breaches/", SLABreachesView.as_view()),
    path("dashboard/delay-heatmap/", DelayHeatmapView.as_view()),
    path("dashboard/engineer-performance/", EngineerPerformanceView.as_view()),
    path("dashboard/manager-approvals/", ManagerApprovalView.as_view()),
    path("dashboard/ticket-aging/", TicketAgingView.as_view()),
    path("dashboard/region-comparison/", RegionComparisonView.as_view()),
    # Non-parameterised ticket paths first
    path("tickets/send-otp/", SendOTPView.as_view()),
    path("tickets/verify-and-submit/", VerifyOTPAndSubmitView.as_view()),
    path("tickets/my-queue/", MyQueueView.as_view()),
    path("tickets/breached/", BreachedTicketsView.as_view()),
    # Ticket CRUD + workflow
    path("tickets/", TicketListCreateView.as_view()),
    path("tickets/<int:pk>/", TicketDetailView.as_view()),
    path("tickets/<int:pk>/transition/", TicketTransitionView.as_view()),
    path("tickets/<int:pk>/transitions/", AvailableTransitionsView.as_view()),
    path("tickets/<int:pk>/timeline/", TicketTimelineView.as_view()),
]
