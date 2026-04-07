from django.contrib.auth.models import User
from django.db import models


class PartRequest(models.Model):
    URGENCY_CHOICES = [
        ('normal', 'Normal'),
        ('urgent', 'Urgent'),
        ('critical', 'Critical'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]

    ticket = models.ForeignKey(
        'ticket.Ticket', on_delete=models.CASCADE, related_name='part_requests',
    )
    requested_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='part_requests_made',
    )
    part_number = models.CharField(max_length=100)
    part_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    quantity = models.IntegerField(default=1)
    urgency = models.CharField(max_length=20, choices=URGENCY_CHOICES, default='normal')
    estimated_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='part_requests_approved',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default='')
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Part Request'
        verbose_name_plural = 'Part Requests'

    def __str__(self):
        return f"{self.part_number} - {self.part_name} ({self.get_status_display()})"
