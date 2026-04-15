import math

from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    BufferAuditLog,
    BufferCase,
    BufferStockItem,
    CaseProof,
    InterRegionTransfer,
    OOWApproval,
    ReplenishmentOrder,
)
from .permissions import CanApproveOOW, CanApproveTransfer
from .serializers import (
    BufferAuditLogSerializer,
    BufferCaseDetailSerializer,
    BufferCaseListSerializer,
    BufferCaseWriteSerializer,
    BufferStockItemSerializer,
    CaseProofSerializer,
    InterRegionTransferSerializer,
    OOWApprovalSerializer,
    ReplenishmentOrderSerializer,
)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _get_role(user):
    profile = getattr(user, "userprofile", None)
    return getattr(profile, "role", "")


def _get_region(user):
    profile = getattr(user, "userprofile", None)
    return getattr(profile, "region", "") or ""


def _user_name(user):
    if not user:
        return ""
    name = f"{user.first_name} {user.last_name}".strip()
    return name if name else user.username


def _log(action, entity_type, entity_id, actor, region="", details=None):
    BufferAuditLog.objects.create(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        region=region,
        details=details or {},
    )


def paginate_queryset(queryset, request):
    try:
        page = max(int(request.query_params.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = min(max(int(request.query_params.get("per_page", 20)), 1), 100)
    except (TypeError, ValueError):
        per_page = 20

    total = queryset.count()
    pages = math.ceil(total / per_page) if total else 1
    start = (page - 1) * per_page
    end = start + per_page

    return queryset[start:end], {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Buffer Stock Items
# ═════════════════════════════════════════════════════════════════════════════

class BufferStockItemListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = BufferStockItem.objects.all()

        # Region scoping: sub_admin sees only their region by default
        view_mode = request.query_params.get("view", "my_region")
        role = _get_role(request.user)
        user_region = _get_region(request.user)

        if view_mode == "my_region" and user_region:
            qs = qs.filter(region=user_region)
        elif view_mode == "my_region" and role not in ("super_admin", "admin"):
            qs = qs.filter(region=user_region) if user_region else qs.none()

        # Explicit region filter
        region_filter = request.query_params.get("region")
        if region_filter:
            qs = qs.filter(region=region_filter)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(part_number__icontains=search)
                | Q(part_name__icontains=search)
                | Q(description__icontains=search)
            )

        category = request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)

        low_stock = request.query_params.get("low_stock")
        if low_stock and low_stock.lower() in ("true", "1"):
            from django.db.models import F
            qs = qs.filter(qty_on_hand__lte=F("reorder_level"))

        page_qs, meta = paginate_queryset(qs, request)
        serializer = BufferStockItemSerializer(page_qs, many=True)
        return Response({"items": serializer.data, **meta})

    def post(self, request):
        serializer = BufferStockItemSerializer(data=request.data)
        if serializer.is_valid():
            item = serializer.save()
            _log("stock_created", "buffer_stock_item", item.pk, request.user,
                 region=item.region, details={"part_number": item.part_number})
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BufferStockItemDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get(self, pk):
        try:
            return BufferStockItem.objects.get(pk=pk)
        except BufferStockItem.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self._get(pk)
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(BufferStockItemSerializer(obj).data)

    def put(self, request, pk):
        obj = self._get(pk)
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = BufferStockItemSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            item = serializer.save()
            _log("stock_updated", "buffer_stock_item", item.pk, request.user,
                 region=item.region)
            return Response(BufferStockItemSerializer(item).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = self._get(pk)
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BufferStockAdjustView(APIView):
    """Adjust buffer stock quantity (e.g. manual correction)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            item = BufferStockItem.objects.get(pk=pk)
        except BufferStockItem.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            qty = int(request.data.get("quantity", 0))
        except (TypeError, ValueError):
            return Response({"detail": "quantity must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get("reason", "")
        item.qty_on_hand += qty
        if item.qty_on_hand < 0:
            item.qty_on_hand = 0
        item.save()

        _log("stock_adjusted", "buffer_stock_item", item.pk, request.user,
             region=item.region, details={"qty_change": qty, "reason": reason})

        return Response(BufferStockItemSerializer(item).data)


# ═════════════════════════════════════════════════════════════════════════════
# Buffer Cases
# ═════════════════════════════════════════════════════════════════════════════

class BufferCaseListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = BufferCase.objects.select_related(
            "buffer_stock_item", "assigned_engineer", "created_by", "approved_by",
        ).all()

        role = _get_role(request.user)
        user_region = _get_region(request.user)

        # Sub-admins see only their region
        if role == "sub_admin" and user_region:
            qs = qs.filter(region=user_region)

        # Filters
        case_type = request.query_params.get("case_type")
        if case_type:
            qs = qs.filter(case_type=case_type)

        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        region = request.query_params.get("region")
        if region:
            qs = qs.filter(region=region)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(case_number__icontains=search)
                | Q(case_id__icontains=search)
                | Q(customer_name__icontains=search)
                | Q(part_number__icontains=search)
            )

        page_qs, meta = paginate_queryset(qs, request)
        serializer = BufferCaseListSerializer(page_qs, many=True)
        return Response({"items": serializer.data, **meta})

    def post(self, request):
        serializer = BufferCaseWriteSerializer(data=request.data)
        if serializer.is_valid():
            case = serializer.save(created_by=request.user)

            # For OOW, automatically create pending approval
            if case.case_type == "oow":
                case.status = "pending_approval"
                case.save()
                OOWApproval.objects.create(
                    buffer_case=case,
                    requested_by=request.user,
                )
                _log("oow_requested", "buffer_case", case.pk, request.user,
                     region=case.region, details={"case_number": case.case_number})

            _log("case_created", "buffer_case", case.pk, request.user,
                 region=case.region,
                 details={"case_type": case.case_type, "case_number": case.case_number})

            return Response(
                BufferCaseDetailSerializer(case).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BufferCaseDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get(self, pk):
        try:
            return BufferCase.objects.select_related(
                "buffer_stock_item", "assigned_engineer",
                "created_by", "approved_by",
            ).prefetch_related("proofs").get(pk=pk)
        except BufferCase.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self._get(pk)
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(BufferCaseDetailSerializer(obj).data)

    def put(self, request, pk):
        obj = self._get(pk)
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = BufferCaseWriteSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(BufferCaseDetailSerializer(obj).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BufferCaseAllocatePartView(APIView):
    """Allocate a buffer stock part to a case. Decrements available quantity."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            case = BufferCase.objects.get(pk=pk)
        except BufferCase.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        # OOW must be approved first
        if case.case_type == "oow" and case.status not in ("approved", "created"):
            if case.status == "pending_approval":
                return Response(
                    {"detail": "OOW case must be approved before allocating parts."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        stock_item_id = request.data.get("buffer_stock_item_id")
        qty = int(request.data.get("qty_used", case.qty_used or 1))

        try:
            stock_item = BufferStockItem.objects.get(pk=stock_item_id)
        except BufferStockItem.DoesNotExist:
            return Response(
                {"detail": "Buffer stock item not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if stock_item.qty_available < qty:
            return Response(
                {"detail": f"Only {stock_item.qty_available} available in {stock_item.get_region_display()}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Reserve stock
        stock_item.qty_reserved += qty
        stock_item.save()

        case.buffer_stock_item = stock_item
        case.part_number = stock_item.part_number
        case.part_name = stock_item.part_name
        case.qty_used = qty
        case.source_region = stock_item.region
        case.status = "part_allocated"
        case.save()

        _log("part_allocated", "buffer_case", case.pk, request.user,
             region=case.region,
             details={
                 "stock_item": stock_item.pk,
                 "part_number": stock_item.part_number,
                 "qty": qty,
                 "source_region": stock_item.region,
             })

        return Response(BufferCaseDetailSerializer(case).data)


class BufferCaseAssignEngineerView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        from authenticate.models import Engineer

        try:
            case = BufferCase.objects.get(pk=pk)
        except BufferCase.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        engineer_id = request.data.get("engineer_id")
        try:
            engineer = Engineer.objects.get(pk=engineer_id, status="active")
        except Engineer.DoesNotExist:
            return Response(
                {"detail": "Engineer not found or inactive."},
                status=status.HTTP_404_NOT_FOUND,
            )

        case.assigned_engineer = engineer
        case.status = "engineer_assigned"
        case.save()

        _log("case_status_changed", "buffer_case", case.pk, request.user,
             region=case.region,
             details={"to_status": "engineer_assigned", "engineer": engineer.name})

        return Response(BufferCaseDetailSerializer(case).data)


class BufferCaseTransitionView(APIView):
    """Generic status transition for a buffer case."""
    permission_classes = [permissions.IsAuthenticated]

    ALLOWED_TRANSITIONS = {
        "created": ["part_allocated", "pending_approval", "cancelled"],
        "pending_approval": ["approved", "rejected"],
        "approved": ["part_allocated", "cancelled"],
        "part_allocated": ["engineer_assigned", "transfer_requested"],
        "transfer_requested": ["part_allocated", "cancelled"],
        "engineer_assigned": ["in_progress"],
        "in_progress": ["service_completed"],
        "service_completed": ["pending_replenishment"],
        "pending_replenishment": ["replenishment_ordered"],
        "replenishment_ordered": ["stock_replenished"],
        "stock_replenished": ["closed"],
    }

    def post(self, request, pk):
        try:
            case = BufferCase.objects.get(pk=pk)
        except BufferCase.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        to_status = request.data.get("to_status")
        if not to_status:
            return Response(
                {"detail": "to_status is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allowed = self.ALLOWED_TRANSITIONS.get(case.status, [])
        if to_status not in allowed:
            return Response(
                {"detail": f"Cannot transition from '{case.status}' to '{to_status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Role guards
        role = _get_role(request.user)

        if to_status in ("approved", "rejected") and role not in ("super_admin", "admin", "manager"):
            return Response(
                {"detail": "Only Manager or Super Admin can approve/reject OOW cases."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # CRITICAL: cannot close until stock_replenished
        if to_status == "closed" and case.status != "stock_replenished":
            return Response(
                {"detail": "Case cannot be closed until replacement stock is received from HP."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = case.status
        case.status = to_status

        if to_status == "closed":
            case.closed_at = timezone.now()

        comment = request.data.get("comment", "")

        case.save()

        _log("case_status_changed", "buffer_case", case.pk, request.user,
             region=case.region,
             details={
                 "from_status": old_status,
                 "to_status": to_status,
                 "comment": comment,
             })

        return Response(BufferCaseDetailSerializer(case).data)


class BufferCaseCompleteServiceView(APIView):
    """Mark service as completed. Requires resolution summary."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            case = BufferCase.objects.get(pk=pk)
        except BufferCase.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if case.status != "in_progress":
            return Response(
                {"detail": "Case must be in_progress to complete service."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        resolution = request.data.get("resolution_summary", "")
        service_notes = request.data.get("service_notes", "")

        case.resolution_summary = resolution
        case.service_notes = service_notes
        case.status = "service_completed"
        case.save()

        _log("case_status_changed", "buffer_case", case.pk, request.user,
             region=case.region,
             details={"to_status": "service_completed", "resolution": resolution})

        return Response(BufferCaseDetailSerializer(case).data)


class BufferCaseTriggerReplenishmentView(APIView):
    """Auto-trigger replenishment order to HP after service completion."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            case = BufferCase.objects.select_related("buffer_stock_item").get(pk=pk)
        except BufferCase.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if case.status != "service_completed":
            return Response(
                {"detail": "Service must be completed before triggering replenishment."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if hasattr(case, "replenishment_order") and case.replenishment_order:
            return Response(
                {"detail": "Replenishment order already exists for this case."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stock_item = case.buffer_stock_item

        order = ReplenishmentOrder.objects.create(
            buffer_case=case,
            buffer_stock_item=stock_item,
            part_number=case.part_number,
            part_name=case.part_name,
            quantity=case.qty_used,
            region=case.region,
            ordered_by=request.user,
            order_date=timezone.now().date(),
        )

        case.status = "pending_replenishment"
        case.save()

        _log("replenishment_created", "replenishment_order", order.pk, request.user,
             region=case.region,
             details={
                 "case_number": case.case_number,
                 "order_number": order.order_number,
                 "part_number": order.part_number,
                 "quantity": order.quantity,
             })

        return Response(BufferCaseDetailSerializer(case).data, status=status.HTTP_201_CREATED)


# ═════════════════════════════════════════════════════════════════════════════
# Proof Upload
# ═════════════════════════════════════════════════════════════════════════════

class CaseProofUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        try:
            case = BufferCase.objects.get(pk=pk)
        except BufferCase.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        file = request.FILES.get("file")
        if not file:
            return Response(
                {"detail": "file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        proof = CaseProof.objects.create(
            buffer_case=case,
            proof_type=request.data.get("proof_type", "image"),
            file=file,
            description=request.data.get("description", ""),
            uploaded_by=request.user,
        )

        case.proof_uploaded = True
        case.save()

        _log("proof_uploaded", "case_proof", proof.pk, request.user,
             region=case.region,
             details={"case_number": case.case_number, "proof_type": proof.proof_type})

        return Response(CaseProofSerializer(proof).data, status=status.HTTP_201_CREATED)


# ═════════════════════════════════════════════════════════════════════════════
# OOW Approvals
# ═════════════════════════════════════════════════════════════════════════════

class OOWApprovalListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = OOWApproval.objects.select_related(
            "buffer_case", "requested_by", "approved_by",
        ).all()

        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        page_qs, meta = paginate_queryset(qs, request)
        serializer = OOWApprovalSerializer(page_qs, many=True)
        return Response({"items": serializer.data, **meta})


class OOWApprovalActionView(APIView):
    permission_classes = [permissions.IsAuthenticated, CanApproveOOW]

    def post(self, request, pk):
        try:
            approval = OOWApproval.objects.select_related("buffer_case").get(pk=pk)
        except OOWApproval.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if approval.status != "pending":
            return Response(
                {"detail": "This approval has already been processed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action = request.data.get("action")  # "approve" or "reject"
        reason = request.data.get("reason", "")

        if action not in ("approve", "reject"):
            return Response(
                {"detail": "action must be 'approve' or 'reject'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        role = _get_role(request.user)

        approval.approved_by = request.user
        approval.approver_role = role
        approval.reason = reason
        approval.responded_at = timezone.now()

        case = approval.buffer_case

        if action == "approve":
            approval.status = "approved"
            case.status = "approved"
            case.approved_by = request.user
            case.approved_at = timezone.now()
            audit_action = "oow_approved"
        else:
            approval.status = "rejected"
            case.status = "rejected"
            audit_action = "oow_rejected"

        approval.save()
        case.save()

        _log(audit_action, "oow_approval", approval.pk, request.user,
             region=case.region,
             details={
                 "case_number": case.case_number,
                 "approver": _user_name(request.user),
                 "approver_role": role,
                 "reason": reason,
             })

        return Response(OOWApprovalSerializer(approval).data)


# ═════════════════════════════════════════════════════════════════════════════
# Inter-Region Transfers
# ═════════════════════════════════════════════════════════════════════════════

class TransferListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = InterRegionTransfer.objects.select_related(
            "buffer_stock_item", "requested_by", "approved_by", "received_by",
        ).all()

        role = _get_role(request.user)
        user_region = _get_region(request.user)

        if role == "sub_admin" and user_region:
            qs = qs.filter(
                Q(source_region=user_region) | Q(destination_region=user_region)
            )

        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        page_qs, meta = paginate_queryset(qs, request)
        serializer = InterRegionTransferSerializer(page_qs, many=True)
        return Response({"items": serializer.data, **meta})

    def post(self, request):
        serializer = InterRegionTransferSerializer(data=request.data)
        if serializer.is_valid():
            transfer = serializer.save(requested_by=request.user)

            _log("transfer_requested", "inter_region_transfer", transfer.pk,
                 request.user, region=transfer.destination_region,
                 details={
                     "transfer_number": transfer.transfer_number,
                     "part_number": transfer.part_number,
                     "quantity": transfer.quantity,
                     "source": transfer.source_region,
                     "destination": transfer.destination_region,
                 })

            return Response(
                InterRegionTransferSerializer(transfer).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TransferDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            obj = InterRegionTransfer.objects.select_related(
                "buffer_stock_item", "requested_by", "approved_by",
            ).get(pk=pk)
        except InterRegionTransfer.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(InterRegionTransferSerializer(obj).data)


class TransferApproveView(APIView):
    permission_classes = [permissions.IsAuthenticated, CanApproveTransfer]

    def post(self, request, pk):
        try:
            transfer = InterRegionTransfer.objects.select_related(
                "buffer_stock_item",
            ).get(pk=pk)
        except InterRegionTransfer.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if transfer.status != "requested":
            return Response(
                {"detail": "Transfer is not in requested state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check source stock availability
        stock_item = transfer.buffer_stock_item
        if stock_item.qty_available < transfer.quantity:
            return Response(
                {"detail": f"Insufficient stock. Only {stock_item.qty_available} available."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Reserve from source
        stock_item.qty_reserved += transfer.quantity
        stock_item.save()

        transfer.status = "approved"
        transfer.approved_by = request.user
        transfer.approved_at = timezone.now()
        transfer.save()

        _log("transfer_approved", "inter_region_transfer", transfer.pk,
             request.user, region=transfer.source_region,
             details={"transfer_number": transfer.transfer_number})

        return Response(InterRegionTransferSerializer(transfer).data)


class TransferRejectView(APIView):
    permission_classes = [permissions.IsAuthenticated, CanApproveTransfer]

    def post(self, request, pk):
        try:
            transfer = InterRegionTransfer.objects.get(pk=pk)
        except InterRegionTransfer.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if transfer.status != "requested":
            return Response(
                {"detail": "Transfer is not in requested state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        transfer.status = "rejected"
        transfer.approved_by = request.user
        transfer.approved_at = timezone.now()
        transfer.rejection_reason = request.data.get("reason", "")
        transfer.save()

        _log("transfer_rejected", "inter_region_transfer", transfer.pk,
             request.user, region=transfer.source_region,
             details={"reason": transfer.rejection_reason})

        return Response(InterRegionTransferSerializer(transfer).data)


class TransferInTransitView(APIView):
    """Mark an approved transfer as in-transit."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            transfer = InterRegionTransfer.objects.select_related(
                "buffer_stock_item",
            ).get(pk=pk)
        except InterRegionTransfer.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if transfer.status != "approved":
            return Response(
                {"detail": "Transfer must be approved before transit."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Move from reserved to in-transit
        stock_item = transfer.buffer_stock_item
        stock_item.qty_reserved -= transfer.quantity
        stock_item.qty_on_hand -= transfer.quantity
        stock_item.save()

        transfer.status = "in_transit"
        transfer.save()

        return Response(InterRegionTransferSerializer(transfer).data)


class TransferReceiveView(APIView):
    """Mark transfer as received at destination. Creates stock in destination region."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            transfer = InterRegionTransfer.objects.select_related(
                "buffer_stock_item",
            ).get(pk=pk)
        except InterRegionTransfer.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if transfer.status != "in_transit":
            return Response(
                {"detail": "Transfer must be in-transit to receive."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Add stock to destination region
        dest_item, created = BufferStockItem.objects.get_or_create(
            part_number=transfer.part_number,
            region=transfer.destination_region,
            defaults={
                "part_name": transfer.part_name,
                "brand": transfer.buffer_stock_item.brand,
                "category": transfer.buffer_stock_item.category,
            },
        )
        dest_item.qty_on_hand += transfer.quantity
        dest_item.save()

        transfer.status = "received"
        transfer.received_by = request.user
        transfer.received_at = timezone.now()
        transfer.save()

        _log("transfer_received", "inter_region_transfer", transfer.pk,
             request.user, region=transfer.destination_region,
             details={
                 "transfer_number": transfer.transfer_number,
                 "quantity": transfer.quantity,
             })

        return Response(InterRegionTransferSerializer(transfer).data)


# ═════════════════════════════════════════════════════════════════════════════
# Replenishment Orders
# ═════════════════════════════════════════════════════════════════════════════

class ReplenishmentListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = ReplenishmentOrder.objects.select_related(
            "buffer_case", "buffer_stock_item", "ordered_by", "received_by",
        ).all()

        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        region = request.query_params.get("region")
        if region:
            qs = qs.filter(region=region)

        page_qs, meta = paginate_queryset(qs, request)
        serializer = ReplenishmentOrderSerializer(page_qs, many=True)
        return Response({"items": serializer.data, **meta})


class ReplenishmentDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            obj = ReplenishmentOrder.objects.select_related(
                "buffer_case", "buffer_stock_item",
            ).get(pk=pk)
        except ReplenishmentOrder.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ReplenishmentOrderSerializer(obj).data)

    def put(self, request, pk):
        try:
            obj = ReplenishmentOrder.objects.get(pk=pk)
        except ReplenishmentOrder.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ReplenishmentOrderSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(ReplenishmentOrderSerializer(obj).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ReplenishmentReceiveView(APIView):
    """Mark replenishment as received. Replenishes buffer stock and allows case closure."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            order = ReplenishmentOrder.objects.select_related(
                "buffer_case", "buffer_stock_item",
            ).get(pk=pk)
        except ReplenishmentOrder.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if order.status == "received":
            return Response(
                {"detail": "Already received."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Replenish stock
        stock_item = order.buffer_stock_item
        stock_item.qty_on_hand += order.quantity
        stock_item.qty_reserved = max(0, stock_item.qty_reserved - order.quantity)
        stock_item.last_replenished_at = timezone.now()
        stock_item.save()

        order.status = "received"
        order.received_by = request.user
        order.received_at = timezone.now()
        order.save()

        # Update case status
        case = order.buffer_case
        if case:
            case.status = "stock_replenished"
            case.save()

        _log("replenishment_received", "replenishment_order", order.pk,
             request.user, region=order.region,
             details={
                 "order_number": order.order_number,
                 "quantity": order.quantity,
                 "case_number": case.case_number if case else "",
             })

        return Response(ReplenishmentOrderSerializer(order).data)


# ═════════════════════════════════════════════════════════════════════════════
# Audit Log
# ═════════════════════════════════════════════════════════════════════════════

class AuditLogListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = BufferAuditLog.objects.select_related("actor").all()

        action = request.query_params.get("action")
        if action:
            qs = qs.filter(action=action)

        entity_type = request.query_params.get("entity_type")
        if entity_type:
            qs = qs.filter(entity_type=entity_type)

        region = request.query_params.get("region")
        if region:
            qs = qs.filter(region=region)

        page_qs, meta = paginate_queryset(qs, request)
        serializer = BufferAuditLogSerializer(page_qs, many=True)
        return Response({"items": serializer.data, **meta})


# ═════════════════════════════════════════════════════════════════════════════
# Dashboard
# ═════════════════════════════════════════════════════════════════════════════

class BufferStockDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        role = _get_role(request.user)
        user_region = _get_region(request.user)

        # Stock summary
        stock_qs = BufferStockItem.objects.all()
        if role == "sub_admin" and user_region:
            stock_qs = stock_qs.filter(region=user_region)

        total_stock_items = stock_qs.count()
        total_qty = stock_qs.aggregate(total=Sum("qty_on_hand"))["total"] or 0

        from django.db.models import F
        low_stock_count = stock_qs.filter(qty_on_hand__lte=F("reorder_level")).count()

        # Case summary
        case_qs = BufferCase.objects.all()
        if role == "sub_admin" and user_region:
            case_qs = case_qs.filter(region=user_region)

        total_cases = case_qs.count()
        open_cases = case_qs.exclude(status__in=["closed", "cancelled", "rejected"]).count()
        iw_cases = case_qs.filter(case_type="iw").count()
        oow_cases = case_qs.filter(case_type="oow").count()

        pending_approvals = OOWApproval.objects.filter(status="pending").count()

        # Cases by status
        cases_by_status = {}
        for s in BufferCase.STATUS_CHOICES:
            count = case_qs.filter(status=s[0]).count()
            if count:
                cases_by_status[s[0]] = count

        # Transfer summary
        transfer_qs = InterRegionTransfer.objects.all()
        pending_transfers = transfer_qs.filter(status="requested").count()
        in_transit_transfers = transfer_qs.filter(status="in_transit").count()

        # Replenishment summary
        pending_replenishments = ReplenishmentOrder.objects.exclude(
            status__in=["received", "cancelled"],
        ).count()

        # Region stock summary
        region_stock = []
        for region_code, region_label in BufferStockItem._meta.get_field("region").choices:
            r_qs = BufferStockItem.objects.filter(region=region_code)
            r_total = r_qs.aggregate(total=Sum("qty_on_hand"))["total"] or 0
            r_reserved = r_qs.aggregate(total=Sum("qty_reserved"))["total"] or 0
            r_items = r_qs.count()
            r_low = r_qs.filter(qty_on_hand__lte=F("reorder_level")).count()
            region_stock.append({
                "region": region_code,
                "region_display": region_label,
                "total_items": r_items,
                "total_qty": r_total,
                "total_reserved": r_reserved,
                "low_stock_count": r_low,
            })

        return Response({
            "total_stock_items": total_stock_items,
            "total_qty": total_qty,
            "low_stock_count": low_stock_count,
            "total_cases": total_cases,
            "open_cases": open_cases,
            "iw_cases": iw_cases,
            "oow_cases": oow_cases,
            "pending_approvals": pending_approvals,
            "cases_by_status": cases_by_status,
            "pending_transfers": pending_transfers,
            "in_transit_transfers": in_transit_transfers,
            "pending_replenishments": pending_replenishments,
            "region_stock": region_stock,
        })
