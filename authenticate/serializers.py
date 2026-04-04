from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import User
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import serializers

from .models import UserProfile

UserModel = get_user_model()


def ensure_user_profile(user):
    default_role = UserProfile.ADMIN if user.is_staff or user.is_superuser else UserProfile.EMPLOYEE
    profile, created = UserProfile.objects.get_or_create(
        user=user,
        defaults={"role": default_role},
    )

    if not created and default_role == UserProfile.ADMIN and profile.role != UserProfile.ADMIN:
        profile.role = UserProfile.ADMIN
        profile.save(update_fields=["role"])

    return profile


class AuthUserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "role"]

    def get_role(self, obj):
        return ensure_user_profile(obj).role


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    role = serializers.ChoiceField(
        choices=UserProfile.ROLE_CHOICES,
        required=False,
        default=UserProfile.EMPLOYEE,
    )

    class Meta:
        model = User
        fields = ["username", "password", "first_name", "last_name", "email", "role"]

    def validate_role(self, value):
        request = self.context.get("request")
        if value == UserProfile.ADMIN and (not request or not request.user.is_authenticated or not getattr(request.user, "userprofile", None) or request.user.userprofile.role != UserProfile.ADMIN):
            raise serializers.ValidationError("Only admins can create admin users.")
        return value

    def create(self, validated_data):
        role = validated_data.pop("role", UserProfile.EMPLOYEE)
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        profile = ensure_user_profile(user)
        if profile.role != role:
            profile.role = role
            profile.save(update_fields=["role"])
        return user


class UpdateProfileSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role"]
        read_only_fields = ["username", "role"]

    def get_role(self, obj):
        return ensure_user_profile(obj).role


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