import logging
import math
import re

from django.contrib.auth.models import User
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from authenticate.models import Engineer, UserProfile
# OTP disabled — uncomment when SMS provider is available
# from material.sms import send_otp_sms, verify_otp

from .models import DelayRecord, Ticket, TicketTimeline
from .serializers import (
    AvailableTransitionSerializer,
    TicketCreateSerializer,
    TicketDetailSerializer,
    TicketListSerializer,
    TicketUpdateSerializer,
    TimelineEntrySerializer,
    TransitionSerializer,
)
from .services import (
    TransitionError,
    get_available_transitions,
    lookup_sla,
    transition_ticket,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_user_role(user):
    """
    Map the logged-in user's profile role to a workflow role.

    Important: this returns the ACTOR's role (the person performing the
    action), never the role of the engineer being assigned.
    sub_admin / super_admin are regional admins with full workflow control.
    """
    profile = getattr(user, "userprofile", None)
    if not profile:
        return "admin"

    role = profile.role
    role_map = {
        "super_admin": "admin",
        "sub_admin": "sub_admin",
        "admin": "admin",
        "manager": "manager",
        "engineer": "engineer",
        "receptionist": "receptionist",
        "cc_team": "cc_team",
    }
    return role_map.get(role, "admin")


def get_user_region(user):
    """Return the user's region from their profile, or None."""
    profile = getattr(user, "userprofile", None)
    if profile:
        return profile.region
    return None


def _paginate(queryset, request):
    """
    Apply page-based pagination and return (items_qs, meta_dict).
    Query params: page (default 1), per_page (default 20).
    """
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = max(1, min(100, int(request.query_params.get("per_page", 20))))
    except (ValueError, TypeError):
        per_page = 20

    total = queryset.count()
    pages = max(1, math.ceil(total / per_page))
    page = min(page, pages)  # clamp

    start = (page - 1) * per_page
    items_qs = queryset[start: start + per_page]

    meta = {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }
    return items_qs, meta


def _clean_phone(phone: str) -> str:
    """Strip non-digits and remove leading +91 / 91 to get 10-digit Indian number."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 13 and digits.startswith("091"):
        digits = digits[3:]
    return digits


# ---------------------------------------------------------------------------
# Ticket List + Create
# ---------------------------------------------------------------------------

class TicketListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        role = get_user_role(user)
        profile = getattr(user, "userprofile", None)

        # Region scoping: admin sees all, others see their region
        if role == "admin":
            qs = Ticket.objects.all()
        elif profile and profile.region:
            qs = Ticket.objects.filter(region=profile.region)
        else:
            qs = Ticket.objects.filter(
                Q(created_by=user) | Q(current_assignee=user)
            )

        params = request.query_params

        # --- Filters ---
        search = params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(cust_name__icontains=search)
                | Q(ticket_number__icontains=search)
                | Q(case_id__icontains=search)
                | Q(product_name__icontains=search)
                | Q(serial_number__icontains=search)
                | Q(cust_contact__icontains=search)
                | Q(engineer_name__icontains=search)
            )

        filter_status = params.get("status", "").strip()
        if filter_status:
            qs = qs.filter(current_status=filter_status)

        filter_priority = params.get("priority", "").strip()
        if filter_priority:
            qs = qs.filter(priority=filter_priority)

        filter_service_type = params.get("service_type", "").strip()
        if filter_service_type:
            qs = qs.filter(service_type=filter_service_type)

        filter_assignee = params.get("assignee_id", "").strip()
        if filter_assignee:
            qs = qs.filter(current_assignee_id=filter_assignee)

        filter_region = params.get("region", "").strip()
        if filter_region and role == "admin":
            qs = qs.filter(region=filter_region)

        # SLA health filter — requires in-memory filtering as it's computed
        filter_sla = params.get("sla_health", "").strip()

        # Ordering
        ordering = params.get("ordering", "-created_at")
        allowed_orderings = {
            "created_at", "-created_at",
            "updated_at", "-updated_at",
            "ticket_number", "-ticket_number",
            "cust_name", "-cust_name",
            "priority", "-priority",
            "current_status", "-current_status",
            "arrival_date", "-arrival_date",
        }
        if ordering in allowed_orderings:
            qs = qs.order_by(ordering)

        # If SLA health filter is requested, we need to compute it per ticket.
        # This is done post-query since it depends on the current timeline entry.
        if filter_sla:
            # Fetch all, then filter in Python (acceptable for moderate datasets)
            items_qs, meta = _paginate(qs, request)
            serializer = TicketListSerializer(items_qs, many=True)
            filtered_data = [
                item for item in serializer.data
                if item.get("sla_health") == filter_sla
            ]
            # Adjust meta for filtered count
            meta["total"] = len(filtered_data)
            meta["pages"] = max(1, math.ceil(len(filtered_data) / meta["per_page"]))
            return Response({"items": filtered_data, **meta})

        items_qs, meta = _paginate(qs, request)
        serializer = TicketListSerializer(items_qs, many=True)
        return Response({"items": serializer.data, **meta})

    def post(self, request):
        serializer = TicketCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        profile = getattr(user, "userprofile", None)
        region = serializer.validated_data.get("region") or (
            profile.region if profile else None
        )

        ticket = serializer.save(
            created_by=user,
            region=region,
            current_status="cso_created",
        )

        # Create initial timeline entry
        sla_config = lookup_sla("cso_created", ticket.service_type, ticket.priority)
        TicketTimeline.objects.create(
            ticket=ticket,
            from_status=None,
            to_status="cso_created",
            actor=user,
            actor_role=get_user_role(user),
            comment="Ticket created",
            entered_at=timezone.now(),
            sla_minutes=sla_config.sla_minutes if sla_config else None,
            responsible_role=sla_config.responsible_role if sla_config else None,
        )

        return Response(
            TicketDetailSerializer(ticket).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Ticket Detail (GET / PUT / DELETE)
# ---------------------------------------------------------------------------

class TicketDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_ticket(self, request, pk):
        user = request.user
        role = get_user_role(user)
        profile = getattr(user, "userprofile", None)

        try:
            ticket = Ticket.objects.get(pk=pk)
        except Ticket.DoesNotExist:
            return None

        # Access control
        if role == "admin":
            return ticket
        if profile and profile.region and ticket.region == profile.region:
            return ticket
        if ticket.created_by == user or ticket.current_assignee == user:
            return ticket

        return None  # no access

    def get(self, request, pk):
        ticket = self._get_ticket(request, pk)
        if ticket is None:
            return Response(
                {"detail": "Ticket not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(TicketDetailSerializer(ticket).data)

    def put(self, request, pk):
        ticket = self._get_ticket(request, pk)
        if ticket is None:
            return Response(
                {"detail": "Ticket not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = TicketUpdateSerializer(ticket, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(TicketDetailSerializer(ticket).data)

    def delete(self, request, pk):
        ticket = self._get_ticket(request, pk)
        if ticket is None:
            return Response(
                {"detail": "Ticket not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        role = get_user_role(request.user)
        if role != "admin":
            return Response(
                {"detail": "Only admins can delete tickets."},
                status=status.HTTP_403_FORBIDDEN,
            )
        ticket.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Ticket Transition (POST)
# ---------------------------------------------------------------------------

class TicketTransitionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            ticket = Ticket.objects.get(pk=pk)
        except Ticket.DoesNotExist:
            return Response(
                {"detail": "Ticket not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = TransitionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        to_status = serializer.validated_data["to_status"]
        comment = serializer.validated_data.get("comment", "")
        assignee_id = serializer.validated_data.get("assignee_id")
        engineer_id = serializer.validated_data.get("engineer_id")

        actor = request.user
        actor_role = get_user_role(actor)

        # On 'assigned' transition, validate and set the engineer
        if to_status == "assigned":
            if not engineer_id and not assignee_id:
                return Response(
                    {"detail": "An engineer must be selected for assignment."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            eid = engineer_id or assignee_id
            try:
                engineer = Engineer.objects.get(pk=eid)
            except Engineer.DoesNotExist:
                return Response(
                    {"detail": f"Engineer with id {eid} not found."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate: engineer must be active
            if engineer.status != "active":
                return Response(
                    {"detail": f"Engineer '{engineer.name}' is inactive and cannot be assigned."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate: engineer must be from same region as ticket
            if ticket.region and engineer.region != ticket.region:
                return Response(
                    {"detail": f"Engineer '{engineer.name}' belongs to {engineer.get_region_display()}, "
                               f"but this ticket is in {ticket.get_region_display()}. "
                               f"Cross-region assignment is not allowed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            ticket.assigned_engineer = engineer
            ticket.assigned_at = timezone.now()

        try:
            ticket = transition_ticket(
                ticket=ticket,
                to_status=to_status,
                actor=actor,
                actor_role=actor_role,
                comment=comment,
                metadata={"engineer_id": engineer_id or assignee_id} if (engineer_id or assignee_id) else {},
            )
        except TransitionError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(TicketDetailSerializer(ticket).data)


# ---------------------------------------------------------------------------
# Available Transitions (GET)
# ---------------------------------------------------------------------------

class AvailableTransitionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            ticket = Ticket.objects.get(pk=pk)
        except Ticket.DoesNotExist:
            return Response(
                {"detail": "Ticket not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        actor_role = get_user_role(request.user)
        available = get_available_transitions(ticket, actor_role)

        # Build user-friendly list
        status_labels = dict(Ticket.TICKET_STATUS_CHOICES)
        result = []
        for t in available:
            result.append({
                "to_status": t["to"],
                "label": status_labels.get(t["to"], t["to"]),
                "requires_comment": t["to"] in ("cx_rejected", "closed"),
            })

        serializer = AvailableTransitionSerializer(result, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Ticket Timeline (GET)
# ---------------------------------------------------------------------------

class TicketTimelineView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            ticket = Ticket.objects.get(pk=pk)
        except Ticket.DoesNotExist:
            return Response(
                {"detail": "Ticket not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        entries = TicketTimeline.objects.filter(ticket=ticket).order_by("entered_at")
        serializer = TimelineEntrySerializer(entries, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# OTP views (delegating to material.sms)
# ---------------------------------------------------------------------------

class SendOTPView(APIView):
    """
    OTP sending is currently disabled (no SMS provider).
    This endpoint is kept as a stub so the frontend doesn't break
    if it ever calls it. Enable when an SMS provider is configured.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response({
            "detail": "OTP verification is currently disabled. Submit the ticket directly after customer review."
        })


class VerifyOTPAndSubmitView(APIView):
    """
    Create a ticket after customer review.

    OTP verification is currently disabled (no SMS provider).
    Accepts form_data directly and creates the ticket.
    When an SMS provider is configured, uncomment the OTP verification block.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        form_data = request.data.get("form_data", {})
        if not form_data:
            form_data = request.data  # allow flat payload too

        # ── OTP verification disabled ────────────────────────────
        # phone = request.data.get("phone", "").strip()
        # otp = request.data.get("otp", "").strip()
        # if not phone or not otp:
        #     return Response({"detail": "Phone and OTP required."}, status=status.HTTP_400_BAD_REQUEST)
        # cleaned = _clean_phone(phone)
        # if not verify_otp(cleaned, otp):
        #     return Response({"detail": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)
        # ─────────────────────────────────────────────────────────

        serializer = TicketCreateSerializer(data=form_data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        profile = getattr(user, "userprofile", None)
        region = form_data.get("region") or (profile.region if profile else None)

        ticket = serializer.save(
            created_by=user,
            region=region,
            current_status="cso_created",
        )

        # Create initial timeline entry
        sla_config = lookup_sla("cso_created", ticket.service_type, ticket.priority)
        TicketTimeline.objects.create(
            ticket=ticket,
            from_status=None,
            to_status="cso_created",
            actor=user,
            actor_role=get_user_role(user),
            comment="Ticket created (customer verified)",
            entered_at=timezone.now(),
            sla_minutes=sla_config.sla_minutes if sla_config else None,
            responsible_role=sla_config.responsible_role if sla_config else None,
        )

        return Response(
            TicketDetailSerializer(ticket).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# My Queue
# ---------------------------------------------------------------------------

class MyQueueView(APIView):
    """Tickets assigned to the current user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Ticket.objects.filter(
            current_assignee=request.user,
        ).exclude(
            current_status="closed",
        ).order_by("-updated_at")

        items_qs, meta = _paginate(qs, request)
        serializer = TicketListSerializer(items_qs, many=True)
        return Response({"items": serializer.data, **meta})


# ---------------------------------------------------------------------------
# Breached Tickets
# ---------------------------------------------------------------------------

class BreachedTicketsView(APIView):
    """Tickets with an active SLA breach on the current stage."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        role = get_user_role(user)
        profile = getattr(user, "userprofile", None)

        # Find tickets with open timeline entries that are breached
        now = timezone.now()

        # Get all open timeline entries
        open_entries = TicketTimeline.objects.filter(
            exited_at__isnull=True,
            sla_minutes__isnull=False,
        ).select_related("ticket")

        breached_ticket_ids = set()
        for entry in open_entries:
            elapsed = (now - entry.entered_at).total_seconds() / 60
            if elapsed > entry.sla_minutes:
                breached_ticket_ids.add(entry.ticket_id)

        if not breached_ticket_ids:
            return Response({"items": [], "total": 0, "page": 1, "per_page": 20, "pages": 1})

        qs = Ticket.objects.filter(pk__in=breached_ticket_ids)

        # Region scoping
        if role != "admin":
            if profile and profile.region:
                qs = qs.filter(region=profile.region)
            else:
                qs = qs.filter(
                    Q(created_by=user) | Q(current_assignee=user)
                )

        qs = qs.order_by("-updated_at")

        items_qs, meta = _paginate(qs, request)
        serializer = TicketListSerializer(items_qs, many=True)
        return Response({"items": serializer.data, **meta})
