from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Count, Q, Max, OuterRef, Subquery, DecimalField
from django.db.models.functions import TruncDate
from django.utils import timezone
from .models import HPStockItem, HPStockRMAPart, OpencallPartsCount, OpencallActivePartCase
from .serializers import HPStockItemSerializer, HPStockRMAPartSerializer, OpencallPartsCountSerializer

from rest_framework.pagination import PageNumberPagination
import math
import re
import random
import urllib.parse
from datetime import timedelta, datetime, timezone as dt_timezone
from material.models import OTPVerification

# Transition timestamps are stored in UTC (settings TIME_ZONE=UTC, USE_TZ=True), but
# the users operate in India and pick dates on an IST calendar. Convert timestamps to
# IST before taking their date, so an action done at (say) 1 AM IST counts on that IST
# day rather than the previous UTC day. India has no DST, so a fixed +05:30 is exact.
IST = dt_timezone(timedelta(hours=5, minutes=30))

class CustomPageNumberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'per_page'
    max_page_size = 100

    def get_paginated_response(self, data):
        total = self.page.paginator.count
        per_page = self.get_page_size(self.request)
        pages = math.ceil(total / per_page) if total else 1
        return Response({
            'items': data,
            'total': total,
            'page': self.page.number,
            'per_page': per_page,
            'pages': pages
        })

# The HP Stock workflow in order. WORK_STATUS branches into UNUSED_RETURN /
# DEFECTIVE_RETURN / DOA, which all rejoin at HANDOVER, so they share one step.
WORKFLOW_STAGES = [
    ['PENDING'],
    ['STOCK_CHECK'],
    ['GOOD_PART_PHOTO'],
    ['ISSUED'],
    ['WORK_STATUS'],
    ['UNUSED_RETURN', 'DEFECTIVE_RETURN', 'DOA'],
    ['HANDOVER'],
    ['RETURN_PART_PHOTO'],
    ['DC_CUT_REQUEST'],
    ['CLOSED'],
]

# For each status, every status at or past it in the workflow. A case sitting on
# one of these has completed that stage, which is how "how many cases did X" is
# counted (the workflow only moves forward).
STAGES_AT_OR_PAST = {
    status: [s for step in WORKFLOW_STAGES[idx:] for s in step]
    for idx, step in enumerate(WORKFLOW_STAGES)
    for status in step
}

# Cases where the engineer has taken the part (reached ISSUED) but has NOT yet handed
# it back (not reached HANDOVER) — i.e. the part is still out with the engineer, return
# pending. This is "at or past ISSUED" minus "at or past HANDOVER":
# {ISSUED, WORK_STATUS, UNUSED_RETURN, DEFECTIVE_RETURN, DOA}.
PENDING_RETURN_STATUSES = [
    s for s in STAGES_AT_OR_PAST['ISSUED'] if s not in STAGES_AT_OR_PAST['HANDOVER']
]


def _ist_date_str(ts):
    """The IST calendar date (YYYY-MM-DD) of an ISO timestamp string, or None.

    Timestamps are stored in UTC; the users pick dates in IST, so the timestamp is
    converted to IST before its date is taken. Falls back to the raw date prefix if
    the value can't be parsed (so a malformed entry never crashes a count).
    """
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return ts[:10] or None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt.astimezone(IST).date().isoformat()


def stage_reached_on_date(history, target_status, date_str):
    """True if this transition_history reached `target_status` on the date (YYYY-MM-DD).

    `history` is a JSON list of {to_status, timestamp, ...}. The timestamp records when
    the transition happened; its IST date is compared against date_str (which the user
    picked on an IST calendar). Used to count, per calendar day, how many cases reached
    a given workflow stage — as opposed to how many currently sit at or past it. A stage
    reached more than once on the same day still counts as one.
    """
    for entry in (history or []):
        if entry.get('to_status') != target_status:
            continue
        if _ist_date_str(entry.get('timestamp')) == date_str:
            return True
    return False


# Price bands for a part, keyed by the value the frontend sends/receives. Price
# is not a column on HPStockItem — it is looked up from the RMA catalog by
# good_part_number — so band filters annotate the price in via a subquery.
# Bounds are inclusive on the upper end (<= 5000 is Low, and so on).
PART_VALUE_BANDS = {
    'LOW': (None, 5000),
    'MID': (5000, 10000),
    'HIGH': (10000, 15000),
    'CRITICAL': (15000, None),
}


def annotate_part_price(queryset):
    """Annotate `part_price` from the RMA catalog (null when there is no match)."""
    price_subquery = (
        HPStockRMAPart.objects
        .filter(part_number=OuterRef('good_part_number'))
        .values('price')[:1]
    )
    return queryset.annotate(
        part_price=Subquery(price_subquery, output_field=DecimalField(max_digits=12, decimal_places=2))
    )


