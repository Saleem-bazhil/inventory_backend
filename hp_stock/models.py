from django.contrib.auth.models import User
from django.db import models

class HPStockItem(models.Model):
    case_id = models.CharField(max_length=100, blank=True, default="", verbose_name="Case ID")
    work_order_id = models.CharField(max_length=100, blank=True, default="", verbose_name="Work Order ID")
    delivery_no = models.CharField(max_length=100, blank=True, default="", verbose_name="Delivery No")
    service_event_no = models.CharField(max_length=100, blank=True, default="", verbose_name="Service Event No")
    material_order_no = models.CharField(max_length=100, blank=True, default="", verbose_name="Material Order No")
    hp_sales_order_no = models.CharField(max_length=100, blank=True, default="", verbose_name="HP Sales Order No")
    gvrma_no = models.CharField(max_length=100, blank=True, default="", verbose_name="GVRMA No")
    good_part_number = models.CharField(max_length=100, blank=True, default="", verbose_name="Good Part Number")
    part_order_number = models.CharField(max_length=100, blank=True, default="", verbose_name="Part Order Number")
    so_number = models.CharField(max_length=100, blank=True, default="", verbose_name="SO Number")
    warranty_trade = models.CharField(max_length=50, blank=True, default="", db_index=True, verbose_name="Warranty/Trade")
    part_shipment_status = models.CharField(max_length=100, blank=True, default="", db_index=True, verbose_name="Part Shipment Status")
    good_part_image = models.FileField(upload_to="hp_stock_images/", blank=True, null=True, verbose_name="Good Part Photo")
    good_part_image_back = models.FileField(upload_to="hp_stock_images/", blank=True, null=True, verbose_name="Good Part Back Photo")
    return_part_image = models.FileField(upload_to="hp_stock_images/", blank=True, null=True, verbose_name="Return Part Photo")
    # Return part photo categories (all optional)
    return_part_ct_image = models.FileField(upload_to="hp_stock_images/", blank=True, null=True, verbose_name="Return Part CT Photo")
    return_box_front_image = models.FileField(upload_to="hp_stock_images/", blank=True, null=True, verbose_name="Return Box Front Photo")
    return_box_back_image = models.FileField(upload_to="hp_stock_images/", blank=True, null=True, verbose_name="Return Box Back Photo")
    return_box_corner_right_image = models.FileField(upload_to="hp_stock_images/", blank=True, null=True, verbose_name="Return Box Corner Right Photo")
    return_box_corner_left_image = models.FileField(upload_to="hp_stock_images/", blank=True, null=True, verbose_name="Return Box Corner Left Photo")
    return_box_corner_top_image = models.FileField(upload_to="hp_stock_images/", blank=True, null=True, verbose_name="Return Box Corner Top Photo")
    return_box_corner_bottom_image = models.FileField(upload_to="hp_stock_images/", blank=True, null=True, verbose_name="Return Box Corner Bottom Photo")
    return_option_image_1 = models.FileField(upload_to="hp_stock_images/", blank=True, null=True, verbose_name="Return Option Photo 1")
    return_option_image_2 = models.FileField(upload_to="hp_stock_images/", blank=True, null=True, verbose_name="Return Option Photo 2")
    return_option_image_3 = models.FileField(upload_to="hp_stock_images/", blank=True, null=True, verbose_name="Return Option Photo 3")
    dc_cut_request_message = models.TextField(blank=True, default="", verbose_name="DC Cut Request Message")
    dc_cut_approved = models.BooleanField(default=False, verbose_name="DC Cut Approved")
    dc_cut_chat = models.JSONField(default=list, blank=True, verbose_name="DC Cut Chat Logs")
    
    region = models.CharField(max_length=20, blank=True, default="", verbose_name="Region")
    status = models.CharField(
        max_length=30,
        choices=[
            ("PENDING", "Stock Entry"),
            ("STOCK_CHECK", "Stock Check"),
            ("GOOD_PART_PHOTO", "Good Part Photo"),
            ("ISSUED", "Part Taken by Engineer"),
            ("WORK_STATUS", "Work Status"),
            ("UNUSED_RETURN", "Unused Part"),
            ("DEFECTIVE_RETURN", "Old/Defective Part"),
            ("HANDOVER", "Part Handover by Engineer"),
            ("RETURN_PART_PHOTO", "Return Part Photo"),
            ("DC_CUT_REQUEST", "DC Cut Request"),
            ("CLOSED", "Close the Case"),
        ],
        default="PENDING",
        verbose_name="Status",
    )
    engineer_name = models.CharField(max_length=255, blank=True, default="", verbose_name="Engineer Name")
    engineer_phone = models.CharField(max_length=20, blank=True, default="", verbose_name="Engineer Phone")
    part_description = models.TextField(blank=True, default="", verbose_name="Part Description")
    customer_name = models.CharField(max_length=255, blank=True, default="", verbose_name="Customer Name")
    inventory_details = models.TextField(blank=True, default="", verbose_name="Inventory Details")
    transition_history = models.JSONField(default=list, blank=True, verbose_name="Transition History")
    opencall_case_details = models.JSONField(default=dict, blank=True, verbose_name="Opencall Case Details")
    case_created_time = models.DateTimeField(null=True, blank=True, verbose_name="Case Created Time")
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="hp_stock_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-case_created_time", "-created_at"]
        verbose_name = "HP Stock Item"
        verbose_name_plural = "HP Stock Items"

    def __str__(self):
        return f"HP Stock - Case: {self.case_id} | WO: {self.work_order_id}"


