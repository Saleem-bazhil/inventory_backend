from django.contrib.auth.models import User
from django.db import models

from authenticate.models import UserProfile

REGION_CHOICES = UserProfile.REGION_CHOICES


# =============================================================================
# Buffer Stock Item — Region-wise OEM spare part inventory
# =============================================================================

class BufferStockItem(models.Model):
    CATEGORY_CHOICES = [
        ("print_head", "Print Head"),
        ("toner", "Toner Cartridge"),
        ("fuser", "Fuser Unit"),
        ("drum", "Drum Unit"),
        ("formatter", "Formatter Board"),
        ("scanner", "Scanner Assembly"),
        ("adf", "ADF Assembly"),
        ("roller", "Roller Kit"),
        ("power_supply", "Power Supply"),
        ("other", "Other"),
    ]

    part_number = models.CharField(max_length=100)
    part_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    category = models.CharField(
        max_length=30, choices=CATEGORY_CHOICES, default="other",
    )
    brand = models.CharField(max_length=100, default="HP")
    region = models.CharField(max_length=20, choices=REGION_CHOICES)
    qty_on_hand = models.IntegerField(default=0)
    qty_reserved = models.IntegerField(default=0)
    qty_in_transit = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=2)
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    storage_location = models.CharField(max_length=100, blank=True, default="")
    provided_by = models.CharField(max_length=100, default="HP")
    last_replenished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["region", "part_number"]
        unique_together = [("part_number", "region")]
        verbose_name = "Buffer Stock Item"

    @property
    def qty_available(self):
        return self.qty_on_hand - self.qty_reserved

    def __str__(self):
        return f"{self.part_number} — {self.part_name} [{self.region}] (Avail: {self.qty_available})"


# =============================================================================
# Buffer Case — Service case lifecycle (IW / OOW)
# =============================================================================

class BufferCase(models.Model):
    CASE_TYPE_CHOICES = [
        ("iw", "In-Warranty"),
        ("oow", "Out-of-Warranty"),
    ]

    STATUS_CHOICES = [
        ("created", "Created"),
        ("pending_approval", "Pending Approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("part_allocated", "Part Allocated"),
        ("transfer_requested", "Transfer Requested"),
        ("engineer_assigned", "Engineer Assigned"),
        ("in_progress", "In Progress"),
        ("service_completed", "Service Completed"),
        ("pending_replenishment", "Pending Replenishment"),
        ("replenishment_ordered", "Replenishment Ordered"),
        ("stock_replenished", "Stock Replenished"),
        ("closed", "Closed"),
        ("cancelled", "Cancelled"),
    ]

    # Auto-generated case number
    case_number = models.CharField(max_length=20, unique=True, editable=False)

    # HP case ID — required for IW, optional for OOW
    case_id = models.CharField(
        max_length=100, blank=True, default="",
        help_text="HP Case ID. Required for in-warranty cases.",
    )
    case_type = models.CharField(max_length=5, choices=CASE_TYPE_CHOICES)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="created")
    region = models.CharField(max_length=20, choices=REGION_CHOICES)

    # Customer
    customer_name = models.CharField(max_length=255)
    customer_contact = models.CharField(max_length=50, blank=True, default="")
    customer_email = models.CharField(max_length=255, blank=True, default="")
    customer_address = models.TextField(blank=True, default="")

    # Product
    product_name = models.CharField(max_length=255, blank=True, default="")
    serial_number = models.CharField(max_length=100, blank=True, default="")
    model_number = models.CharField(max_length=100, blank=True, default="")

    # Part usage
    buffer_stock_item = models.ForeignKey(
        BufferStockItem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="cases",
    )
    part_number = models.CharField(max_length=100, blank=True, default="")
    part_name = models.CharField(max_length=255, blank=True, default="")
    qty_used = models.IntegerField(default=1)
    source_region = models.CharField(
        max_length=20, choices=REGION_CHOICES, blank=True, default="",
        help_text="Region the part was sourced from (may differ if transferred).",
    )

    # Engineer (non-login entity)
    assigned_engineer = models.ForeignKey(
        "authenticate.Engineer", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="buffer_cases",
    )

    # Resolution
    resolution_summary = models.TextField(blank=True, default="")
    service_notes = models.TextField(blank=True, default="")
    proof_uploaded = models.BooleanField(default=False)

    # OOW Approval (denormalized for quick access; canonical data in OOWApproval)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_buffer_cases",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Tracking
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_buffer_cases",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Buffer Case"

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)
            self.case_number = f"BC-{self.created_at.year}-{self.pk:05d}"
            super().save(update_fields=["case_number"])
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.case_number} [{self.get_case_type_display()}] — {self.customer_name}"


# =============================================================================
# OOW Approval — Mandatory audit record for out-of-warranty approvals
# =============================================================================