def opencall_active_case_ids():
    """Case ids of OpenCall's current "Active Part Cases" (latest report date pushed)."""
    latest = OpencallActivePartCase.objects.aggregate(d=Max('report_date'))['d']
    if not latest:
        return None
    return OpencallActivePartCase.objects.filter(report_date=latest).values_list('case_id', flat=True)


def part_value_band_q(band: str) -> Q:
    """Q object selecting rows whose annotated `part_price` falls in `band`."""
    low, high = PART_VALUE_BANDS[band]
    q = Q(part_price__isnull=False)
    if low is not None:
        q &= Q(part_price__gt=low)
    if high is not None:
        q &= Q(part_price__lte=high)
    return q


def _upload_images_parallel(files):
    """Save each uploaded file to storage, all at once, preserving input order.

    A transition can carry up to ten photos. Against S3 each save is a network
    round trip, so doing them one after another made "Confirm Transition" take as
    long as the sum of every upload. They are independent, so they go out together
    and the call now takes about as long as the slowest single upload.

    Returns [(saved_name, url), ...] — assign saved_name to the FileField (never
    the file object, which would upload it a second time on save()).
    """
    from concurrent.futures import ThreadPoolExecutor
    from django.core.files.storage import default_storage

    def _save(uploaded):
        saved_name = default_storage.save(f"hp_stock_images/{uploaded.name}", uploaded)
        return saved_name, default_storage.url(saved_name)

    if len(files) == 1:
        return [_save(files[0])]

    with ThreadPoolExecutor(max_workers=min(len(files), 8)) as pool:
        return list(pool.map(_save, files))


