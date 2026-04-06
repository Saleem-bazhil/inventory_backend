from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

from authenticate.models import UserProfile


class OTPVerification(models.Model):
    """Stores OTPs in the database so they work across multiple server workers."""
    phone = models.CharField(max_length=15, db_index=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = "OTP Verification"

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"OTP for {self.phone}"


class MaterialTrack(models.Model):
    # --- Service Type Choices ---
    WARRANTY = "warranty"
    NON_WARRANTY = "non_warranty"
    DOC = "doc"
    AMC = "amc"
    RENTAL = "rental"
    SERVICE_TYPE_CHOICES = (
        (WARRANTY, "Warranty"),
        (NON_WARRANTY, "Non Warranty"),
        (DOC, "DOC"),
        (AMC, "AMC"),
        (RENTAL, "Rental"),
    )

    # --- Call Status Choices ---
    PENDING = "pending"
    CLOSED = "closed"
    TAKEN_FOR_SERVICE = "taken_for_service"
    CALL_STATUS_CHOICES = (
        (PENDING, "Pending"),
        (CLOSED, "Closed"),
        (TAKEN_FOR_SERVICE, "Taken for Service"),
    )

    # --- Region FK (links to the sub-admin who created it) ---
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="materials")
    region = models.CharField(
        max_length=20, choices=UserProfile.REGION_CHOICES,
        blank=True, null=True,
        help_text="Auto-set from the sub-admin's region on create.",
    )

    # --- Customer Information ---
    cust_name = models.CharField(max_length=255, verbose_name="Customer Name", default="")
    cust_contact = models.CharField(max_length=100, verbose_name="Contact Number", blank=True, null=True)
    cust_address = models.TextField(verbose_name="Customer Address", blank=True, null=True)

    # --- Service Details ---
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPE_CHOICES, default=WARRANTY, verbose_name="Service Type")
    product_name = models.CharField(max_length=200, verbose_name="Product Name", default="")
    serial_number = models.CharField(max_length=100, verbose_name="Serial Number", blank=True, null=True)
    case_id = models.CharField(max_length=100, verbose_name="Case ID", unique=True, default="")
    condition_received = models.TextField(verbose_name="Condition Received", blank=True, null=True)
    arrival_date = models.DateField(verbose_name="Arrival Date", blank=True, null=True)
    delivery_date = models.DateField(verbose_name="Delivery Date", blank=True, null=True)

    # --- Issue Description ---
    issue_description = models.TextField(verbose_name="Issue Description", blank=True, null=True)

    # --- Part Details ---
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
    call_status = models.CharField(max_length=20, choices=CALL_STATUS_CHOICES, default=PENDING, verbose_name="Call Status")
    explanation = models.TextField(verbose_name="Explanation", blank=True, null=True)
    customer_comments = models.TextField(verbose_name="Customer Comments", blank=True, null=True)

    # --- Timestamps ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Material Tracking Record"
        verbose_name_plural = "Material Tracking Records"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.case_id} - {self.cust_name} ({self.product_name})"
