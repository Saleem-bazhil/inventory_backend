"""Dashboard & analytics API views."""
import math
from collections import defaultdict

from django.contrib.auth.models import User
from django.db.models import Avg, Count, F, Q, Sum
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from authenticate.models import UserProfile
from .models import DelayRecord, Ticket, TicketTimeline


def _get_user_role(user):
    """Map user profile role to workflow role. sub_admin = regional admin."""
    profile = getattr(user, "userprofile", None)
    if not profile:
        return "admin"
    role_map = {
        "super_admin": "admin",
        "sub_admin": "sub_admin",
        "admin": "admin",
        "manager": "manager",
        "engineer": "engineer",
        "receptionist": "receptionist",
        "cc_team": "cc_team",
    }
    return role_map.get(profile.role, "admin")


# ---------------------------------------------------------------------------
# Dashboard Overview
# ---------------------------------------------------------------------------

class DashboardOverviewView(APIView):
    """
    GET /api/dashboard/overview/
    Returns: { overview: {...}, regions: [...] }
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        role = _get_user_role(user)
        profile = getattr(user, "userprofile", None)

        # Scope queryset
        if role == "admin":
            qs = Ticket.objects.all()
            # Admin can filter by specific region
            region_filter = request.query_params.get("region", "").strip()
            if region_filter:
                qs = qs.filter(region=region_filter)
        elif profile and profile.region:
            qs = Ticket.objects.filter(region=profile.region)
        else:
            qs = Ticket.objects.filter(Q(created_by=user) | Q(current_assignee=user))

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        total = qs.count()
        tickets_today = qs.filter(created_at__gte=today_start).count()
        closed_today = qs.filter(closed_at__gte=today_start).count()

        # Status breakdown
        by_status = {}
        for row in qs.values("current_status").annotate(count=Count("id")):
            by_status[row["current_status"]] = row["count"]

        # Priority breakdown
        by_priority = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for row in qs.values("priority").annotate(count=Count("id")):
            by_priority[row["priority"]] = row["count"]

        # SLA breaches (open timeline entries past SLA)
        open_entries = TicketTimeline.objects.filter(
            ticket__in=qs,
            exited_at__isnull=True,
            sla_minutes__isnull=False,
        )
        breached_count = 0
        warning_count = 0
        for entry in open_entries:
            elapsed = (now - entry.entered_at).total_seconds() / 60
            if elapsed > entry.sla_minutes:
                breached_count += 1
            elif elapsed > entry.sla_minutes * 0.75:
                warning_count += 1

        # Average resolution time (closed tickets)
        closed = qs.filter(closed_at__isnull=False, created_at__isnull=False)
        if closed.exists():
            total_hours = sum(
                (t.closed_at - t.created_at).total_seconds() / 3600
                for t in closed[:100]  # limit for performance
            )
            avg_resolution_hrs = round(total_hours / min(closed.count(), 100), 1)
        else:
            avg_resolution_hrs = 0.0

        # Specific workflow counts (overall)
        assigned_count = qs.filter(assigned_engineer__isnull=False).exclude(current_status="closed").count()
        unassigned_count = qs.filter(assigned_engineer__isnull=True).exclude(current_status="closed").count()
        in_progress_count = by_status.get("in_progress", 0) + by_status.get("diagnosis", 0) + by_status.get("assigned", 0)
        part_pending_count = by_status.get("part_requested", 0)
        part_order_pending_count = by_status.get("cx_approved", 0) + by_status.get("part_ordered", 0)
        part_quote_pending_count = by_status.get("part_approved", 0) + by_status.get("quotation_sent", 0)
        ready_to_dispatch_count = by_status.get("ready_for_delivery", 0)
        cx_pending_count = by_status.get("cx_pending", 0)
        completed_count = by_status.get("closed", 0)

        # Warranty breakdown (overall — includes all tickets, not just open)
        warranty_count = qs.filter(service_type="warranty").count()
        out_of_warranty_count = qs.exclude(service_type="warranty").count()

        # Today's breakdown
        today_qs = qs.filter(created_at__gte=today_start)
        today_warranty = today_qs.filter(service_type="warranty").count()
        today_out_of_warranty = today_qs.exclude(service_type="warranty").count()
        today_assigned = today_qs.filter(assigned_engineer__isnull=False).exclude(current_status="closed").count()
        today_unassigned = today_qs.filter(assigned_engineer__isnull=True).exclude(current_status="closed").count()

        today_by_status = {}
        for row in today_qs.values("current_status").annotate(count=Count("id")):
            today_by_status[row["current_status"]] = row["count"]

        today_part_pending = today_by_status.get("part_requested", 0)
        today_part_order_pending = today_by_status.get("cx_approved", 0) + today_by_status.get("part_ordered", 0)
        today_part_quote_pending = today_by_status.get("part_approved", 0) + today_by_status.get("quotation_sent", 0)
        today_cx_pending = today_by_status.get("cx_pending", 0)

        overview = {
            "total_tickets": total,
            "by_status": by_status,
            "by_priority": by_priority,
            "breached_count": breached_count,
            "warning_count": warning_count,
            "avg_resolution_hrs": avg_resolution_hrs,
            "tickets_today": tickets_today,
            "closed_today": closed_today,
            # Overall KPI counts
            "assigned_count": assigned_count,
            "unassigned_count": unassigned_count,
            "in_progress_count": in_progress_count,
            "part_pending_count": part_pending_count,
            "part_order_pending_count": part_order_pending_count,
            "part_quote_pending_count": part_quote_pending_count,
            "ready_to_dispatch_count": ready_to_dispatch_count,
            "cx_pending_count": cx_pending_count,
            "completed_count": completed_count,
            "warranty_count": warranty_count,
            "out_of_warranty_count": out_of_warranty_count,
            # Today's KPI counts
            "today_warranty": today_warranty,
            "today_out_of_warranty": today_out_of_warranty,
            "today_assigned": today_assigned,
            "today_unassigned": today_unassigned,
            "today_part_pending": today_part_pending,
            "today_part_order_pending": today_part_order_pending,
            "today_part_quote_pending": today_part_quote_pending,
            "today_cx_pending": today_cx_pending,
        }

        # Region breakdown (admin only)
        regions = []
        if role == "admin":
            for code, label in UserProfile.REGION_CHOICES:
                region_qs = Ticket.objects.filter(region=code)
                region_total = region_qs.count()
                open_tickets = region_qs.exclude(current_status="closed").count()
                region_breached = DelayRecord.objects.filter(
                    ticket__region=code,
                ).count()
                regions.append({
                    "region": code,
                    "total_tickets": region_total,
                    "open_tickets": open_tickets,
                    "breached": region_breached,
                    "avg_resolution_hrs": 0,
                })

        return Response({"overview": overview, "regions": regions})


# ---------------------------------------------------------------------------
# SLA Breaches
# ---------------------------------------------------------------------------

class SLABreachesView(APIView):
    """
    GET /api/dashboard/sla-breaches/
    Returns list of currently breached tickets with details.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        open_entries = TicketTimeline.objects.filter(
            exited_at__isnull=True,
            sla_minutes__isnull=False,
        ).select_related("ticket", "ticket__current_assignee")

        result = []
        for entry in open_entries:
            elapsed = (now - entry.entered_at).total_seconds() / 60
            if elapsed > entry.sla_minutes:
                assignee = entry.ticket.current_assignee
                result.append({
                    "id": f"breach-{entry.id}",
                    "ticket_id": entry.ticket_id,
                    "ticket_number": entry.ticket.ticket_number,
                    "current_status": entry.to_status,
                    "responsible_role": entry.responsible_role or "",
                    "responsible_user": (
                        assignee.get_full_name() or assignee.username
                    ) if assignee else None,
                    "delay_minutes": round(elapsed - entry.sla_minutes),
                    "entered_at": entry.entered_at.isoformat(),
                    "sla_minutes": entry.sla_minutes,
                })

        result.sort(key=lambda x: x["delay_minutes"], reverse=True)
        return Response(result)


