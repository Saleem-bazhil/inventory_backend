from django.contrib.auth.models import User
from django.db import models


class Invoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('partial', 'Partial'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    invoice_number = models.CharField(max_length=20, unique=True, editable=False)
    ticket = models.ForeignKey(
        'ticket.Ticket', on_delete=models.CASCADE, related_name='invoices',
    )
    quotation = models.ForeignKey(
        'quotation.Quotation', on_delete=models.SET_NULL, null=True, blank=True,
    )
    customer_name = models.CharField(max_length=255)
    customer_phone = models.CharField(max_length=50, blank=True, default='')
    customer_email = models.CharField(max_length=255, blank=True, default='')
    customer_address = models.TextField(blank=True, default='')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=18.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    payment_method = models.CharField(max_length=50, blank=True, default='')
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    region = models.CharField(max_length=20, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)
            self.invoice_number = f"INV-{self.created_at.year}-{self.pk:05d}"
            super().save(update_fields=['invoice_number'])
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice_number} - {self.customer_name}"


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name='items',
    )
    description = models.CharField(max_length=500)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = 'Invoice Item'
        verbose_name_plural = 'Invoice Items'

    def __str__(self):
        return f"{self.description} x{self.quantity}"