class HPStockRMAPart(models.Model):
    part_number = models.CharField(max_length=100, db_index=True, verbose_name="Part Number")
    description = models.TextField(blank=True, default="", verbose_name="Part Description")
    category = models.CharField(max_length=100, blank=True, default="", verbose_name="Category")
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Price")
    hsn_code = models.CharField(max_length=50, blank=True, default="", verbose_name="HSN Code")
    igst = models.CharField(max_length=10, blank=True, default="", verbose_name="IGST")
    cgst = models.CharField(max_length=10, blank=True, default="", verbose_name="CGST")
    sgst = models.CharField(max_length=10, blank=True, default="", verbose_name="SGST")
    eosl_flag = models.CharField(max_length=10, blank=True, default="", verbose_name="EOSL Flag")
    validity = models.DateField(null=True, blank=True, verbose_name="Validity")
    parts_status = models.CharField(max_length=50, blank=True, default="", verbose_name="Parts Status")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["part_number"]
        verbose_name = "HP Stock RMA Part"
        verbose_name_plural = "HP Stock RMA Parts"

    def __str__(self):
        return f"{self.part_number} - {self.description[:30]}"


class OpencallPartsCount(models.Model):
    """Day-by-day, region-wise count of parts calls in the OpenCall record table.

    Computed on the OpenCall side (parts in each daily report per region) and pushed
    here. Read-only from the frontend's perspective — it just displays the counts.
    """
    report_date = models.DateField(db_index=True, verbose_name="Report Date")
    region = models.CharField(max_length=50, blank=True, default="", db_index=True, verbose_name="Region")
    count = models.IntegerField(default=0, verbose_name="Parts Call Count")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-report_date", "region"]
        unique_together = ("report_date", "region")
        verbose_name = "OpenCall Parts Count"
        verbose_name_plural = "OpenCall Parts Counts"

    def __str__(self):
        return f"{self.report_date} {self.region}: {self.count}"


class OpencallActivePartCase(models.Model):
    """Case IDs of OpenCall's "Active Part Cases" for a report date (pushed from OpenCall).

    Used to scope the HP Stock part-value bands to exactly the cases OpenCall currently
    counts as active part cases — the same set behind the region cards' Active number.
    """
    report_date = models.DateField(db_index=True, verbose_name="Report Date")
    case_id = models.CharField(max_length=100, db_index=True, verbose_name="Case ID")
    region = models.CharField(max_length=50, blank=True, default="", verbose_name="Region")

    class Meta:
        unique_together = ("report_date", "case_id")
        verbose_name = "OpenCall Active Part Case"
        verbose_name_plural = "OpenCall Active Part Cases"

    def __str__(self):
        return f"{self.report_date} {self.case_id} ({self.region})"
