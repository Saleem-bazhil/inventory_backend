from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import DelayRecord, SLAConfig, Ticket, TicketTimeline


@admin.register(Ticket)
class TicketAdmin(ModelAdmin):
    list_display = [
        "ticket_number",
        "cust_name",
        "product_name",
        "case_id",
        "service_type",
        "priority",
        "current_status",
        "region",
        "current_assignee",
        "created_at",
    ]
    list_filter = [
        "current_status",
        "service_type",
        "priority",
        "region",
        "requires_parts",
        "otp_verified",
    ]
    search_fields = [
        "ticket_number",
        "cust_name",
        "cust_contact",
        "case_id",
        "product_name",
        "serial_number",
        "engineer_name",
    ]
    readonly_fields = ["ticket_number", "created_at", "updated_at"]
    raw_id_fields = ["current_assignee", "created_by"]


@admin.register(TicketTimeline)
class TicketTimelineAdmin(ModelAdmin):
    list_display = [
        "ticket",
        "from_status",
        "to_status",
        "actor",
        "actor_role",
        "entered_at",
        "exited_at",
        "duration_minutes",
        "is_breached",
    ]
    list_filter = ["to_status", "is_breached", "actor_role"]
    search_fields = ["ticket__ticket_number", "comment"]
    raw_id_fields = ["ticket", "actor"]


@admin.register(SLAConfig)
class SLAConfigAdmin(ModelAdmin):
    list_display = [
        "status",
        "service_type",
        "priority",
        "sla_minutes",
        "responsible_role",
        "warning_at_percent",
        "is_active",
    ]
    list_filter = ["status", "is_active", "responsible_role"]
    search_fields = ["status", "responsible_role"]


@admin.register(DelayRecord)
class DelayRecordAdmin(ModelAdmin):
    list_display = [
        "ticket",
        "status",
        "responsible_role",
        "sla_minutes",
        "actual_minutes",
        "delay_minutes",
        "delay_category",
        "acknowledged_at",
    ]
    list_filter = ["delay_category", "status", "responsible_role"]
    search_fields = ["ticket__ticket_number", "reason"]
    raw_id_fields = ["ticket", "timeline_entry", "responsible_user", "acknowledged_by"]