class OOWApproval(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    buffer_case = models.OneToOneField(
        BufferCase, on_delete=models.CASCADE, related_name="oow_approval",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    requested_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="oow_requests",
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="oow_approvals",
    )
    approver_role = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Role of the approver at the time of action.",
    )
    reason = models.TextField(blank=True, default="")
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        verbose_name = "OOW Approval"

    def __str__(self):
        return f"OOW {self.status} — {self.buffer_case.case_number}"


# =============================================================================
# Inter-Region Transfer — Part movement between regions
# =============================================================================

class InterRegionTransfer(models.Model):
    STATUS_CHOICES = [
        ("requested", "Requested"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("in_transit", "In Transit"),
        ("received", "Received"),
        ("cancelled", "Cancelled"),
    ]

    transfer_number = models.CharField(max_length=20, unique=True, editable=False)

    buffer_stock_item = models.ForeignKey(
        BufferStockItem, on_delete=models.CASCADE, related_name="transfers_out",
    )
    part_number = models.CharField(max_length=100)
    part_name = models.CharField(max_length=255)
    quantity = models.IntegerField()

    source_region = models.CharField(max_length=20, choices=REGION_CHOICES)
    destination_region = models.CharField(max_length=20, choices=REGION_CHOICES)

    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="requested")

    related_case = models.ForeignKey(
        BufferCase, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transfers",
    )

    requested_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="transfer_requests",
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transfer_approvals",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")

    received_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transfer_receipts",
    )
    received_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Inter-Region Transfer"

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)
            self.transfer_number = f"TRF-{self.created_at.year}-{self.pk:05d}"
            super().save(update_fields=["transfer_number"])
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.transfer_number}: {self.part_number} x{self.quantity} "
            f"{self.source_region} → {self.destination_region}"
        )


# =============================================================================
# Replenishment Order — Triggered after service to replenish buffer from HP
# =============================================================================

class ReplenishmentOrder(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("ordered", "Ordered"),
        ("shipped", "Shipped"),
        ("received", "Received"),
        ("cancelled", "Cancelled"),
    ]

    order_number = models.CharField(max_length=20, unique=True, editable=False)

    buffer_case = models.OneToOneField(
        BufferCase, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="replenishment_order",
    )
    buffer_stock_item = models.ForeignKey(
        BufferStockItem, on_delete=models.CASCADE, related_name="replenishment_orders",
    )

    part_number = models.CharField(max_length=100)
    part_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    region = models.CharField(max_length=20, choices=REGION_CHOICES)

    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="pending")

    ordered_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="replenishment_orders",
    )
    received_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="replenishment_receipts",
    )

    order_date = models.DateField(null=True, blank=True)
    expected_delivery = models.DateField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Replenishment Order"

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)
            self.order_number = f"RPL-{self.created_at.year}-{self.pk:05d}"
            super().save(update_fields=["order_number"])
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_number} — {self.part_number} x{self.quantity} [{self.region}]"


# =============================================================================
# Case Proof — Uploaded evidence of service completion
# =============================================================================

class CaseProof(models.Model):
    PROOF_TYPE_CHOICES = [
        ("image", "Image"),
        ("video", "Video"),
        ("document", "Document"),
    ]

    buffer_case = models.ForeignKey(
        BufferCase, on_delete=models.CASCADE, related_name="proofs",
    )
    proof_type = models.CharField(max_length=10, choices=PROOF_TYPE_CHOICES, default="image")
    file = models.FileField(upload_to="buffer_proofs/%Y/%m/")
    description = models.CharField(max_length=255, blank=True, default="")
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Case Proof"

    def __str__(self):
        return f"Proof ({self.proof_type}) — {self.buffer_case.case_number}"


# =============================================================================
# Buffer Audit Log — Complete trail for every significant action
# =============================================================================

class BufferAuditLog(models.Model):
    ACTION_CHOICES = [
        ("stock_created", "Stock Created"),
        ("stock_updated", "Stock Updated"),
        ("stock_adjusted", "Stock Adjusted"),
        ("case_created", "Case Created"),
        ("case_status_changed", "Case Status Changed"),
        ("case_closed", "Case Closed"),
        ("oow_requested", "OOW Approval Requested"),
        ("oow_approved", "OOW Approved"),
        ("oow_rejected", "OOW Rejected"),
        ("transfer_requested", "Transfer Requested"),
        ("transfer_approved", "Transfer Approved"),
        ("transfer_rejected", "Transfer Rejected"),
        ("transfer_received", "Transfer Received"),
        ("replenishment_created", "Replenishment Created"),
        ("replenishment_received", "Replenishment Received"),
        ("proof_uploaded", "Proof Uploaded"),
        ("part_allocated", "Part Allocated"),
        ("part_released", "Part Released"),
    ]

    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    entity_type = models.CharField(max_length=30)
    entity_id = models.IntegerField()
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    details = models.JSONField(default=dict, blank=True)
    region = models.CharField(max_length=20, choices=REGION_CHOICES, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Buffer Audit Log"

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.action} — {self.entity_type}#{self.entity_id}"