# ---------------------------------------------------------------------------
# Delay Heatmap
# ---------------------------------------------------------------------------

class DelayHeatmapView(APIView):
    """
    GET /api/dashboard/delay-heatmap/?period=30d
    Returns delay data grouped by role x status.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        period = request.query_params.get("period", "30d")
        days = {"7d": 7, "30d": 30, "90d": 90}.get(period, 30)
        since = timezone.now() - timezone.timedelta(days=days)

        delays = DelayRecord.objects.filter(
            Q(created_at__gte=since) | Q(created_at__isnull=True)
        )

        # Group by role + status
        heatmap = defaultdict(lambda: {
            "avg_delay_mins": 0,
            "breach_count": 0,
            "total_tickets": 0,
            "severe_count": 0,
        })

        for d in delays:
            key = (d.responsible_role, d.status)
            cell = heatmap[key]
            cell["breach_count"] += 1
            cell["total_tickets"] += 1
            cell["avg_delay_mins"] += d.delay_minutes
            if d.delay_category == "severe":
                cell["severe_count"] += 1

        result = []
        for (role, stat), cell in heatmap.items():
            if cell["breach_count"] > 0:
                cell["avg_delay_mins"] = round(cell["avg_delay_mins"] / cell["breach_count"])
            result.append({
                "role": role,
                "status": stat,
                **cell,
            })

        return Response(result)


# ---------------------------------------------------------------------------
# Engineer Performance
# ---------------------------------------------------------------------------

class EngineerPerformanceView(APIView):
    """
    GET /api/dashboard/engineer-performance/
    Returns per-engineer metrics.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Get all users with engineer role
        engineers = UserProfile.objects.filter(
            role__in=["engineer", "sub_admin"]
        ).select_related("user")

        result = []
        for profile in engineers:
            user = profile.user
            assigned = Ticket.objects.filter(current_assignee=user).count()
            completed = Ticket.objects.filter(
                current_assignee=user,
                current_status="closed",
            ).count()
            in_progress = Ticket.objects.filter(
                current_assignee=user,
            ).exclude(
                current_status__in=["closed", "cso_created"]
            ).count()

            # Average resolution hours
            closed_tickets = Ticket.objects.filter(
                current_assignee=user,
                current_status="closed",
                closed_at__isnull=False,
            )
            if closed_tickets.exists():
                total_hrs = sum(
                    (t.closed_at - t.created_at).total_seconds() / 3600
                    for t in closed_tickets[:50]
                )
                avg_hrs = round(total_hrs / min(closed_tickets.count(), 50), 1)
            else:
                avg_hrs = 0.0

            # Delay data
            delays = DelayRecord.objects.filter(responsible_user=user)
            breach_count = delays.count()
            total_delay = delays.aggregate(s=Sum("delay_minutes"))["s"] or 0

            # SLA compliance
            timeline_entries = TicketTimeline.objects.filter(
                actor=user,
                exited_at__isnull=False,
                sla_minutes__isnull=False,
            )
            total_entries = timeline_entries.count()
            breached_entries = timeline_entries.filter(is_breached=True).count()
            compliance = round(
                ((total_entries - breached_entries) / total_entries * 100)
                if total_entries > 0 else 100,
                1,
            )

            result.append({
                "engineer_id": user.id,
                "name": user.get_full_name() or user.username,
                "assigned": assigned,
                "completed": completed,
                "in_progress": in_progress,
                "avg_resolution_hrs": avg_hrs,
                "sla_compliance_pct": compliance,
                "total_delay_mins": total_delay,
                "breach_count": breach_count,
            })

        result.sort(key=lambda x: x["sla_compliance_pct"], reverse=True)
        return Response(result)


