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
    
    region = models.CharField(max_length=20, blank=True, default="", verbose_name="Region")
    status = models.CharField(
        max_length=30,
        choices=[
            ("PENDING", "Stock Entry"),
            ("STOCK_CHECK", "Stock Check"),
            ("ISSUED", "Part Taken by Engineer"),
            ("WORK_STATUS", "Work Status"),
            ("UNUSED_RETURN", "Unused Part"),
            ("DEFECTIVE_RETURN", "Old/Defective Part"),
            ("HANDOVER", "Handover by Engineer"),
            ("CLOSED", "Close the Case"),
        ],
        default="PENDING",
        verbose_name="Status",
    )
    engineer_name = models.CharField(max_length=255, blank=True, default="", verbose_name="Engineer Name")
    transition_history = models.JSONField(default=list, blank=True, verbose_name="Transition History")
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="hp_stock_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "HP Stock Item"
        verbose_name_plural = "HP Stock Items"

    def __str__(self):
        return f"HP Stock - Case: {self.case_id} | WO: {self.work_order_id}"
