from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from authenticate.models import Engineer


class Ticket(models.Model):
    """Main service record — replaces MaterialTrack."""

    # --- Status choices ---
    TICKET_STATUS_CHOICES = (
        ("cso_created", "CSO Created"),
        ("assigned", "Assigned"),
        ("diagnosis", "Diagnosis"),
        ("part_requested", "Part Requested"),
        ("part_approved", "Part Approved"),
        ("quotation_sent", "Quotation Sent"),
        ("cx_pending", "Customer Pending"),
        ("cx_approved", "Customer Approved"),
        ("cx_rejected", "Customer Rejected"),
        ("part_ordered", "Part Ordered"),
        ("part_received", "Part Received"),
        ("in_progress", "In Progress"),
        ("ready_for_delivery", "Ready for Delivery"),
        ("closed", "Closed"),
        ("under_observation", "Under Observation"),
    )

    # --- Service type choices ---
    SERVICE_TYPE_CHOICES = (
        ("warranty", "Warranty"),
        ("non_warranty", "Non Warranty"),
        ("doc", "DOC"),
        ("amc", "AMC"),
        ("rental", "Rental"),
    )

    # --- Priority choices ---
    PRIORITY_CHOICES = (
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    )

    # --- Region choices ---
    REGION_CHOICES = (
        ("vellore", "Vellore"),
        ("salem", "Salem"),
        ("chennai", "Chennai"),
        ("kanchipuram", "Kanchipuram"),
        ("hosur", "Hosur"),
    )

    # --- Ticket identifier ---
    ticket_number = models.CharField(
        max_length=30, unique=True, blank=True,
        verbose_name="Ticket Number",
    )

    # --- Work Order ---
    work_order = models.CharField(max_length=100, verbose_name="Work Order", blank=True, default="")

    # --- Customer information ---
    cust_name = models.CharField(max_length=255, verbose_name="Customer Name", blank=True, default="")
    cust_contact = models.CharField(max_length=100, verbose_name="Contact Number", blank=True, null=True)
    cust_email = models.EmailField(verbose_name="Customer Email", blank=True, null=True)
    cust_address = models.TextField(verbose_name="Customer Address", blank=True, null=True)
    location = models.CharField(max_length=255, verbose_name="Location", blank=True, default="")

    # --- Product information ---
    product_name = models.CharField(max_length=200, verbose_name="Product Name", blank=True, default="")
    serial_number = models.CharField(max_length=100, verbose_name="Serial Number", blank=True, null=True)
    model_number = models.CharField(max_length=100, verbose_name="Model Number", blank=True, null=True)
    brand = models.CharField(max_length=100, verbose_name="Brand", blank=True, null=True)
    case_id = models.CharField(max_length=100, verbose_name="Case ID", unique=True, blank=True, default="")
    condition_received = models.TextField(verbose_name="Condition Received", blank=True, null=True)

    # --- Service details ---
    service_type = models.CharField(
        max_length=20, choices=SERVICE_TYPE_CHOICES, default="warranty",
        verbose_name="Service Type",
    )
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default="medium",
        verbose_name="Priority",
    )
    issue_description = models.TextField(verbose_name="Issue Description", blank=True, null=True)

    # --- Workflow state ---
    current_status = models.CharField(
        max_length=30, choices=TICKET_STATUS_CHOICES, default="cso_created",
        verbose_name="Current Status",
    )
    current_assignee = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_tickets", verbose_name="Current Assignee",
    )
    requires_parts = models.BooleanField(default=False, verbose_name="Requires Parts")

    # --- Assigned engineer (separate entity) ---
    assigned_engineer = models.ForeignKey(
        Engineer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_tickets", verbose_name="Assigned Engineer",
    )
    assigned_at = models.DateTimeField(null=True, blank=True, verbose_name="Assigned At")

    # --- Part details ---
    part_number = models.CharField(max_length=100, verbose_name="Product/Part No.", blank=True, null=True)
    part_usage = models.CharField(max_length=200, verbose_name="Part Usage", blank=True, null=True)
    failure_code = models.CharField(max_length=100, verbose_name="Failure Code", blank=True, null=True)
    part_description = models.TextField(verbose_name="Part Description", blank=True, null=True)
    qty = models.IntegerField(default=1, verbose_name="Qty")
    ct_code = models.CharField(max_length=100, verbose_name="CT Code", blank=True, null=True)
    so_req_id = models.CharField(max_length=100, verbose_name="So. No./Req ID", blank=True, null=True)
    removed_part_sno = models.CharField(max_length=100, verbose_name="Removed Part S.No.", blank=True, null=True)
    installed_part_sno = models.CharField(max_length=100, verbose_name="Installed Part S.No.", blank=True, null=True)

    # --- Resolution & Engineer ---
    resolution_summary = models.TextField(verbose_name="Resolution Summary", blank=True, null=True)
    engineer_name = models.CharField(max_length=200, verbose_name="Engineer Name", blank=True, null=True)
    hp_id = models.CharField(max_length=100, verbose_name="HP ID", blank=True, null=True)
    explanation = models.TextField(verbose_name="Explanation", blank=True, null=True)
    customer_comments = models.TextField(verbose_name="Customer Comments", blank=True, null=True)

    # --- Tracking ---
    region = models.CharField(
        max_length=20, choices=REGION_CHOICES, blank=True, null=True,
        verbose_name="Region",
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_tickets", verbose_name="Created By",
    )
    otp_verified = models.BooleanField(default=False, verbose_name="OTP Verified")
    otp_verified_at = models.DateTimeField(null=True, blank=True, verbose_name="OTP Verified At")

    # --- Dates ---
    arrival_date = models.DateField(verbose_name="Arrival Date", blank=True, null=True)
    target_completion = models.DateField(verbose_name="Target Completion", blank=True, null=True)
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="Closed At")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ticket"
        verbose_name_plural = "Tickets"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ticket_number} - {self.cust_name} ({self.product_name})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        # Need to save first to get the pk for ticket_number generation
        if is_new and not self.ticket_number:
            # Save once to obtain the auto-generated pk
            super().save(*args, **kwargs)
            from django.utils import timezone
            year = self.created_at.year if self.created_at else timezone.now().year
            self.ticket_number = f"TKT-{year}-{self.pk:06d}"
            # Auto-generate case_id if not provided
            if not self.case_id:
                self.case_id = f"CSO-{year}-{self.pk:06d}"
            Ticket.objects.filter(pk=self.pk).update(
                ticket_number=self.ticket_number,
                case_id=self.case_id,
            )
        else:
            super().save(*args, **kwargs)


