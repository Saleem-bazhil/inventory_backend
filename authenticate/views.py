from django.contrib.auth.models import User
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from .models import Engineer, UserProfile
from .serializers import (
    AuthUserSerializer,
    EngineerCreateUpdateSerializer,
    EngineerSerializer,
    LoginSerializer,
    ManagerSerializer,
    RegisterSerializer,
    SubAdminSerializer,
    UpdateProfileSerializer,
)


def build_auth_response(user):
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": AuthUserSerializer(user).data,
    }


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(build_auth_response(user), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(build_auth_response(serializer.validated_data), status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(AuthUserSerializer(request.user).data, status=status.HTTP_200_OK)

    def put(self, request):
        serializer = UpdateProfileSerializer(request.user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AuthUserSerializer(request.user).data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = UpdateProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AuthUserSerializer(request.user).data, status=status.HTTP_200_OK)


class RefreshView(TokenRefreshView):
    permission_classes = [permissions.AllowAny]


# ── Engineers list (for assignment dropdowns) ──────────────────────

class EngineersListView(APIView):
    """
    Return active engineers filtered by the logged-in user's region.
    Super-admin / admin see all engineers. Sub-admin see their region only.
    Accepts optional ?region= query param for admin filtering.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = getattr(request.user, "userprofile", None)
        is_admin = profile and profile.is_admin if profile else False

        qs = Engineer.objects.filter(status="active")

        if is_admin:
            # Admin can optionally filter by region
            region_filter = request.query_params.get("region", "").strip()
            if region_filter:
                qs = qs.filter(region=region_filter)
        elif profile and profile.region:
            # Non-admin: only their region
            qs = qs.filter(region=profile.region)
        else:
            # No profile/region: return empty
            qs = qs.none()

        serializer = EngineerSerializer(qs, many=True)
        return Response(serializer.data)


# ── Engineer CRUD (sub-admin manages engineers in their region) ───


class EngineerListCreateView(APIView):
    """
    GET: list engineers (region-scoped).
    POST: create a new engineer (region auto-assigned from user).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = getattr(request.user, "userprofile", None)
        is_admin = profile and profile.is_admin if profile else False

        qs = Engineer.objects.all()

        if is_admin:
            region_filter = request.query_params.get("region", "").strip()
            if region_filter:
                qs = qs.filter(region=region_filter)
        elif profile and profile.region:
            qs = qs.filter(region=profile.region)
        else:
            qs = qs.none()

        serializer = EngineerSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        profile = getattr(request.user, "userprofile", None)
        is_admin = profile and profile.is_admin if profile else False

        serializer = EngineerCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Non-admin: force region to user's region
        region = serializer.validated_data.get("region")
        if not is_admin:
            if not profile or not profile.region:
                return Response(
                    {"detail": "Your account has no region assigned."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            region = profile.region
            serializer.validated_data["region"] = region

        engineer = serializer.save(created_by=request.user)
        return Response(
            EngineerSerializer(engineer).data,
            status=status.HTTP_201_CREATED,
        )


class EngineerDetailView(APIView):
    """GET / PUT / DELETE a single engineer."""
    permission_classes = [permissions.IsAuthenticated]

    def _get_engineer(self, request, pk):
        try:
            engineer = Engineer.objects.get(pk=pk)
        except Engineer.DoesNotExist:
            return None

        profile = getattr(request.user, "userprofile", None)
        is_admin = profile and profile.is_admin if profile else False

        if is_admin:
            return engineer
        if profile and profile.region and engineer.region == profile.region:
            return engineer
        return None

    def get(self, request, pk):
        engineer = self._get_engineer(request, pk)
        if not engineer:
            return Response({"detail": "Engineer not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(EngineerSerializer(engineer).data)

    def put(self, request, pk):
        engineer = self._get_engineer(request, pk)
        if not engineer:
            return Response({"detail": "Engineer not found."}, status=status.HTTP_404_NOT_FOUND)

        profile = getattr(request.user, "userprofile", None)
        is_admin = profile and profile.is_admin if profile else False

        serializer = EngineerCreateUpdateSerializer(engineer, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        # Non-admin cannot change region
        if not is_admin and "region" in serializer.validated_data:
            serializer.validated_data["region"] = engineer.region

        serializer.save()
        return Response(EngineerSerializer(engineer).data)

    def delete(self, request, pk):
        engineer = self._get_engineer(request, pk)
        if not engineer:
            return Response({"detail": "Engineer not found."}, status=status.HTTP_404_NOT_FOUND)

        # Soft-delete: set inactive
        engineer.status = "inactive"
        engineer.save(update_fields=["status"])
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Super Admin: manage sub-admins ──────────────────────────────────


class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        profile = getattr(request.user, "userprofile", None)
        return profile and profile.is_super_admin


class SubAdminListCreateView(APIView):
    """GET: list all sub-admins. POST: create a new sub-admin."""
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        users = User.objects.filter(userprofile__role=UserProfile.SUB_ADMIN).select_related("userprofile")
        data = [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "region": u.userprofile.region,
                "region_display": u.userprofile.get_region_display() if u.userprofile.region else "",
                "is_active": u.is_active,
            }
            for u in users
        ]
        return Response(data)

    def post(self, request):
        serializer = SubAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        profile = user.userprofile
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "region": profile.region,
                "region_display": profile.get_region_display() if profile.region else "",
                "is_active": user.is_active,
            },
            status=status.HTTP_201_CREATED,
        )


# ── Super Admin: manage managers ──────────────────────────────────


class ManagerListCreateView(APIView):
    """GET: list all managers. POST: create a new manager."""
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        users = User.objects.filter(userprofile__role=UserProfile.MANAGER).select_related("userprofile")
        data = [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "region": u.userprofile.region,
                "region_display": u.userprofile.get_region_display() if u.userprofile.region else "",
                "is_active": u.is_active,
            }
            for u in users
        ]
        return Response(data)

    def post(self, request):
        serializer = ManagerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        profile = user.userprofile
        return Response(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "region": profile.region,
                "region_display": profile.get_region_display() if profile.region else "",
                "is_active": user.is_active,
            },
            status=status.HTTP_201_CREATED,
        )


class ManagerDetailView(APIView):
    """PUT: update manager. DELETE: deactivate manager."""
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def _get_user(self, pk):
        try:
            return User.objects.select_related("userprofile").get(pk=pk, userprofile__role=UserProfile.MANAGER)
        except User.DoesNotExist:
            return None

    def put(self, request, pk):
        user = self._get_user(pk)
        if not user:
            return Response({"detail": "Manager not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ManagerSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        if "username" in d:
            user.username = d["username"]
        if "email" in d:
            user.email = d["email"]
        if "first_name" in d:
            user.first_name = d["first_name"]
        if "last_name" in d:
            user.last_name = d["last_name"]
        if "password" in d:
            user.set_password(d["password"])
        user.save()
        if "region" in d:
            user.userprofile.region = d["region"] or None
            user.userprofile.save(update_fields=["region"])
        profile = user.userprofile
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "region": profile.region,
            "region_display": profile.get_region_display() if profile.region else "",
            "is_active": user.is_active,
        })

    def delete(self, request, pk):
        user = self._get_user(pk)
        if not user:
            return Response({"detail": "Manager not found."}, status=status.HTTP_404_NOT_FOUND)
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubAdminDetailView(APIView):
    """PUT: update sub-admin. DELETE: deactivate sub-admin."""
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def _get_user(self, pk):
        try:
            return User.objects.select_related("userprofile").get(pk=pk, userprofile__role=UserProfile.SUB_ADMIN)
        except User.DoesNotExist:
            return None

    def put(self, request, pk):
        user = self._get_user(pk)
        if not user:
            return Response({"detail": "Sub-admin not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SubAdminSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        if "username" in d:
            user.username = d["username"]
        if "email" in d:
            user.email = d["email"]
        if "first_name" in d:
            user.first_name = d["first_name"]
        if "last_name" in d:
            user.last_name = d["last_name"]
        if "password" in d:
            user.set_password(d["password"])
        user.save()
        if "region" in d:
            user.userprofile.region = d["region"]
            user.userprofile.save(update_fields=["region"])
        profile = user.userprofile
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "region": profile.region,
            "region_display": profile.get_region_display() if profile.region else "",
            "is_active": user.is_active,
        })

    def delete(self, request, pk):
        user = self._get_user(pk)
        if not user:
            return Response({"detail": "Sub-admin not found."}, status=status.HTTP_404_NOT_FOUND)
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)
