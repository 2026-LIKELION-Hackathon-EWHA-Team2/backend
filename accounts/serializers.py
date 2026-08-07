from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PatientProfile, User



class UserSerializer(serializers.ModelSerializer):
    login_id = serializers.CharField(
        source="username",
        max_length=50,
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="이미 사용 중인 아이디입니다.",
            )
        ],
    )

    password = serializers.CharField(
        max_length=128,
        write_only=True,
        validators=[validate_password],
    )

    terms_agreed = serializers.BooleanField(write_only=True)
    privacy_agreed = serializers.BooleanField(write_only=True)
    overseas_info_agreed = serializers.BooleanField(write_only=True)

    marketing_agreed = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "name",
            "login_id",
            "password",
            "user_type",
            "terms_agreed",
            "privacy_agreed",
            "overseas_info_agreed",
            "marketing_agreed",
            "preferred_language",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        errors = {}

        if not attrs.get("terms_agreed"):
            errors["terms_agreed"] = (
                "서비스 이용약관 동의는 필수입니다."
            )

        if not attrs.get("privacy_agreed"):
            errors["privacy_agreed"] = (
                "개인정보 수집 및 이용 동의는 필수입니다."
            )

        if not attrs.get("overseas_info_agreed"):
            errors["overseas_info_agreed"] = (
                "해외 병원 정보 공유 동의는 필수입니다."
            )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")

        return User.objects.create_user(
            password=password,
            **validated_data,
        )



class UserLoginSerializer(serializers.Serializer):
    login_id = serializers.CharField(max_length=50)

    password = serializers.CharField(
        max_length=128,
        write_only=True,
    )

    def validate(self, data):
        user = authenticate(
            username=data["login_id"],
            password=data["password"],
        )

        if user is None:
            raise serializers.ValidationError(
                {
                    "detail": "아이디 또는 비밀번호가 올바르지 않습니다."
                }
            )

        refresh_token = RefreshToken.for_user(user)

        return {
            "id": user.id,
            "name": user.name,
            "login_id": user.username,
            "user_type": user.user_type,
            "access": str(refresh_token.access_token),
            "refresh": str(refresh_token),
        }


class PatientProfileSerializer(serializers.ModelSerializer):
    name = serializers.CharField(
        source="user.name",
        read_only=True,
    )

    class Meta:
        model = PatientProfile
        fields = (
            "patient_id",
            "name",
            "passport_number",
            "birth_date",
            "nationality",
            "phone",
            "residence_country",
        )
        read_only_fields = fields