class TicketTimeline(models.Model):
    """Audit log entry for every status change on a ticket."""

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="timeline_entries",
    )
    from_status = models.CharField(max_length=30, null=True, blank=True)
    to_status = models.CharField(max_length=30)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="timeline_actions",
    )
    actor_role = models.CharField(max_length=30, blank=True, default="")
    comment = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    # Timing
    entered_at = models.DateTimeField()
    exited_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(null=True, blank=True)

    # SLA tracking
    sla_minutes = models.IntegerField(null=True, blank=True)
    is_breached = models.BooleanField(default=False)
    breach_minutes = models.IntegerField(default=0)
    responsible_role = models.CharField(max_length=30, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ticket Timeline Entry"
        verbose_name_plural = "Ticket Timeline Entries"
        ordering = ["entered_at"]

    def __str__(self):
        return f"{self.ticket.ticket_number}: {self.from_status} -> {self.to_status}"


class SLAConfig(models.Model):
    """SLA rules per status, optionally scoped by service_type and priority."""

    status = models.CharField(max_length=30)
    service_type = models.CharField(max_length=20, null=True, blank=True)
    priority = models.CharField(max_length=10, null=True, blank=True)
    sla_minutes = models.IntegerField()
    responsible_role = models.CharField(max_length=30)
    warning_at_percent = models.IntegerField(default=75)
    escalation_after_mins = models.IntegerField(null=True, blank=True)
    escalation_to_role = models.CharField(max_length=30, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "SLA Configuration"
        verbose_name_plural = "SLA Configurations"
        unique_together = ("status", "service_type", "priority")

    def __str__(self):
        parts = [self.status]
        if self.service_type:
            parts.append(self.service_type)
        if self.priority:
            parts.append(self.priority)
        return f"SLA: {' / '.join(parts)} ({self.sla_minutes} min)"


class DelayRecord(models.Model):
    """Materialized breach data for a ticket timeline entry."""

    DELAY_CATEGORY_CHOICES = (
        ("minor", "Minor"),
        ("moderate", "Moderate"),
        ("severe", "Severe"),
    )

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="delay_records",
    )
    timeline_entry = models.ForeignKey(
        TicketTimeline, on_delete=models.CASCADE, related_name="delay_records",
    )
    status = models.CharField(max_length=30)
    responsible_role = models.CharField(max_length=30)
    responsible_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="delay_records",
    )
    sla_minutes = models.IntegerField()
    actual_minutes = models.IntegerField()
    delay_minutes = models.IntegerField()
    delay_category = models.CharField(max_length=10, choices=DELAY_CATEGORY_CHOICES)
    reason = models.TextField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="acknowledged_delays",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = "Delay Record"
        verbose_name_plural = "Delay Records"
        ordering = ["-id"]

    def __str__(self):
        return (
            f"Delay on {self.ticket.ticket_number} @ {self.status}: "
            f"+{self.delay_minutes} min ({self.delay_category})"
        )
