"""
Serializers for the accounts app.
"""

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import AuditLog, StaffAttendance, User


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT token serializer that includes user info in response.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Add custom claims
        token["username"] = user.username
        token["role"] = user.role
        token["full_name"] = user.get_full_name()
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        # Add user info to response
        data["user"] = {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "full_name": self.user.get_full_name(),
            "role": self.user.role,
            "role_display": self.user.get_role_display(),
        }
        return data


class PINLoginSerializer(serializers.Serializer):
    """
    Serializer for PIN-based quick login.
    """

    employee_id = serializers.CharField()
    pin = serializers.CharField(max_length=6)

    def validate(self, attrs):
        employee_id = attrs.get("employee_id")
        pin = attrs.get("pin")

        try:
            user = User.objects.get(employee_id=employee_id, is_active=True)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid employee ID or PIN.")

        if user.pin != pin:
            raise serializers.ValidationError("Invalid employee ID or PIN.")

        attrs["user"] = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for User model.
    """

    role_display = serializers.CharField(source="get_role_display", read_only=True)
    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "role",
            "role_display",
            "employee_id",
            "profile_photo",
            "is_on_duty",
            "current_shift",
            "is_active",
            "date_joined",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "date_joined", "created_at", "updated_at"]


class UserCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new users.
    """

    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "employee_id",
            "pin",
            "password",
            "confirm_password",
        ]

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("confirm_password"):
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating users.
    """

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "role",
            "employee_id",
            "pin",
            "profile_photo",
            "is_active",
        ]


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for changing password.
    """

    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


class StaffAttendanceSerializer(serializers.ModelSerializer):
    """
    Serializer for staff attendance.
    """

    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    duration = serializers.ReadOnlyField()

    class Meta:
        model = StaffAttendance
        fields = [
            "id",
            "user",
            "user_name",
            "clock_in",
            "clock_out",
            "shift",
            "notes",
            "duration",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ClockInSerializer(serializers.Serializer):
    """
    Serializer for clocking in.
    """

    shift = serializers.ChoiceField(choices=["morning", "evening", "night"])
    notes = serializers.CharField(required=False, allow_blank=True)


class ClockOutSerializer(serializers.Serializer):
    """
    Serializer for clocking out.
    """

    notes = serializers.CharField(required=False, allow_blank=True)


class AuditLogSerializer(serializers.ModelSerializer):
    """
    Serializer for audit logs.
    """

    user_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "user",
            "user_name",
            "action",
            "model_name",
            "object_id",
            "changes",
            "ip_address",
            "timestamp",
        ]
        read_only_fields = fields
