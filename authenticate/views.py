from django.contrib.auth.models import User
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from .models import UserProfile
from .serializers import (
    AuthUserSerializer,
    LoginSerializer,
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
