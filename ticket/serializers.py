from django.contrib.auth.models import User
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from authenticate.models import Engineer
from .models import DelayRecord, Ticket, TicketTimeline
from .utils import get_sla_start_time


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_summary(user):
    """Return a compact dict for a User (used in nested representations)."""
    if user is None:
        return None
    profile = getattr(user, "userprofile", None)
    role = ""
    if profile:
        role = profile.role
    full_name = user.get_full_name() or user.username
    return {"id": user.pk, "full_name": full_name, "role": role}


def _engineer_summary(engineer):
    """Return a compact dict for an Engineer."""
    if engineer is None:
        return None
    return {
        "id": engineer.pk,
        "name": engineer.name,
        "phone": engineer.phone,
        "region": engineer.region,
        "region_display": engineer.get_region_display(),
        "status": engineer.status,
    }


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

class TimelineEntrySerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    class Meta:
        model = TicketTimeline
        fields = [
            "id",
            "from_status",
            "to_status",
            "actor",
            "actor_role",
            "comment",
            "metadata",
            "entered_at",
            "exited_at",
            "duration_minutes",
            "sla_minutes",
            "is_breached",
            "breach_minutes",
            "responsible_role",
            "created_at",
        ]

    def get_actor(self, obj):
        return _user_summary(obj.actor)


# ---------------------------------------------------------------------------
# Ticket — List (lightweight)
# ---------------------------------------------------------------------------

class TicketListSerializer(serializers.ModelSerializer):
    # Computed / annotated fields
    sla_health = serializers.SerializerMethodField()
    sla_remaining_mins = serializers.SerializerMethodField()
    current_stage_elapsed_mins = serializers.SerializerMethodField()
    total_delay_mins = serializers.SerializerMethodField()
    was_under_observation = serializers.SerializerMethodField()

    # Display helpers
    current_status_display = serializers.CharField(
        source="get_current_status_display", read_only=True,
    )
    service_type_display = serializers.CharField(
        source="get_service_type_display", read_only=True,
    )
    region_display = serializers.CharField(
        source="get_region_display", read_only=True,
    )

    # Nested user info
    current_assignee = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    assigned_engineer = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = [
            "id",
            "ticket_number",
            "form_number",
            "work_order",
            "cust_name",
            "cust_contact",
            "location",
            "product_name",
            "serial_number",
            "case_id",
            "brand",
            "service_type",
            "service_type_display",
            "priority",
            "current_status",
            "current_status_display",
            "region",
            "region_display",
            "requires_parts",
            "current_assignee",
            "assigned_engineer",
            "assigned_at",
            "created_by",
            "arrival_date",
            "target_completion",
            "closed_at",
            "cso_date",
            "created_at",
            "updated_at",
            # Computed
            "sla_health",
            "sla_remaining_mins",
            "current_stage_elapsed_mins",
            "total_delay_mins",
            "was_under_observation",
        ]

    # -- helpers for the current open timeline entry --

    def _current_timeline(self, obj):
        """Return the latest open timeline entry (cached on instance)."""
        cache_attr = "_cached_current_timeline"
        if not hasattr(obj, cache_attr):
            entry = (
                TicketTimeline.objects
                .filter(ticket=obj, exited_at__isnull=True)
                .order_by("-entered_at")
                .first()
            )
            setattr(obj, cache_attr, entry)
        return getattr(obj, cache_attr)

    def get_sla_health(self, obj):
        """
        Return one of: 'healthy', 'warning', 'breached', 'unknown'.
        """
        entry = self._current_timeline(obj)
        if entry is None or entry.sla_minutes is None:
            return "on_track"
        start_dt = get_sla_start_time(obj, entry)
        elapsed = (timezone.now() - start_dt).total_seconds() / 60
        if elapsed > entry.sla_minutes:
            return "breached"
        ratio = elapsed / entry.sla_minutes if entry.sla_minutes else 0
        if ratio >= 0.75:
            return "warning"
        return "on_track"

    def get_sla_remaining_mins(self, obj):
        entry = self._current_timeline(obj)
        if entry is None or entry.sla_minutes is None:
            return None
        start_dt = get_sla_start_time(obj, entry)
        elapsed = (timezone.now() - start_dt).total_seconds() / 60
        return max(0, int(entry.sla_minutes - elapsed))

    def get_current_stage_elapsed_mins(self, obj):
        entry = self._current_timeline(obj)
        if entry is None:
            return 0
        start_dt = get_sla_start_time(obj, entry)
        return int((timezone.now() - start_dt).total_seconds() / 60)

    def get_total_delay_mins(self, obj):
        result = DelayRecord.objects.filter(ticket=obj).aggregate(
            total=Sum("delay_minutes"),
        )
        return result["total"] or 0

    def get_current_assignee(self, obj):
        return _user_summary(obj.current_assignee)

    def get_created_by(self, obj):
        return _user_summary(obj.created_by)

    def get_assigned_engineer(self, obj):
        return _engineer_summary(obj.assigned_engineer)

    def get_was_under_observation(self, obj):
        return TicketTimeline.objects.filter(ticket=obj, to_status="under_observation").exists()


