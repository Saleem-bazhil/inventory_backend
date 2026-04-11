"""
Workflow engine for the ticket system.

All status transitions MUST go through ``transition_ticket()``.
It enforces the state machine, records timeline entries, checks SLA, and
creates delay records when breaches occur.
"""

from django.db import transaction
from django.utils import timezone

from .models import DelayRecord, SLAConfig, Ticket, TicketTimeline


# ---------------------------------------------------------------------------
# State machine definition
# ---------------------------------------------------------------------------

WORKFLOW_TRANSITIONS = {
    "cso_created": [{"to": "assigned", "roles": ["manager", "sub_admin", "admin"]}],
    "assigned": [{"to": "diagnosis", "roles": ["engineer", "sub_admin", "admin"]}],
    "diagnosis": [
        {"to": "part_requested", "roles": ["engineer", "sub_admin", "admin"]},
        {"to": "in_progress", "roles": ["engineer", "sub_admin", "admin"]},
    ],
    "part_requested": [
        # Only manager / admin can approve parts — sub_admin is explicitly excluded
        {"to": "part_approved", "roles": ["manager", "admin"]},
        {"to": "diagnosis", "roles": ["manager", "admin"]},
    ],
    "part_approved": [{"to": "quotation_sent", "roles": ["cc_team", "sub_admin", "admin"]}],
    "quotation_sent": [{"to": "cx_pending", "roles": ["cc_team", "sub_admin", "admin"]}],
    "cx_pending": [
        {"to": "cx_approved", "roles": ["cc_team", "sub_admin", "admin"]},
        {"to": "cx_rejected", "roles": ["cc_team", "sub_admin", "admin"]},
    ],
    "cx_approved": [{"to": "part_ordered", "roles": ["manager", "sub_admin", "admin"]}],
    "cx_rejected": [
        {"to": "closed", "roles": ["manager", "sub_admin", "admin"]},
        {"to": "quotation_sent", "roles": ["cc_team", "manager", "sub_admin", "admin"]},
    ],
    "part_ordered": [{"to": "part_received", "roles": ["manager", "sub_admin", "admin"]}],
    "part_received": [{"to": "in_progress", "roles": ["engineer", "sub_admin", "admin"]}],
    "in_progress": [{"to": "ready_for_delivery", "roles": ["engineer", "sub_admin", "admin"]}],
    "ready_for_delivery": [{"to": "closed", "roles": ["receptionist", "manager", "sub_admin", "admin"]}],
    "closed": [{"to": "under_observation", "roles": ["manager", "sub_admin", "admin"]}],
    "under_observation": [
        {"to": "closed", "roles": ["manager", "sub_admin", "admin"]},
        {"to": "in_progress", "roles": ["manager", "sub_admin", "admin"]},
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def lookup_sla(status, service_type, priority):
    """
    Find the most specific SLAConfig for the given combination.

    Priority order:
      1. Exact match on status + service_type + priority
      2. status + service_type (any priority)
      3. status + priority (any service_type)
      4. status only (catch-all)

    Returns the SLAConfig instance or ``None``.
    """
    candidates = SLAConfig.objects.filter(status=status, is_active=True)

    # Try most specific first
    exact = candidates.filter(service_type=service_type, priority=priority).first()
    if exact:
        return exact

    by_service = candidates.filter(service_type=service_type, priority__isnull=True).first()
    if by_service:
        return by_service

    by_priority = candidates.filter(service_type__isnull=True, priority=priority).first()
    if by_priority:
        return by_priority

    catch_all = candidates.filter(service_type__isnull=True, priority__isnull=True).first()
    return catch_all


def classify_delay(delay_minutes):
    """Classify a delay into minor / moderate / severe buckets."""
    if delay_minutes <= 30:
        return "minor"
    elif delay_minutes <= 120:
        return "moderate"
    return "severe"


def get_available_transitions(ticket, actor_role):
    """Return the list of valid transition dicts for the given ticket and role."""
    transitions = WORKFLOW_TRANSITIONS.get(ticket.current_status, [])
    available = []
    for t in transitions:
        if actor_role in t["roles"]:
            # Prevent closed → under_observation loop:
            # If ticket was already under observation, don't allow it again.
            if (
                ticket.current_status == "closed"
                and t["to"] == "under_observation"
                and TicketTimeline.objects.filter(
                    ticket=ticket, status="under_observation"
                ).exists()
            ):
                continue
            available.append(t)
    return available


# ---------------------------------------------------------------------------
# Core transition function
# ---------------------------------------------------------------------------

class TransitionError(Exception):
    """Raised when a status transition is invalid."""
    pass


@transaction.atomic
def transition_ticket(ticket, to_status, actor, actor_role, comment=None, metadata=None):
    """
    Single entry point for ALL ticket status changes.

    Steps:
      1. Validate the transition is legal (state machine + role check).
      2. Close current timeline entry (set exited_at, compute duration, check SLA).
      3. Create a DelayRecord if the current stage was breached.
      4. Look up SLA for the new status.
      5. Create a new timeline entry for the new status.
      6. Update ``ticket.current_status``.
      7. If transitioning to ``closed``, set ``ticket.closed_at``.
      8. Return the updated ticket.

    Raises ``TransitionError`` for illegal transitions.
    """
    from_status = ticket.current_status

    # 1. Validate transition
    allowed = WORKFLOW_TRANSITIONS.get(from_status, [])
    matching_transition = None
    for t in allowed:
        if t["to"] == to_status and actor_role in t["roles"]:
            matching_transition = t
            break

    if matching_transition is None:
        raise TransitionError(
            f"Transition from '{from_status}' to '{to_status}' is not allowed "
            f"for role '{actor_role}'."
        )

    # Auto-set requires_parts based on path chosen from diagnosis
    if from_status == "diagnosis":
        if to_status == "part_requested":
            ticket.requires_parts = True
        elif to_status == "in_progress":
            ticket.requires_parts = False

    now = timezone.now()

    # 2. Close the current (open) timeline entry
    current_entry = (
        TicketTimeline.objects
        .filter(ticket=ticket, exited_at__isnull=True)
        .order_by("-entered_at")
        .first()
    )

    if current_entry:
        current_entry.exited_at = now
        delta = now - current_entry.entered_at
        current_entry.duration_minutes = int(delta.total_seconds() / 60)

        # Check SLA breach
        if current_entry.sla_minutes is not None:
            if current_entry.duration_minutes > current_entry.sla_minutes:
                current_entry.is_breached = True
                current_entry.breach_minutes = (
                    current_entry.duration_minutes - current_entry.sla_minutes
                )
        current_entry.save()

        # 3. Create delay record if breached
        if current_entry.is_breached:
            DelayRecord.objects.create(
                ticket=ticket,
                timeline_entry=current_entry,
                status=from_status,
                responsible_role=current_entry.responsible_role or "",
                responsible_user=ticket.current_assignee,
                sla_minutes=current_entry.sla_minutes or 0,
                actual_minutes=current_entry.duration_minutes,
                delay_minutes=current_entry.breach_minutes,
                delay_category=classify_delay(current_entry.breach_minutes),
            )

    # 4. Look up SLA for new status
    sla_config = lookup_sla(to_status, ticket.service_type, ticket.priority)
    sla_minutes = sla_config.sla_minutes if sla_config else None
    responsible_role = sla_config.responsible_role if sla_config else None

    # 5. Create new timeline entry
    TicketTimeline.objects.create(
        ticket=ticket,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        actor_role=actor_role,
        comment=comment or "",
        metadata=metadata or {},
        entered_at=now,
        sla_minutes=sla_minutes,
        responsible_role=responsible_role,
    )

    # 6. Update ticket status
    ticket.current_status = to_status

    # 7. Handle closed status
    if to_status == "closed":
        ticket.closed_at = now
    elif from_status == "closed":
        # Reopening — clear closed_at
        ticket.closed_at = None

    ticket.save()

    # 8. Auto-create linked records based on transition (side effects)
    _apply_side_effects(ticket, from_status, to_status, actor, comment, metadata or {})

    return ticket


# ---------------------------------------------------------------------------
# Side effects: auto-create records when tickets reach certain stages
# ---------------------------------------------------------------------------

def _apply_side_effects(ticket, from_status, to_status, actor, comment, metadata):
    """
    When a ticket transitions to a workflow stage, auto-create the
    corresponding record in the linked module so it appears on that page.
    """
    from parts.models import PartRequest
    from quotation.models import Quotation, QuotationItem
    from invoice.models import Invoice

    # diagnosis → part_requested: auto-create PartRequest from ticket's part fields
    if to_status == "part_requested" and from_status == "diagnosis":
        # Only create if one doesn't already exist for this ticket in pending state
        if not PartRequest.objects.filter(ticket=ticket, status="pending").exists():
            PartRequest.objects.create(
                ticket=ticket,
                requested_by=actor,
                part_number=ticket.part_number or "TBD",
                part_name=ticket.part_description or ticket.product_name or "Part for service",
                description=comment or ticket.issue_description or "",
                quantity=ticket.qty or 1,
                urgency="normal",
                estimated_cost=None,
                status="pending",
            )

    # part_approved → quotation_sent: auto-create Quotation draft
    elif to_status == "quotation_sent" and from_status == "part_approved":
        if not Quotation.objects.filter(ticket=ticket, status__in=["draft", "sent"]).exists():
            # Get approved parts to estimate cost
            approved_parts = PartRequest.objects.filter(ticket=ticket, status="approved")
            parts_cost = sum(
                (p.estimated_cost or 0) * p.quantity for p in approved_parts
            )
            tax_amount = round(float(parts_cost) * 0.18, 2)
            total = float(parts_cost) + tax_amount

            q = Quotation.objects.create(
                ticket=ticket,
                parts_cost=parts_cost,
                labor_cost=0,
                tax_percent=18.00,
                tax_amount=tax_amount,
                discount=0,
                total_amount=total,
                status="sent",
                prepared_by=actor,
                sent_at=timezone.now(),
                notes=comment or "",
            )

            # Add line items from approved parts
            for part in approved_parts:
                QuotationItem.objects.create(
                    quotation=q,
                    part_request=part,
                    description=f"{part.part_name} ({part.part_number})",
                    quantity=part.quantity,
                    unit_price=part.estimated_cost or 0,
                    total=(part.estimated_cost or 0) * part.quantity,
                )

    # cx_approved → part_ordered: auto-create PurchaseOrder
    elif to_status == "part_ordered" and from_status == "cx_approved":
        from procurement.models import PurchaseOrder, POItem
        if not PurchaseOrder.objects.filter(
            items__part_request__ticket=ticket,
            status__in=["draft", "sent", "confirmed"],
        ).exists():
            approved_parts = PartRequest.objects.filter(ticket=ticket, status="approved")
            total_amount = sum(
                (p.estimated_cost or 0) * p.quantity for p in approved_parts
            )

            po = PurchaseOrder.objects.create(
                supplier_name=metadata.get("supplier_name", "TBD"),
                supplier_contact=metadata.get("supplier_contact", ""),
                supplier_email=metadata.get("supplier_email", ""),
                status="sent",
                ordered_by=actor,
                total_amount=total_amount,
                order_date=timezone.now().date(),
                notes=f"Auto-created for ticket {ticket.ticket_number}",
            )

            for part in approved_parts:
                POItem.objects.create(
                    purchase_order=po,
                    part_request=part,
                    part_number=part.part_number,
                    part_name=part.part_name,
                    quantity=part.quantity,
                    unit_price=part.estimated_cost or 0,
                    total=(part.estimated_cost or 0) * part.quantity,
                )

                # Update part request status to ordered
                part.status = "ordered"
                part.save(update_fields=["status"])

    # ready_for_delivery → closed: auto-create Invoice
    elif to_status == "closed" and from_status == "ready_for_delivery":
        if not Invoice.objects.filter(ticket=ticket).exists():
            # Get the quotation if any
            quotation = Quotation.objects.filter(
                ticket=ticket, status="customer_approved",
            ).first()

            if quotation:
                inv = Invoice.objects.create(
                    ticket=ticket,
                    quotation=quotation,
                    customer_name=ticket.cust_name,
                    customer_phone=ticket.cust_contact or "",
                    customer_email=ticket.cust_email or "",
                    customer_address=ticket.cust_address or "",
                    subtotal=quotation.parts_cost + quotation.labor_cost,
                    tax_percent=quotation.tax_percent,
                    tax_amount=quotation.tax_amount,
                    discount=quotation.discount,
                    total=quotation.total_amount,
                    status="sent",
                    created_by=actor,
                    notes=f"Auto-generated on ticket closure",
                )

    # part_received: update PartRequest statuses to received
    elif to_status == "part_received":
        PartRequest.objects.filter(
            ticket=ticket, status="ordered",
        ).update(status="received")
