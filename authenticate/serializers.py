from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import User
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import serializers

from .models import Engineer, UserProfile

UserModel = get_user_model()


def ensure_user_profile(user):
    default_role = UserProfile.SUPER_ADMIN if user.is_superuser else UserProfile.SUB_ADMIN
    profile, created = UserProfile.objects.get_or_create(
        user=user,
        defaults={"role": default_role},
    )

    if not created and user.is_superuser and profile.role != UserProfile.SUPER_ADMIN:
        profile.role = UserProfile.SUPER_ADMIN
        profile.save(update_fields=["role"])

    return profile


class AuthUserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    region = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "role", "region"]

    def get_role(self, obj):
        return ensure_user_profile(obj).role

    def get_region(self, obj):
        return ensure_user_profile(obj).region


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    role = serializers.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        required=False,
        default=UserProfile.SUB_ADMIN,
    )
    region = serializers.ChoiceField(
        choices=UserProfile.REGION_CHOICES,
        required=False,
        allow_blank=True,
        default="",
    )

    class Meta:
        model = User
        fields = ["username", "password", "first_name", "last_name", "email", "role", "region"]

    def validate_role(self, value):
        request = self.context.get("request")
        if value == UserProfile.SUPER_ADMIN and (
            not request
            or not request.user.is_authenticated
            or not getattr(request.user, "userprofile", None)
            or request.user.userprofile.role != UserProfile.SUPER_ADMIN
        ):
            raise serializers.ValidationError("Only super admins can create super admin users.")
        return value

    def validate(self, data):
        role = data.get("role", UserProfile.SUB_ADMIN)
        region = data.get("region", "")
        if role == UserProfile.SUB_ADMIN and not region:
            raise serializers.ValidationError({"region": "Region is required for sub-admin users."})
        return data

    def create(self, validated_data):
        role = validated_data.pop("role", UserProfile.SUB_ADMIN)
        region = validated_data.pop("region", "")
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        profile = ensure_user_profile(user)
        profile.role = role
        profile.region = region if role == UserProfile.SUB_ADMIN else None
        profile.save(update_fields=["role", "region"])
        return user


class UpdateProfileSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField(read_only=True)
    region = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "region"]
        read_only_fields = ["username", "role", "region"]

    def get_role(self, obj):
        return ensure_user_profile(obj).role

    def get_region(self, obj):
        return ensure_user_profile(obj).region


class SubAdminSerializer(serializers.Serializer):
    """Used by super admin to create / update sub-admins."""
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=6, required=False)
    email = serializers.EmailField(required=False, default="", allow_blank=True)
    first_name = serializers.CharField(required=False, default="", allow_blank=True)
    last_name = serializers.CharField(required=False, default="", allow_blank=True)
    region = serializers.ChoiceField(choices=UserProfile.REGION_CHOICES)

    def validate_username(self, value):
        if self.instance is None and User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def create(self, validated_data):
        region = validated_data.pop("region")
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "Password is required when creating a sub-admin."})
        user = User.objects.create_user(password=password, is_staff=True, **validated_data)
        profile = ensure_user_profile(user)
        profile.role = UserProfile.SUB_ADMIN
        profile.region = region
        profile.save(update_fields=["role", "region"])
        return user


class ManagerSerializer(serializers.Serializer):
    """Used by super admin to create / update managers (part approval role)."""
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=6, required=False)
    email = serializers.EmailField(required=False, default="", allow_blank=True)
    first_name = serializers.CharField(required=False, default="", allow_blank=True)
    last_name = serializers.CharField(required=False, default="", allow_blank=True)
    region = serializers.ChoiceField(
        choices=UserProfile.REGION_CHOICES,
        required=False,
        allow_blank=True,
        default="",
    )

    def validate_username(self, value):
        if self.instance is None and User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def create(self, validated_data):
        region = validated_data.pop("region", "")
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "Password is required when creating a manager."})
        user = User.objects.create_user(password=password, is_staff=True, **validated_data)
        profile = ensure_user_profile(user)
        profile.role = UserProfile.MANAGER
        profile.region = region or None
        profile.save(update_fields=["role", "region"])
        return user


# ---------------------------------------------------------------------------
# Engineer
# ---------------------------------------------------------------------------

class EngineerSerializer(serializers.ModelSerializer):
    region_display = serializers.CharField(source="get_region_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Engineer
        fields = [
            "id", "name", "email", "phone", "region", "region_display",
            "status", "status_display", "created_by", "created_by_name",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None


class EngineerCreateUpdateSerializer(serializers.ModelSerializer):
    region = serializers.CharField(required=False, allow_blank=True, default="")

    class Meta:
        model = Engineer
        fields = ["name", "email", "phone", "region", "status"]

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Engineer name is required.")
        return value.strip()

    def validate_region(self, value):
        if not value:
            return value
        valid_regions = [r[0] for r in UserProfile.REGION_CHOICES]
        if value not in valid_regions:
            raise serializers.ValidationError(f"'{value}' is not a valid region.")
        return value


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        username = data["username"].strip()
        password = data["password"]

        resolved_username = username
        if username:
            matched_user = UserModel.objects.filter(email__iexact=username).only("username").first()
            if matched_user:
                resolved_username = matched_user.username

        user = authenticate(username=resolved_username, password=password)
        if not user:
            raise AuthenticationFailed("Invalid username or password.")
        if not user.is_active:
            raise AuthenticationFailed("User account is disabled.")

        ensure_user_profile(user)
        return user