# ---------------------------------------------------------------------------
# Ticket — Detail (full, with timeline)
# ---------------------------------------------------------------------------

class TicketDetailSerializer(serializers.ModelSerializer):
    timeline = serializers.SerializerMethodField()
    delay_records = serializers.SerializerMethodField()
    current_assignee = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    assigned_engineer = serializers.SerializerMethodField()
    was_under_observation = serializers.SerializerMethodField()

    # Display helpers
    current_status_display = serializers.CharField(
        source="get_current_status_display", read_only=True,
    )
    service_type_display = serializers.CharField(
        source="get_service_type_display", read_only=True,
    )
    region_display = serializers.CharField(
        source="get_region_display", read_only=True,
    )
    priority_display = serializers.CharField(
        source="get_priority_display", read_only=True,
    )

    # Computed SLA fields
    sla_health = serializers.SerializerMethodField()
    sla_remaining_mins = serializers.SerializerMethodField()
    current_stage_elapsed_mins = serializers.SerializerMethodField()
    total_delay_mins = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = [
            "id",
            "ticket_number",
            "form_number",
            "work_order",
            # Customer
            "cust_name",
            "cust_contact",
            "cust_email",
            "cust_address",
            "location",
            # Product
            "product_name",
            "serial_number",
            "model_number",
            "brand",
            "case_id",
            "condition_received",
            # Service
            "service_type",
            "service_type_display",
            "priority",
            "priority_display",
            "issue_description",
            # Workflow
            "current_status",
            "current_status_display",
            "current_assignee",
            "assigned_engineer",
            "assigned_at",
            "requires_parts",
            # Parts
            "part_number",
            "part_usage",
            "failure_code",
            "part_description",
            "qty",
            "ct_code",
            "so_req_id",
            "removed_part_sno",
            "installed_part_sno",
            # Resolution
            "resolution_summary",
            "engineer_name",
            "hp_id",
            "explanation",
            "customer_comments",
            # Tracking
            "region",
            "region_display",
            "created_by",
            "otp_verified",
            "otp_verified_at",
            # Dates
            "cso_date",
            "arrival_date",
            "target_completion",
            "closed_at",
            "created_at",
            "updated_at",
            # Computed
            "sla_health",
            "sla_remaining_mins",
            "current_stage_elapsed_mins",
            "total_delay_mins",
            "was_under_observation",
            # Nested
            "timeline",
            "delay_records",
        ]

    def _current_timeline(self, obj):
        cache_attr = "_cached_current_timeline"
        if not hasattr(obj, cache_attr):
            entry = (
                TicketTimeline.objects
                .filter(ticket=obj, exited_at__isnull=True)
                .order_by("-entered_at")
                .first()
            )
            setattr(obj, cache_attr, entry)
        return getattr(obj, cache_attr)

    def get_sla_health(self, obj):
        entry = self._current_timeline(obj)
        if entry is None or entry.sla_minutes is None:
            return "on_track"
        start_dt = get_sla_start_time(obj, entry)
        elapsed = (timezone.now() - start_dt).total_seconds() / 60
        if elapsed > entry.sla_minutes:
            return "breached"
        ratio = elapsed / entry.sla_minutes if entry.sla_minutes else 0
        if ratio >= 0.75:
            return "warning"
        return "on_track"

    def get_sla_remaining_mins(self, obj):
        entry = self._current_timeline(obj)
        if entry is None or entry.sla_minutes is None:
            return None
        start_dt = get_sla_start_time(obj, entry)
        elapsed = (timezone.now() - start_dt).total_seconds() / 60
        return max(0, int(entry.sla_minutes - elapsed))

    def get_current_stage_elapsed_mins(self, obj):
        entry = self._current_timeline(obj)
        if entry is None:
            return 0
        start_dt = get_sla_start_time(obj, entry)
        return int((timezone.now() - start_dt).total_seconds() / 60)

    def get_total_delay_mins(self, obj):
        result = DelayRecord.objects.filter(ticket=obj).aggregate(
            total=Sum("delay_minutes"),
        )
        return result["total"] or 0

    def get_current_assignee(self, obj):
        return _user_summary(obj.current_assignee)

    def get_created_by(self, obj):
        return _user_summary(obj.created_by)

    def get_assigned_engineer(self, obj):
        return _engineer_summary(obj.assigned_engineer)

    def get_timeline(self, obj):
        entries = obj.timeline_entries.all().order_by("entered_at")
        return TimelineEntrySerializer(entries, many=True).data

    def get_delay_records(self, obj):
        records = obj.delay_records.all().order_by("-id")
        return DelayRecordSerializer(records, many=True).data

    def get_was_under_observation(self, obj):
        return TicketTimeline.objects.filter(ticket=obj, to_status="under_observation").exists()


