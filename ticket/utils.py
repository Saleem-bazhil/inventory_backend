import datetime
from django.utils import timezone


def get_sla_start_time(ticket, timeline_entry):
    """
    Returns the corrected start time for SLA calculation.
    If the timeline entry is the initial CSO stage, we use cso_date as start time 
    if it exists, otherwise fallback to created_at.
    For all other stages, we use the timestamp when it entered that stage.
    """
    if timeline_entry.to_status == "cso_created":
        if ticket.cso_date:
            return timezone.make_aware(datetime.datetime.combine(ticket.cso_date, datetime.time.min))
        return ticket.created_at
    return timeline_entry.entered_at
