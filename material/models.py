from django.db import models

class MaterialTrack(models.Model):
    # --- Customer & Order Information ---
    cust_name = models.CharField(max_length=255, verbose_name="Customer Name")
    cust_contact = models.CharField(max_length=100, verbose_name="Customer Contact", blank=True, null=True)
    case_id = models.CharField(max_length=100, verbose_name="Case ID", unique=True)
    so_number = models.CharField(max_length=100, verbose_name="SO#", blank=True, null=True)
    
    # --- Issue & Product Details ---
    warranty = models.BooleanField(default=False, verbose_name="Warranty")
    issue = models.TextField(blank=True, null=True, verbose_name="Issue")
    
    # Note: If 'Product' is a dropdown of fixed items, this could be a ForeignKey 
    # to a separate Product model, but a CharField is the simplest starting point.
    product = models.CharField(max_length=200, verbose_name="Product")
    model_name = models.CharField(max_length=200, verbose_name="Model", blank=True, null=True)
    part_number = models.CharField(max_length=100, verbose_name="Part #", blank=True, null=True)
    serial_number = models.CharField(max_length=100, verbose_name="Serial #", blank=True, null=True)
    qty = models.IntegerField(default=0, verbose_name="Qty")
    
    # --- Tracking & Dates ---
    hp_part_in_date = models.DateField(blank=True, null=True, verbose_name="HP Part In Date")
    
    # 'Aging' is often a calculated field (current date - in_date), 
    # but if you need to store it manually as shown on the form:
    aging = models.IntegerField(blank=True, null=True, verbose_name="Aging (Days)")
    
    out_date = models.DateField(blank=True, null=True, verbose_name="Out Date")
    
    # These could be ForeignKeys to the standard Django User model if your staff logs in
    collector = models.CharField(max_length=200, blank=True, null=True, verbose_name="Collector")
    
    in_date = models.DateField(blank=True, null=True, verbose_name="In Date")
    receiver = models.CharField(max_length=200, blank=True, null=True, verbose_name="Receiver")
    
    used_part = models.BooleanField(default=False, verbose_name="Used Part")
    remarks = models.TextField(blank=True, null=True, verbose_name="Remarks")

    # --- Meta & String Representation ---
    class Meta:
        verbose_name = "Material Tracking Record"
        verbose_name_plural = "Material Tracking Records"
        ordering = ['-out_date', '-in_date'] # Orders by newest first

    def __str__(self):
        return f"{self.case_id} - {self.cust_name} ({self.part_number})"