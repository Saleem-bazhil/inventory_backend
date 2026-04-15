from django.urls import path

from .views import (
    AuditLogListView,
    BufferCaseAllocatePartView,
    BufferCaseAssignEngineerView,
    BufferCaseCompleteServiceView,
    BufferCaseDetailView,
    BufferCaseListCreateView,
    BufferCaseTriggerReplenishmentView,
    BufferCaseTransitionView,
    BufferStockAdjustView,
    BufferStockDashboardView,
    BufferStockItemDetailView,
    BufferStockItemListCreateView,
    CaseProofUploadView,
    OOWApprovalActionView,
    OOWApprovalListView,
    ReplenishmentDetailView,
    ReplenishmentListView,
    ReplenishmentReceiveView,
    TransferApproveView,
    TransferDetailView,
    TransferInTransitView,
    TransferListCreateView,
    TransferReceiveView,
    TransferRejectView,
)

urlpatterns = [
    # Dashboard
    path("buffer-stock/dashboard/", BufferStockDashboardView.as_view(), name="buffer-stock-dashboard"),

    # Buffer Stock Items
    path("buffer-stock/items/", BufferStockItemListCreateView.as_view(), name="buffer-stock-list"),
    path("buffer-stock/items/<int:pk>/", BufferStockItemDetailView.as_view(), name="buffer-stock-detail"),
    path("buffer-stock/items/<int:pk>/adjust/", BufferStockAdjustView.as_view(), name="buffer-stock-adjust"),

    # Buffer Cases
    path("buffer-stock/cases/", BufferCaseListCreateView.as_view(), name="buffer-case-list"),
    path("buffer-stock/cases/<int:pk>/", BufferCaseDetailView.as_view(), name="buffer-case-detail"),
    path("buffer-stock/cases/<int:pk>/allocate-part/", BufferCaseAllocatePartView.as_view(), name="buffer-case-allocate"),
    path("buffer-stock/cases/<int:pk>/assign-engineer/", BufferCaseAssignEngineerView.as_view(), name="buffer-case-assign"),
    path("buffer-stock/cases/<int:pk>/transition/", BufferCaseTransitionView.as_view(), name="buffer-case-transition"),
    path("buffer-stock/cases/<int:pk>/complete-service/", BufferCaseCompleteServiceView.as_view(), name="buffer-case-complete"),
    path("buffer-stock/cases/<int:pk>/trigger-replenishment/", BufferCaseTriggerReplenishmentView.as_view(), name="buffer-case-replenish"),
    path("buffer-stock/cases/<int:pk>/upload-proof/", CaseProofUploadView.as_view(), name="buffer-case-proof"),

    # OOW Approvals
    path("buffer-stock/approvals/", OOWApprovalListView.as_view(), name="oow-approval-list"),
    path("buffer-stock/approvals/<int:pk>/action/", OOWApprovalActionView.as_view(), name="oow-approval-action"),

    # Inter-Region Transfers
    path("buffer-stock/transfers/", TransferListCreateView.as_view(), name="transfer-list"),
    path("buffer-stock/transfers/<int:pk>/", TransferDetailView.as_view(), name="transfer-detail"),
    path("buffer-stock/transfers/<int:pk>/approve/", TransferApproveView.as_view(), name="transfer-approve"),
    path("buffer-stock/transfers/<int:pk>/reject/", TransferRejectView.as_view(), name="transfer-reject"),
    path("buffer-stock/transfers/<int:pk>/in-transit/", TransferInTransitView.as_view(), name="transfer-in-transit"),
    path("buffer-stock/transfers/<int:pk>/receive/", TransferReceiveView.as_view(), name="transfer-receive"),

    # Replenishment Orders
    path("buffer-stock/replenishments/", ReplenishmentListView.as_view(), name="replenishment-list"),
    path("buffer-stock/replenishments/<int:pk>/", ReplenishmentDetailView.as_view(), name="replenishment-detail"),
    path("buffer-stock/replenishments/<int:pk>/receive/", ReplenishmentReceiveView.as_view(), name="replenishment-receive"),

    # Audit Logs
    path("buffer-stock/audit-logs/", AuditLogListView.as_view(), name="buffer-audit-list"),
]
