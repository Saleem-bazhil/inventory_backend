"""Seed default SLA configuration."""
from django.core.management.base import BaseCommand
from ticket.models import SLAConfig


DEFAULT_SLAS = [
    {"status": "cso_created",        "sla_minutes": 30,    "responsible_role": "receptionist", "escalation_after_mins": 45,   "escalation_to_role": "manager"},
    {"status": "assigned",           "sla_minutes": 60,    "responsible_role": "manager",      "escalation_after_mins": 90,   "escalation_to_role": "admin"},
    {"status": "diagnosis",          "sla_minutes": 240,   "responsible_role": "engineer",     "escalation_after_mins": 360,  "escalation_to_role": "manager"},
    {"status": "part_requested",     "sla_minutes": 120,   "responsible_role": "manager",      "escalation_after_mins": 180,  "escalation_to_role": "admin"},
    {"status": "part_approved",      "sla_minutes": 120,   "responsible_role": "cc_team",      "escalation_after_mins": 180,  "escalation_to_role": "manager"},
    {"status": "quotation_sent",     "sla_minutes": 60,    "responsible_role": "cc_team",      "escalation_after_mins": 120,  "escalation_to_role": "manager"},
    {"status": "cx_pending",         "sla_minutes": 1440,  "responsible_role": "cc_team",      "escalation_after_mins": 2880, "escalation_to_role": "manager"},
    {"status": "cx_approved",        "sla_minutes": 60,    "responsible_role": "manager",      "escalation_after_mins": 120,  "escalation_to_role": "admin"},
    {"status": "part_ordered",       "sla_minutes": 2880,  "responsible_role": "manager",      "escalation_after_mins": 4320, "escalation_to_role": "admin"},
    {"status": "part_received",      "sla_minutes": 120,   "responsible_role": "manager",      "escalation_after_mins": 240,  "escalation_to_role": "admin"},
    {"status": "in_progress",        "sla_minutes": 480,   "responsible_role": "engineer",     "escalation_after_mins": 720,  "escalation_to_role": "manager"},
    {"status": "ready_for_delivery", "sla_minutes": 240,   "responsible_role": "receptionist", "escalation_after_mins": 480,  "escalation_to_role": "manager"},
    {"status": "under_observation",  "sla_minutes": 10080, "responsible_role": "engineer",     "escalation_after_mins": 14400,"escalation_to_role": "manager"},
]


class Command(BaseCommand):
    help = "Seed default SLA configuration for all ticket statuses"

    def handle(self, *args, **options):
        created_count = 0
        for sla_data in DEFAULT_SLAS:
            _, created = SLAConfig.objects.get_or_create(
                status=sla_data["status"],
                service_type=None,
                priority=None,
                defaults={
                    "sla_minutes": sla_data["sla_minutes"],
                    "responsible_role": sla_data["responsible_role"],
                    "escalation_after_mins": sla_data.get("escalation_after_mins"),
                    "escalation_to_role": sla_data.get("escalation_to_role"),
                },
            )
            if created:
                created_count += 1
                self.stdout.write(f"  Created SLA: {sla_data['status']} ({sla_data['sla_minutes']}m)")
            else:
                self.stdout.write(f"  Exists: {sla_data['status']}")

        self.stdout.write(self.style.SUCCESS(f"\nDone! Created {created_count} SLA configs."))