class DelayRecordSerializer(serializers.ModelSerializer):
    responsible_user = serializers.SerializerMethodField()
    acknowledged_by = serializers.SerializerMethodField()

    class Meta:
        model = DelayRecord
        fields = [
            "id",
            "status",
            "responsible_role",
            "responsible_user",
            "sla_minutes",
            "actual_minutes",
            "delay_minutes",
            "delay_category",
            "reason",
            "acknowledged_by",
            "acknowledged_at",
        ]

    def get_responsible_user(self, obj):
        return _user_summary(obj.responsible_user)

    def get_acknowledged_by(self, obj):
        return _user_summary(obj.acknowledged_by)


# ---------------------------------------------------------------------------
# Ticket — Create
# ---------------------------------------------------------------------------

class TicketCreateSerializer(serializers.ModelSerializer):
    """Used by CSO to create a new ticket."""

    class Meta:
        model = Ticket
        fields = [
            "work_order",
            # Customer
            "cust_name",
            "cust_contact",
            "cust_email",
            "cust_address",
            "location",
            # Product
            "product_name",
            "serial_number",
            "model_number",
            "brand",
            "case_id",
            "condition_received",
            # Service
            "service_type",
            "priority",
            "issue_description",
            # Parts (optional at creation)
            "part_number",
            "part_usage",
            "failure_code",
            "part_description",
            "qty",
            "ct_code",
            "so_req_id",
            "removed_part_sno",
            "installed_part_sno",
            # Resolution (optional at creation)
            "resolution_summary",
            "engineer_name",
            "hp_id",
            "explanation",
            "customer_comments",
            # Dates
            "cso_date",
            "arrival_date",
            "target_completion",
            # Region (may be set automatically)
            "region",
        ]


# ---------------------------------------------------------------------------
# Ticket — Update
# ---------------------------------------------------------------------------

class TicketUpdateSerializer(serializers.ModelSerializer):
    """Partial update of non-workflow fields."""

    class Meta:
        model = Ticket
        fields = [
            # Customer
            "cust_name",
            "cust_contact",
            "cust_email",
            "cust_address",
            # Product
            "product_name",
            "serial_number",
            "model_number",
            "brand",
            "case_id",
            "condition_received",
            # Service
            "service_type",
            "priority",
            "issue_description",
            "requires_parts",
            # Parts
            "part_number",
            "part_usage",
            "failure_code",
            "part_description",
            "qty",
            "ct_code",
            "so_req_id",
            "removed_part_sno",
            "installed_part_sno",
            # Resolution
            "resolution_summary",
            "engineer_name",
            "hp_id",
            "explanation",
            "customer_comments",
            # Dates
            "cso_date",
            "arrival_date",
            "target_completion",
            # Region
            "region",
        ]


# ---------------------------------------------------------------------------
# Transition
# ---------------------------------------------------------------------------

class TransitionSerializer(serializers.Serializer):
    to_status = serializers.CharField(max_length=30)
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    assignee_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    engineer_id = serializers.IntegerField(required=False, allow_null=True, default=None)

    def validate_to_status(self, value):
        valid_statuses = [s[0] for s in Ticket.TICKET_STATUS_CHOICES]
        if value not in valid_statuses:
            raise serializers.ValidationError(f"'{value}' is not a valid status.")
        return value


# ---------------------------------------------------------------------------
# Available transitions
# ---------------------------------------------------------------------------

class AvailableTransitionSerializer(serializers.Serializer):
    to_status = serializers.CharField()
    label = serializers.CharField()
    requires_comment = serializers.BooleanField()
