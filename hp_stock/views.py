from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from .models import HPStockItem, HPStockRMAPart, OpencallPartsCount
from .serializers import HPStockItemSerializer, HPStockRMAPartSerializer, OpencallPartsCountSerializer

from rest_framework.pagination import PageNumberPagination
import math
import re
import random
import urllib.parse
from datetime import timedelta
from material.models import OTPVerification

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

        if date_param:
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
        regions = queryset.values('region').annotate(
            total=Count('id'),
            active=Count('id', filter=~Q(status__in=['CLOSED', 'DC_CUT_REQUEST'])),
            dc_cut_request=Count('id', filter=Q(status='DC_CUT_REQUEST')),
            closed=Count('id', filter=Q(status='CLOSED'))
        ).order_by('-total')
        return Response({
            'total': total,
            'active_total': active_total,
            'dc_cut_request_total': dc_cut_request_total,
            'closed_total': closed_total,
            'regions': list(regions)
        })

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

        good_part_image = request.FILES.get("good_part_image")
        if good_part_image:
            from django.core.files.storage import default_storage
            file_name = default_storage.save(f"hp_stock_images/{good_part_image.name}", good_part_image)
            image_url = default_storage.url(file_name)
            entry["image"] = image_url
            
            if next_status == "GOOD_PART_PHOTO":
                obj.good_part_image = good_part_image
            elif next_status == "RETURN_PART_PHOTO":
                obj.return_part_image = good_part_image

        good_part_image_back = request.FILES.get("good_part_image_back")
        if good_part_image_back:
            from django.core.files.storage import default_storage
            file_name = default_storage.save(f"hp_stock_images/{good_part_image_back.name}", good_part_image_back)
            image_url_back = default_storage.url(file_name)
            entry["image_back"] = image_url_back
            
            if next_status == "GOOD_PART_PHOTO":
                obj.good_part_image_back = good_part_image_back

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
        uploaded_return_fields = []
        if next_status == "RETURN_PART_PHOTO":
            from django.core.files.storage import default_storage
            return_images = []
            for field_name, label in return_photo_fields:
                uploaded = request.FILES.get(field_name)
                if uploaded:
                    saved_name = default_storage.save(f"hp_stock_images/{uploaded.name}", uploaded)
                    setattr(obj, field_name, saved_name)
                    uploaded_return_fields.append(field_name)
                    return_images.append({"label": label, "url": default_storage.url(saved_name)})
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