def _clean_phone(phone: str) -> str:
    """Strip non-digits and remove leading +91 or 91 to get 10-digit Indian number."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 13 and digits.startswith("091"):
        digits = digits[3:]
    return digits

def verify_otp_local(phone: str, otp: str) -> bool:
    """Verify OTP for a given phone number using the database."""
    phone = _clean_phone(phone)
    # Clean up expired OTPs
    OTPVerification.objects.filter(expires_at__lt=timezone.now()).delete()

    entry = OTPVerification.objects.filter(phone=phone).first()
    if not entry:
        return False
    if timezone.now() > entry.expires_at:
        entry.delete()
        return False
    if entry.otp != otp:
        return False

    # OTP verified — remove it so it can't be reused
    entry.delete()
    return True

class HPStockItemViewSet(viewsets.ModelViewSet):
    queryset = HPStockItem.objects.all()
    serializer_class = HPStockItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        profile = getattr(user, 'userprofile', None)
        
        # Admin roles see all by default unless filtered, others see their region
        role = profile.role if profile else ''
        if role not in ['admin', 'super_admin', 'manager']:
            user_region = profile.region if profile else ''
            if user_region:
                queryset = queryset.filter(region=user_region)

        # Filters
        view_mode = self.request.query_params.get('view', '')
        search = self.request.query_params.get('search', '')
        region = self.request.query_params.get('region', '')
        is_closed_param = self.request.query_params.get('is_closed', '').strip().lower()
        date_param = self.request.query_params.get('date', '').strip()
        warranty_trade_param = self.request.query_params.get('warranty_trade', '').strip()
        part_shipment_status_param = self.request.query_params.get('part_shipment_status', '').strip()
        stage_done_param = self.request.query_params.get('stage_done', '').strip().upper()
        # Optional date (YYYY-MM-DD) pairing with stage_done: list exactly the cases
        # that reached that stage on that day (matches a date-scoped count card), read
        # from transition_history rather than current status.
        stage_on_date_param = self.request.query_params.get('stage_on_date', '').strip()
        value_band_param = self.request.query_params.get('value_band', '').strip().upper()

        if region and region != 'all':
            # Non-admins should not be able to bypass their region check
            if role not in ['admin', 'super_admin', 'manager']:
                user_region = profile.region if profile else ''
                queryset = queryset.filter(region=user_region)
            else:
                queryset = queryset.filter(region=region)
        elif view_mode == 'my_region':
            user_region = profile.region if profile else ''
            if user_region:
                queryset = queryset.filter(region=user_region)

        if self.action != 'summary':
            if is_closed_param == 'true':
                queryset = queryset.filter(status='CLOSED')
            elif is_closed_param == 'dc_cut_request':
                queryset = queryset.filter(status='DC_CUT_REQUEST')
            elif is_closed_param == 'false':
                queryset = queryset.exclude(status__in=['CLOSED', 'DC_CUT_REQUEST'])

        # Pending return: part taken by an engineer but not handed back yet. Its card
        # is always current-state (date-independent), so it ignores stage_on_date.
        if stage_done_param == 'PENDING_RETURN':
            queryset = queryset.filter(status__in=PENDING_RETURN_STATUSES)
        # Cases that have completed a given stage — the counterpart of the stage
        # counts in summary(), so clicking a count card lists exactly those cases.
        elif stage_done_param in STAGES_AT_OR_PAST:
            if stage_on_date_param:
                # Date-scoped card: list only cases that reached this exact stage on
                # that day (from history), so the row set equals the card's number.
                matching_ids = [
                    row['id']
                    for row in queryset.values('id', 'transition_history')
                    if stage_reached_on_date(row['transition_history'], stage_done_param, stage_on_date_param)
                ]
                queryset = queryset.filter(id__in=matching_ids)
            else:
                queryset = queryset.filter(status__in=STAGES_AT_OR_PAST[stage_done_param])

        # Part value band — derived from price, so it stays super-admin-only.
        if value_band_param in PART_VALUE_BANDS and role == 'super_admin':
            active_ids = opencall_active_case_ids()
            queryset = queryset.filter(case_id__in=active_ids) if active_ids is not None else queryset.none()
            queryset = annotate_part_price(queryset).filter(part_value_band_q(value_band_param))

        # In the list, ?date= means "cases whose case was created on this day". The
        # summary uses ?date= differently — "cases that reached a stage on this day"
        # (counted from transition_history inside summary()), so it must NOT be
        # narrowed to the creation date here or those transitions get filtered out.
        # Likewise skip it when stage_on_date is driving a history-based stage filter,
        # so a date-scoped card click isn't also narrowed by case-creation date.
        if date_param and self.action != 'summary' and not stage_on_date_param:
            queryset = queryset.filter(
                Q(case_created_time__date=date_param) |
                Q(case_created_time__isnull=True, created_at__date=date_param)
            )

        if warranty_trade_param and warranty_trade_param.lower() != 'all':
            queryset = queryset.filter(warranty_trade=warranty_trade_param)

        if part_shipment_status_param and part_shipment_status_param.lower() != 'all':
            queryset = queryset.filter(part_shipment_status=part_shipment_status_param)

        if search:
            queryset = queryset.filter(
                Q(case_id__icontains=search) |
                Q(work_order_id__icontains=search) |
                Q(delivery_no__icontains=search) |
                Q(service_event_no__icontains=search) |
                Q(material_order_no__icontains=search) |
                Q(hp_sales_order_no__icontains=search) |
                Q(gvrma_no__icontains=search) |
                Q(good_part_number__icontains=search) |
                Q(part_order_number__icontains=search) |
                Q(so_number__icontains=search) |
                Q(sn_number__icontains=search) |
                Q(engineer_name__icontains=search)
            )

        return queryset

    @action(detail=False, methods=['get'])
    def filter_options(self, request):
        """Distinct, region-scoped values for the Warranty/Trade and Part
        Shipment Status filter dropdowns (so the UI reflects real data)."""
        qs = HPStockItem.objects.all()
        profile = getattr(request.user, 'userprofile', None)
        role = profile.role if profile else ''
        if role not in ['admin', 'super_admin', 'manager']:
            user_region = profile.region if profile else ''
            if user_region:
                qs = qs.filter(region=user_region)

        warranty_trade = sorted(
            v for v in qs.exclude(warranty_trade='')
            .values_list('warranty_trade', flat=True).distinct() if v
        )
        part_shipment_status = sorted(
            v for v in qs.exclude(part_shipment_status='')
            .values_list('part_shipment_status', flat=True).distinct() if v
        )
        return Response({
            'warranty_trade': warranty_trade,
            'part_shipment_status': part_shipment_status,
        })

    @action(detail=False, methods=['get'])
    def summary(self, request):
        queryset = self.get_queryset()
        total = queryset.count()
        active_total = queryset.exclude(status__in=['CLOSED', 'DC_CUT_REQUEST']).count()
        dc_cut_request_total = queryset.filter(status='DC_CUT_REQUEST').count()
        closed_total = queryset.filter(status='CLOSED').count()

        # Cases that have completed each workflow stage. The workflow is strictly
        # linear (WORK_STATUS branches to UNUSED/DEFECTIVE/DOA, all rejoining at
        # HANDOVER), so a case that sits at or past a stage has completed it.
        good_part_photo_done = STAGES_AT_OR_PAST['GOOD_PART_PHOTO']
        issued_done = STAGES_AT_OR_PAST['ISSUED']
        handover_done = STAGES_AT_OR_PAST['HANDOVER']
        return_part_photo_done = STAGES_AT_OR_PAST['RETURN_PART_PHOTO']

        # A date filter changes what the four stage cards mean: instead of "how many
        # cases sit at or past this stage" (all-time, status-based), they become "how
        # many cases transitioned INTO this stage on this calendar day" — read from
        # each item's transition_history timestamps. Without a date, the original
        # status-based counts are used unchanged.
        date_param = request.query_params.get('date', '').strip()
        STAGE_CARDS = [
            ('good_part_photo', 'GOOD_PART_PHOTO', good_part_photo_done),
            ('return_part_photo', 'RETURN_PART_PHOTO', return_part_photo_done),
            ('issued', 'ISSUED', issued_done),
            ('handover', 'HANDOVER', handover_done),
        ]

        if date_param:
            # Pull only the history (small JSON) for the rows in scope, then count in
            # Python — JSONField can't be filtered on nested timestamp dates portably
            # (sqlite dev vs postgres prod). region is fetched too for the breakdown.
            history_rows = list(queryset.values('region', 'transition_history'))

            stage_totals = {}
            region_stage = {}  # region -> {key: count}
            for key, target, _done in STAGE_CARDS:
                total_for_stage = 0
                for r in history_rows:
                    if stage_reached_on_date(r['transition_history'], target, date_param):
                        total_for_stage += 1
                        reg = r['region'] or ''
                        region_stage.setdefault(reg, {})
                        region_stage[reg][key] = region_stage[reg].get(key, 0) + 1
                stage_totals[key] = total_for_stage

            good_part_photo_total = stage_totals['good_part_photo']
            return_part_photo_total = stage_totals['return_part_photo']
            issued_total = stage_totals['issued']
            handover_total = stage_totals['handover']
        else:
            good_part_photo_total = queryset.filter(status__in=good_part_photo_done).count()
            return_part_photo_total = queryset.filter(status__in=return_part_photo_done).count()
            issued_total = queryset.filter(status__in=issued_done).count()
            handover_total = queryset.filter(status__in=handover_done).count()

        # Pending return: part taken by an engineer but not yet handed back. This is a
        # current-state figure ("who is still holding a part right now"), so it stays
        # status-based even when a date filter reshapes the other stage cards.
        pending_return_total = queryset.filter(status__in=PENDING_RETURN_STATUSES).count()

        # Part value counts are derived from price, which is super-admin-only, so
        # they are omitted entirely for everyone else.
        part_value_totals = {}
        profile = getattr(request.user, 'userprofile', None)
        if getattr(profile, 'role', '') == 'super_admin':
            # Part-value bands cover only OpenCall's current Active Part Cases �
            # the same set behind the region cards' Active number.
            active_ids = opencall_active_case_ids()
            scoped = queryset.filter(case_id__in=active_ids) if active_ids is not None else queryset.none()
            priced = annotate_part_price(scoped)
            part_value_totals = {
                f'part_value_{band.lower()}_total': priced.filter(part_value_band_q(band)).count()
                for band in PART_VALUE_BANDS
            }

        regions = list(queryset.values('region').annotate(
            total=Count('id'),
            active=Count('id', filter=~Q(status__in=['CLOSED', 'DC_CUT_REQUEST'])),
            dc_cut_request=Count('id', filter=Q(status='DC_CUT_REQUEST')),
            closed=Count('id', filter=Q(status='CLOSED')),
            good_part_photo=Count('id', filter=Q(status__in=good_part_photo_done)),
            return_part_photo=Count('id', filter=Q(status__in=return_part_photo_done)),
            issued=Count('id', filter=Q(status__in=issued_done)),
            handover=Count('id', filter=Q(status__in=handover_done)),
            pending_return=Count('id', filter=Q(status__in=PENDING_RETURN_STATUSES)),
        ).order_by('-total'))

        # With a date filter on, the four stage counts are day-based (from history),
        # so overwrite the per-region stage numbers with the day-based tallies.
        if date_param:
            for row in regions:
                by_stage = region_stage.get(row.get('region') or '', {})
                row['good_part_photo'] = by_stage.get('good_part_photo', 0)
                row['return_part_photo'] = by_stage.get('return_part_photo', 0)
                row['issued'] = by_stage.get('issued', 0)
                row['handover'] = by_stage.get('handover', 0)
        return Response({
            'total': total,
            'active_total': active_total,
            'dc_cut_request_total': dc_cut_request_total,
            'closed_total': closed_total,
            'good_part_photo_total': good_part_photo_total,
            'return_part_photo_total': return_part_photo_total,
            'issued_total': issued_total,
            'handover_total': handover_total,
            'pending_return_total': pending_return_total,
            **part_value_totals,
            'regions': regions
        })

    @action(detail=False, methods=['get'])
    def dc_cut_value_counts(self, request):
        """Part value band counts across DC Cut requests only.

        Backs the value cards above the DC Cut approval table, so the counts cover
        exactly the cases listed there. Derived from price, so super-admin only.
        Honours ?region=<name> like the list endpoint does.
        """
        profile = getattr(request.user, 'userprofile', None)
        if getattr(profile, 'role', '') != 'super_admin':
            return Response({})

        dc_requests = self.get_queryset().filter(status='DC_CUT_REQUEST')
        priced = annotate_part_price(dc_requests)
        counts = {
            f'part_value_{band.lower()}_total': priced.filter(part_value_band_q(band)).count()
            for band in PART_VALUE_BANDS
        }
        counts['total'] = dc_requests.count()
        return Response(counts)

    @action(detail=False, methods=['get'])
    def daily_region_counts(self, request):
        """Read-only: parts-call count per region, day by day.

        Each HP Stock item is a parts call synced from the opencall system, so
        grouping items by day + region gives the day-by-day, region-wise count of
        opencall parts calls. Optional query params: ?region=<name>, ?days=<N>
        (limit to the last N days). Returns rows plus per-day and per-region totals.
        """
        queryset = self.get_queryset()

        region = request.query_params.get('region')
        if region:
            queryset = queryset.filter(region=region)

        days = request.query_params.get('days')
        if days:
            try:
                since = timezone.now() - timedelta(days=int(days))
                queryset = queryset.filter(created_at__gte=since)
            except (TypeError, ValueError):
                pass

        rows = list(
            queryset
            .annotate(day=TruncDate('created_at'))
            .values('day', 'region')
            .annotate(count=Count('id'))
            .order_by('-day', 'region')
        )

        # Convenience roll-ups so the frontend can render a matrix without re-scanning.
        region_totals = {}
        day_totals = {}
        for r in rows:
            reg = r['region'] or 'unknown'
            day = r['day'].isoformat() if r['day'] else None
            r['day'] = day
            region_totals[reg] = region_totals.get(reg, 0) + r['count']
            if day:
                day_totals[day] = day_totals.get(day, 0) + r['count']

        return Response({
            'rows': rows,
            'region_totals': region_totals,
            'day_totals': day_totals,
            'total': sum(r['count'] for r in rows),
        })

    def perform_create(self, serializer):
        user = self.request.user
        profile = getattr(user, 'userprofile', None)
        role = profile.role if profile else ''
        
        if role not in ['admin', 'super_admin', 'manager']:
            user_region = profile.region if profile else ''
            serializer.save(region=user_region)
        else:
            serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        profile = getattr(user, 'userprofile', None)
        role = profile.role if profile else ''
        
        if role not in ['admin', 'super_admin', 'manager']:
            user_region = profile.region if profile else ''
            serializer.save(region=user_region)
        else:
            serializer.save()

    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        obj = self.get_object()
        user = request.user
        profile = getattr(user, "userprofile", None)
        role = profile.role if profile else ''
        
        # Region scoping: non-admins can only transition items in their own region
        if role not in ['admin', 'super_admin', 'manager']:
            user_region = profile.region if profile else ''
            if obj.region != user_region:
                return Response(
                    {"detail": "You can only transition HP stock items in your own region."},
                    status=403,
                )

        current_status = obj.status or "PENDING"
        
        HP_STOCK_TRANSITIONS = {
            "PENDING": ["STOCK_CHECK"],
            "STOCK_CHECK": ["GOOD_PART_PHOTO"],
            "GOOD_PART_PHOTO": ["ISSUED"],
            "ISSUED": ["WORK_STATUS"],
            "WORK_STATUS": ["UNUSED_RETURN", "DEFECTIVE_RETURN"],
            "UNUSED_RETURN": ["HANDOVER"],
            "DEFECTIVE_RETURN": ["HANDOVER"],
            "HANDOVER": ["RETURN_PART_PHOTO"],
            "RETURN_PART_PHOTO": ["DC_CUT_REQUEST"],
            "DC_CUT_REQUEST": ["CLOSED"],
        }
        
        requested_to_status = request.data.get("to_status")
        if requested_to_status:
            next_status = requested_to_status
        else:
            transitions = HP_STOCK_TRANSITIONS.get(current_status, [])
            next_status = transitions[0] if transitions else None

        if not next_status:
            return Response(
                {"detail": "No transition available for current status."},
                status=400,
            )

        if next_status == "CLOSED" and current_status == "DC_CUT_REQUEST":
            if not obj.dc_cut_approved:
                return Response(
                    {"detail": "DC Cut must be approved by the RMA team before closing the case."},
                    status=400,
                )

        engineer_name = (request.data.get("engineer_name") or "").strip()
        remarks = (request.data.get("remarks") or "").strip()
        dc_cut_request_message = request.data.get("dc_cut_request_message")
        if dc_cut_request_message is not None:
            obj.dc_cut_request_message = dc_cut_request_message.strip()

        # OTP Verification for ISSUED or HANDOVER
        if next_status in ["ISSUED", "HANDOVER"]:
            engineer_phone = (request.data.get("engineer_phone") or "").strip()
            otp = (request.data.get("otp") or "").strip()
            
            if not engineer_name:
                return Response({"detail": "Engineer Name is required for this transition."}, status=400)
            if not engineer_phone:
                return Response({"detail": "Engineer Phone Number is required for OTP verification."}, status=400)
            if not otp:
                return Response({"detail": "Verification OTP is required."}, status=400)
                
            # Verify OTP
            cleaned = _clean_phone(engineer_phone)
            if not verify_otp_local(cleaned, otp):
                return Response({"detail": "Invalid or expired OTP. Please try again."}, status=400)
                
            obj.engineer_phone = engineer_phone

        # Update engineer if passed
        if engineer_name:
            obj.engineer_name = engineer_name

        history = list(obj.transition_history or [])
        actor_name = f"{user.first_name} {user.last_name}".strip() or user.username
        
        entry = {
            "from_status": current_status,
            "to_status": next_status,
            "comment": remarks,
            "updated_by": actor_name,
            "timestamp": timezone.now().isoformat(),
        }
        
        if engineer_name:
            entry["engineer_name"] = engineer_name
        if next_status in ["ISSUED", "HANDOVER"] and getattr(obj, "engineer_phone", None):
            entry["engineer_phone"] = obj.engineer_phone

        # Every photo on this request, uploaded to storage once, in parallel.
        #
        # Two things used to make this slow on production (where storage is S3):
        # each upload went out one after another, and assigning the *file object*
        # to a FileField made obj.save() upload it a second time. Assigning the
        # saved name instead just records the path, so each file crosses the wire
        # once.
        pending_uploads = []  # (field_name or None, history_key, label, file)

        good_part_image = request.FILES.get("good_part_image")
        if good_part_image:
            field = None
            if next_status == "GOOD_PART_PHOTO":
                field = "good_part_image"
            elif next_status == "RETURN_PART_PHOTO":
                field = "return_part_image"
            pending_uploads.append((field, "image", None, good_part_image))

        good_part_image_back = request.FILES.get("good_part_image_back")
        if good_part_image_back:
            field = "good_part_image_back" if next_status == "GOOD_PART_PHOTO" else None
            pending_uploads.append((field, "image_back", None, good_part_image_back))

        # Return part photo categories (all optional, only on RETURN_PART_PHOTO)
        return_photo_fields = [
            ("return_part_ct_image", "Part CT Image"),
            ("return_box_front_image", "Box with Part Front Image"),
            ("return_box_back_image", "Box with Part Back Image"),
            ("return_box_corner_right_image", "Box with Part Corner Right Side Image"),
            ("return_box_corner_left_image", "Box with Part Corner Left Side Image"),
            ("return_box_corner_top_image", "Box with Part Corner Top Side Image"),
            ("return_box_corner_bottom_image", "Box with Part Corner Bottom Side Image"),
            ("return_option_image_1", "Option Image 1"),
            ("return_option_image_2", "Option Image 2"),
            ("return_option_image_3", "Option Image 3"),
        ]
        if next_status == "RETURN_PART_PHOTO":
            for field_name, label in return_photo_fields:
                uploaded = request.FILES.get(field_name)
                if uploaded:
                    pending_uploads.append((field_name, "return_images", label, uploaded))

        uploaded_return_fields = []
        if pending_uploads:
            results = _upload_images_parallel([f for _, _, _, f in pending_uploads])

            return_images = []
            for (field_name, history_key, label, _), (saved_name, url) in zip(pending_uploads, results):
                if field_name:
                    # The saved name, not the file object — assigning the object would
                    # make obj.save() re-upload it.
                    setattr(obj, field_name, saved_name)
                    if field_name.startswith("return_") and field_name != "return_part_image":
                        uploaded_return_fields.append(field_name)
                if history_key == "return_images":
                    return_images.append({"label": label, "url": url})
                else:
                    entry[history_key] = url
            if return_images:
                entry["return_images"] = return_images

        history.append(entry)
        obj.status = next_status
        obj.transition_history = history
        
        # Save modifications
        save_fields = ["status", "transition_history"]
        if engineer_name:
            save_fields.append("engineer_name")
        if next_status in ["ISSUED", "HANDOVER"] and getattr(obj, "engineer_phone", None):
            save_fields.append("engineer_phone")
        if getattr(obj, "good_part_image", None):
            save_fields.append("good_part_image")
        if getattr(obj, "good_part_image_back", None):
            save_fields.append("good_part_image_back")
        if getattr(obj, "return_part_image", None):
            save_fields.append("return_part_image")
        save_fields.extend(uploaded_return_fields)
        if dc_cut_request_message is not None:
            save_fields.append("dc_cut_request_message")
            
        obj.save(update_fields=save_fields)

        return Response(HPStockItemSerializer(obj).data)

    @action(detail=True, methods=['post'])
    def send_otp(self, request, pk=None):
        obj = self.get_object()
        phone = (request.data.get("phone") or "").strip()
        target_status = (request.data.get("to_status") or "").strip()
        
        if not phone:
            return Response({"detail": "Phone number is required."}, status=400)
            
        cleaned = _clean_phone(phone)
        if len(cleaned) != 10:
            return Response({"detail": "Invalid phone number. Must be a 10-digit Indian mobile number (e.g. 9876543210)."}, status=400)
            
        # Generate 6-digit OTP
        otp = str(random.randint(100000, 999999))
        
        # Remove any existing OTPs for this phone, then store the new one
        OTPVerification.objects.filter(phone=cleaned).delete()
        OTPVerification.objects.create(
            phone=cleaned,
            otp=otp,
            expires_at=timezone.now() + timedelta(minutes=5)
        )
        
        # Prepare message
        status_label = "Part Taken" if target_status == "ISSUED" else "Handover"
        message = f"Your OTP for HP Stock {status_label} (Case: {obj.case_id}) is {otp}. Valid for 5 minutes. Do not share."
        
        # Prefilled WhatsApp URL
        whatsapp_url = f"https://wa.me/91{cleaned}?text={urllib.parse.quote(message)}"
        
        return Response({
            "otp": otp,  # Return it so frontend can display or prefill for testing/fallback
            "whatsapp_url": whatsapp_url,
            "detail": f"OTP {otp} generated successfully. Please send it to the engineer via WhatsApp."
        })

    @action(detail=True, methods=['post'])
    def approve_dc_cut(self, request, pk=None):
        obj = self.get_object()
        obj.dc_cut_approved = True
        obj.save(update_fields=['dc_cut_approved'])
        
        # Add transition history entry
        history = list(obj.transition_history or [])
        actor_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
        
        entry = {
            "from_status": obj.status,
            "to_status": obj.status,
            "comment": "DC Cut Approved by RMA Team",
            "updated_by": actor_name,
            "timestamp": timezone.now().isoformat(),
        }
        history.append(entry)
        obj.transition_history = history
        obj.save(update_fields=['transition_history'])
        
        return Response(HPStockItemSerializer(obj).data)

    @action(detail=True, methods=['post'])
    def send_dc_cut_chat_message(self, request, pk=None):
        obj = self.get_object()
        message = (request.data.get("message") or "").strip()
        if not message:
            return Response({"detail": "Message content cannot be empty."}, status=400)
        
        chat = list(obj.dc_cut_chat or [])
        actor_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
        
        entry = {
            "sender": actor_name,
            "message": message,
            "timestamp": timezone.now().isoformat(),
        }
        chat.append(entry)
        obj.dc_cut_chat = chat
        obj.save(update_fields=['dc_cut_chat'])
        
        return Response(HPStockItemSerializer(obj).data)


class HPStockRMAPartViewSet(viewsets.ModelViewSet):
    serializer_class = HPStockRMAPartSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = HPStockRMAPart.objects.all()
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(part_number__icontains=search) |
                Q(description__icontains=search) |
                Q(category__icontains=search) |
                Q(hsn_code__icontains=search)
            )
        return queryset

    @action(detail=False, methods=['delete'])
    def delete_all(self, request):
        count, _ = HPStockRMAPart.objects.all().delete()
        return Response({"detail": f"Successfully deleted all {count} parts from the catalog."})

    @action(detail=False, methods=['post'])
    def import_excel(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({"detail": "No file was uploaded."}, status=400)
        
        try:
            import pandas as pd
            df = pd.read_excel(file_obj)
        except Exception as e:
            return Response({"detail": f"Failed to parse Excel file: {str(e)}"}, status=400)
        
        total_excel_rows = len(df)
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]
        
        if 'part' not in df.columns:
            return Response({"detail": "Excel sheet must contain a 'Part' (part number) column."}, status=400)
            
        success_count = 0
        skipped_empty = 0
        errors = []
        
        from datetime import datetime
        
        def clean_val(val):
            if pd.isna(val):
                return ""
            if isinstance(val, float):
                if val.is_integer():
                    return str(int(val))
                return str(val)
            val_str = str(val).strip()
            if val_str.endswith('.0'):
                try:
                    f_val = float(val_str)
                    if f_val.is_integer():
                        return str(int(f_val))
                except ValueError:
                    pass
            return val_str

        # Clear catalog first
        HPStockRMAPart.objects.all().delete()
        
        parts_to_create = []
        
        for idx, row in df.iterrows():
            part_num = clean_val(row.get('part'))
            if not part_num or part_num == 'nan':
                skipped_empty += 1
                continue
            
            desc = clean_val(row.get('part_description'))
            cat = clean_val(row.get('category'))
            
            price_val = 0.00
            try:
                raw_price = row.get('price', 0.00)
                if not pd.isna(raw_price):
                    price_val = float(raw_price)
            except:
                pass
                
            hsn = clean_val(row.get('hsn_code'))
            igst = clean_val(row.get('igst'))
            cgst = clean_val(row.get('cgst'))
            sgst = clean_val(row.get('sgst'))
            eosl = clean_val(row.get('eosl_flag'))
            
            val_date = None
            raw_validity = row.get('validity')
            if raw_validity and not pd.isna(raw_validity):
                if isinstance(raw_validity, datetime):
                    val_date = raw_validity.date()
                else:
                    date_str = str(raw_validity).strip()
                    for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
                        try:
                            val_date = datetime.strptime(date_str, fmt).date()
                            break
                        except ValueError:
                            continue
            
            p_status = clean_val(row.get('parts_status'))

            parts_to_create.append(HPStockRMAPart(
                part_number=part_num,
                description=desc,
                category=cat,
                price=price_val,
                hsn_code=hsn,
                igst=igst,
                cgst=cgst,
                sgst=sgst,
                eosl_flag=eosl,
                validity=val_date,
                parts_status=p_status
            ))

        # Perform bulk insert
        try:
            HPStockRMAPart.objects.bulk_create(parts_to_create, batch_size=5000)
            success_count = len(parts_to_create)
        except Exception as ex:
            return Response({"detail": f"Failed to bulk insert records to database: {str(ex)}"}, status=500)
                
        # Prepare response details
        detail_msg = (
            f"Processed {total_excel_rows} rows from Excel. "
            f"Successfully imported all {success_count} parts. "
            f"Skipped {skipped_empty} empty/invalid rows."
        )
        
        return Response({
            "detail": detail_msg,
            "total_excel_rows": total_excel_rows,
            "success_count": success_count,
            "skipped_empty": skipped_empty,
            "errors": errors
        })


class OpencallPartsCountViewSet(viewsets.ModelViewSet):
    """Region-wise OpenCall "Active Part Cases" count, pushed from OpenCall. Read-only in UI."""
    queryset = OpencallPartsCount.objects.all().order_by('-report_date', 'region')
    serializer_class = OpencallPartsCountSerializer
    pagination_class = None

    @action(detail=False, methods=['post'])
    def bulk_replace_active_cases(self, request):
        """OpenCall pushes the full active part-case id list for a report date."""
        payload = request.data
        rows = payload if isinstance(payload, list) else payload.get('rows', [])
        if not rows:
            return Response({'written': 0})
        report_date = rows[0].get('report_date')
        if not report_date:
            return Response({'written': 0})
        OpencallActivePartCase.objects.filter(report_date=report_date).delete()
        OpencallActivePartCase.objects.bulk_create([
            OpencallActivePartCase(
                report_date=report_date,
                case_id=str(r.get('case_id') or ''),
                region=(r.get('region') or ''),
            )
            for r in rows if r.get('case_id')
        ], ignore_conflicts=True)
        return Response({'written': len(rows)})

    @action(detail=False, methods=['post'])
    def bulk_upsert(self, request):
        payload = request.data
        rows = payload if isinstance(payload, list) else payload.get('rows', [])
        written = 0
        for r in rows:
            report_date = r.get('report_date')
            if not report_date:
                continue
            OpencallPartsCount.objects.update_or_create(
                report_date=report_date,
                region=(r.get('region') or ''),
                defaults={'count': r.get('count') or 0},
            )
            written += 1
        return Response({'written': written})