# ---------------------------------------------------------------------------
# Manager Approval Metrics
# ---------------------------------------------------------------------------

class ManagerApprovalView(APIView):
    """GET /api/dashboard/manager-approvals/"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        managers = UserProfile.objects.filter(
            role__in=["manager", "super_admin", "admin"]
        ).select_related("user")

        result = []
        for profile in managers:
            user = profile.user
            approvals = TicketTimeline.objects.filter(
                actor=user,
                to_status__in=["assigned", "part_approved", "cx_approved", "part_ordered"],
                exited_at__isnull=False,
            )
            total_approvals = approvals.count()
            avg_mins = 0
            if total_approvals:
                total_duration = sum(
                    (e.exited_at - e.entered_at).total_seconds() / 60
                    for e in approvals[:50]
                )
                avg_mins = round(total_duration / min(total_approvals, 50))

            pending = TicketTimeline.objects.filter(
                responsible_role__in=["manager", "admin"],
                exited_at__isnull=True,
            ).count()

            breach_count = DelayRecord.objects.filter(
                responsible_user=user,
            ).count()

            result.append({
                "manager_id": user.id,
                "name": user.get_full_name() or user.username,
                "avg_approval_mins": avg_mins,
                "pending_count": pending,
                "approved_count": total_approvals,
                "breach_count": breach_count,
            })

        return Response(result)


# ---------------------------------------------------------------------------
# Ticket Aging
# ---------------------------------------------------------------------------

class TicketAgingView(APIView):
    """GET /api/dashboard/ticket-aging/"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        open_tickets = Ticket.objects.exclude(current_status="closed")

        buckets = [
            ("0-4h", 0, 240),
            ("4-8h", 240, 480),
            ("8-24h", 480, 1440),
            ("1-2d", 1440, 2880),
            ("2-5d", 2880, 7200),
            ("5d+", 7200, float("inf")),
        ]

        result = []
        for label, low, high in buckets:
            count = 0
            breached = 0
            for t in open_tickets:
                age_mins = (now - t.created_at).total_seconds() / 60
                if low <= age_mins < high:
                    count += 1
                    # Check if currently breached
                    entry = TicketTimeline.objects.filter(
                        ticket=t, exited_at__isnull=True, sla_minutes__isnull=False,
                    ).first()
                    if entry:
                        elapsed = (now - entry.entered_at).total_seconds() / 60
                        if elapsed > entry.sla_minutes:
                            breached += 1
            result.append({
                "range": label,
                "count": count,
                "breached": breached,
            })

        return Response(result)


# ---------------------------------------------------------------------------
# Region Comparison
# ---------------------------------------------------------------------------

class RegionComparisonView(APIView):
    """GET /api/dashboard/region-comparison/"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        result = []
        for code, label in UserProfile.REGION_CHOICES:
            qs = Ticket.objects.filter(region=code)
            total = qs.count()
            open_count = qs.exclude(current_status="closed").count()
            breached = DelayRecord.objects.filter(ticket__region=code).count()

            closed = qs.filter(closed_at__isnull=False)
            if closed.exists():
                total_hrs = sum(
                    (t.closed_at - t.created_at).total_seconds() / 3600
                    for t in closed[:50]
                )
                avg_hrs = round(total_hrs / min(closed.count(), 50), 1)
            else:
                avg_hrs = 0.0

            result.append({
                "region": code,
                "total_tickets": total,
                "open_tickets": open_count,
                "breached": breached,
                "avg_resolution_hrs": avg_hrs,
            })

        return Response(result)
