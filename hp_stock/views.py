from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Count, Q
from django.utils import timezone
from .models import HPStockItem, HPStockRMAPart
from .serializers import HPStockItemSerializer, HPStockRMAPartSerializer

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

        if search:
            queryset = queryset.filter(
                Q(case_id__icontains=search) |
                Q(work_order_id__icontains=search) |
                Q(delivery_no__icontains=search) |
                Q(service_event_no__icontains=search) |
                Q(material_order_no__icontains=search) |
                Q(hp_sales_order_no__icontains=search) |
                Q(gvrma_no__icontains=search) |
                Q(engineer_name__icontains=search)
            )

        return queryset

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

        engineer_name = (request.data.get("engineer_name") or "").strip()
        remarks = (request.data.get("remarks") or "").strip()

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
        if getattr(obj, "return_part_image", None):
            save_fields.append("return_part_image")
            
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
