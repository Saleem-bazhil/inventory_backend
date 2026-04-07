from django.contrib.auth.models import User
from django.db import models


class Quotation(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('customer_approved', 'Customer Approved'),
        ('customer_rejected', 'Customer Rejected'),
        ('negotiating', 'Negotiating'),
        ('expired', 'Expired'),
    ]

    quotation_number = models.CharField(max_length=20, unique=True, editable=False)
    ticket = models.ForeignKey(
        'ticket.Ticket', on_delete=models.CASCADE, related_name='quotations',
    )
    parts_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    labor_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=18.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='draft')
    prepared_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='quotations_prepared',
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    customer_response_at = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    rejection_reason = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Quotation'
        verbose_name_plural = 'Quotations'

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)
            self.quotation_number = f"QT-{self.created_at.year}-{self.pk:05d}"
            super().save(update_fields=['quotation_number'])
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quotation_number} - {self.get_status_display()}"


class QuotationItem(models.Model):
    quotation = models.ForeignKey(
        Quotation, on_delete=models.CASCADE, related_name='items',
    )
    part_request = models.ForeignKey(
        'parts.PartRequest', on_delete=models.SET_NULL, null=True, blank=True,
    )
    description = models.CharField(max_length=500)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Quotation Item'
        verbose_name_plural = 'Quotation Items'

    def __str__(self):
        return f"{self.description} x{self.quantity}"
