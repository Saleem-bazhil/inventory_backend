from django.contrib.auth.models import User
from django.db import models


class PurchaseOrder(models.Model):
    PO_STATUS = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('confirmed', 'Confirmed'),
        ('shipped', 'Shipped'),
        ('partial_received', 'Partial'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]

    po_number = models.CharField(max_length=20, unique=True, editable=False)
    supplier_name = models.CharField(max_length=255)
    supplier_contact = models.CharField(max_length=255, blank=True, default='')
    supplier_email = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=20, choices=PO_STATUS, default='draft')
    ordered_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='purchase_orders',
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    order_date = models.DateField(null=True, blank=True)
    expected_delivery = models.DateField(null=True, blank=True)
    actual_delivery = models.DateField(null=True, blank=True)
    region = models.CharField(max_length=20, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Purchase Order'
        verbose_name_plural = 'Purchase Orders'

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)
            self.po_number = f"PO-{self.created_at.year}-{self.pk:05d}"
            super().save(update_fields=['po_number'])
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.po_number} - {self.supplier_name}"


class POItem(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name='items',
    )
    part_request = models.ForeignKey(
        'parts.PartRequest', on_delete=models.SET_NULL, null=True, blank=True,
    )
    part_number = models.CharField(max_length=100)
    part_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    total = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    received_qty = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'PO Item'
        verbose_name_plural = 'PO Items'

    def __str__(self):
        return f"{self.part_number} - {self.part_name} x{self.quantity}"


class StockItem(models.Model):
    part_number = models.CharField(max_length=100, unique=True)
    part_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    category = models.CharField(max_length=100, blank=True, default='')
    brand = models.CharField(max_length=100, blank=True, default='')
    qty_on_hand = models.IntegerField(default=0)
    qty_reserved = models.IntegerField(default=0)
    qty_on_order = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=5)
    reorder_qty = models.IntegerField(default=10)
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    region = models.CharField(max_length=20, blank=True, default='')
    storage_location = models.CharField(max_length=100, blank=True, default='')
    last_restocked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['part_number']
        verbose_name = 'Stock Item'
        verbose_name_plural = 'Stock Items'

    @property
    def qty_available(self):
        return self.qty_on_hand - self.qty_reserved

    def __str__(self):
        return f"{self.part_number} - {self.part_name} (On hand: {self.qty_on_hand})"


class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('in', 'In'),
        ('out', 'Out'),
        ('reserved', 'Reserved'),
        ('released', 'Released'),
        ('adjustment', 'Adjustment'),
        ('buffer_in', 'Buffer In'),
        ('buffer_out', 'Buffer Out'),
    ]

    stock_item = models.ForeignKey(
        StockItem, on_delete=models.CASCADE, related_name='movements',
    )
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField()
    reference_type = models.CharField(max_length=50, blank=True, default='')
    reference_id = models.IntegerField(null=True, blank=True)
    performed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Stock Movement'
        verbose_name_plural = 'Stock Movements'

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} - {self.stock_item.part_number}"


class BufferStock(models.Model):
    stock_item = models.ForeignKey(
        StockItem, on_delete=models.CASCADE, related_name='buffer_entries',
    )
    quantity = models.IntegerField()
    reason = models.TextField(blank=True, default='')
    reserved_by = models.ForeignKey(User, on_delete=models.CASCADE)
    reserved_for_ticket = models.ForeignKey(
        'ticket.Ticket', on_delete=models.SET_NULL, null=True, blank=True,
    )
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Buffer Stock'
        verbose_name_plural = 'Buffer Stocks'

    def __str__(self):
        return f"Buffer: {self.stock_item.part_number} x{self.quantity}"


class BufferPart(models.Model):
    """Simple buffer entry — standalone parts not tied to stock inventory."""

    part_number = models.CharField(max_length=100, verbose_name="Part Number")
    part_name = models.CharField(max_length=255, verbose_name="Part Name")
    quantity = models.IntegerField(verbose_name="Quantity")
    general_name = models.CharField(max_length=255, blank=True, default="", verbose_name="General Name")
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="buffer_parts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Buffer Part"
        verbose_name_plural = "Buffer Parts"

    def __str__(self):
        return f"{self.part_number} — {self.part_name} x{self.quantity}"
