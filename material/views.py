import logging
import re

import requests
from django.db.models import Q, Sum
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from authenticate.models import UserProfile
from .models import MaterialTrack
from .serializers import MaterialSerializer
from .sms import send_otp_sms, verify_otp

logger = logging.getLogger(__name__)


def _clean_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 13 and digits.startswith("091"):
        digits = digits[3:]
    return digits


class MaterialTrackList(generics.ListCreateAPIView):
    serializer_class = MaterialSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        profile = getattr(user, "userprofile", None)

        # Base queryset by role
        if profile and profile.is_super_admin:
            qs = MaterialTrack.objects.all()
        elif profile and profile.region:
            qs = MaterialTrack.objects.filter(region=profile.region)
        else:
            qs = MaterialTrack.objects.filter(user=user)

        # --- Filters from query params ---
        params = self.request.query_params

        search = params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(cust_name__icontains=search)
                | Q(case_id__icontains=search)
                | Q(product_name__icontains=search)
                | Q(part_number__icontains=search)
                | Q(serial_number__icontains=search)
                | Q(engineer_name__icontains=search)
                | Q(cust_contact__icontains=search)
            )

        service_type = params.get("service_type", "").strip()
        if service_type:
            qs = qs.filter(service_type=service_type)

        call_status = params.get("call_status", "").strip()
        if call_status:
            qs = qs.filter(call_status=call_status)

        # Region filter (super admin only — sub-admin is already scoped)
        region = params.get("region", "").strip()
        if region and profile and profile.is_super_admin:
            qs = qs.filter(region=region)

        # Ordering
        ordering = params.get("ordering", "-created_at")
        allowed = {
            "case_id", "-case_id",
            "cust_name", "-cust_name",
            "qty", "-qty",
            "created_at", "-created_at",
            "arrival_date", "-arrival_date",
        }
        if ordering in allowed:
            qs = qs.order_by(ordering)

        return qs

    def perform_create(self, serializer):
        user = self.request.user
        profile = getattr(user, "userprofile", None)
        region = profile.region if profile else None
        serializer.save(user=user, region=region)


class MaterialTrackDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MaterialSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        profile = getattr(user, "userprofile", None)

        if profile and profile.is_super_admin:
            return MaterialTrack.objects.all()

        if profile and profile.region:
            return MaterialTrack.objects.filter(region=profile.region)

        return MaterialTrack.objects.filter(user=user)


class SendOTPView(APIView):
    """Send OTP to customer's phone for verification via Fast2SMS OTP route."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        phone = request.data.get("phone", "").strip()
        if not phone:
            return Response(
                {"detail": "Phone number is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cleaned = _clean_phone(phone)
        if len(cleaned) != 10:
            return Response(
                {"detail": "Invalid phone number. Must be a 10-digit Indian mobile number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            send_otp_sms(cleaned)
            return Response({"detail": "OTP sent successfully."})
        except requests.exceptions.HTTPError as e:
            body = e.response.text if e.response is not None else ""
            logger.error("Fast2SMS error: %s | body: %s", e, body)
            return Response(
                {"detail": f"SMS gateway error: {body or str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as e:
            logger.exception("Failed to send OTP")
            return Response(
                {"detail": f"Failed to send OTP: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class VerifyOTPAndSubmitView(APIView):
    """Verify OTP and save material record to database."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        phone = request.data.get("phone", "").strip()
        otp = request.data.get("otp", "").strip()
        form_data = request.data.get("form_data", {})

        if not phone or not otp:
            return Response(
                {"detail": "Phone number and OTP are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cleaned = _clean_phone(phone)

        # Verify OTP
        if not verify_otp(cleaned, otp):
            return Response(
                {"detail": "Invalid or expired OTP."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Save material record
        serializer = MaterialSerializer(data=form_data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        profile = getattr(user, "userprofile", None)
        region = profile.region if profile else None
        material = serializer.save(user=user, region=region)

        return Response(
            MaterialSerializer(material).data,
            status=status.HTTP_201_CREATED,
        )


class DashboardStatsView(APIView):
    """
    Super admin: returns overall stats + per-region breakdown.
    Sub admin: returns only their region's stats.
    """
    permission_classes = [permissions.IsAuthenticated]

    def _region_stats(self, qs, label=None):
        total = qs.count()
        total_qty = qs.aggregate(s=Sum("qty"))["s"] or 0
        pending = qs.filter(call_status="pending").count()
        closed = qs.filter(call_status="closed").count()
        taken = qs.filter(call_status="taken_for_service").count()
        return {
            "region": label,
            "total_materials": total,
            "total_qty": total_qty,
            "pending": pending,
            "closed": closed,
            "taken_for_service": taken,
        }

    def get(self, request):
        profile = getattr(request.user, "userprofile", None)

        if profile and profile.is_super_admin:
            overall = self._region_stats(MaterialTrack.objects.all(), label="all")
            regions = []
            for code, label in UserProfile.REGION_CHOICES:
                qs = MaterialTrack.objects.filter(region=code)
                regions.append(self._region_stats(qs, label=code))
            return Response({"overall": overall, "regions": regions})

        region = profile.region if profile else None
        if region:
            qs = MaterialTrack.objects.filter(region=region)
        else:
            qs = MaterialTrack.objects.filter(user=request.user)
        return Response({"overall": self._region_stats(qs, label=region), "regions": []})
