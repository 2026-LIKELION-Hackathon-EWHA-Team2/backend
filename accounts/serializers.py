from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    HospitalProfile,
    MedicalSpecialty,
    PatientProfile,
    User,
)


# =========================================================
# 환자 프로필
# =========================================================


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
            "address",
            "residence_country",
        )

        read_only_fields = (
            "patient_id",
            "name",
        )


# =========================================================
# 병원 진료과
# =========================================================


class MedicalSpecialtySerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalSpecialty

        fields = (
            "hospital_specialty_id",
            "specialty_name",
        )

        read_only_fields = (
            "hospital_specialty_id",
        )


# =========================================================
# 병원 프로필
# =========================================================


class HospitalProfileSerializer(serializers.ModelSerializer):
    name = serializers.CharField(
        source="user.name",
        read_only=True,
    )

    specialties = MedicalSpecialtySerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = HospitalProfile

        fields = (
            "hospital_id",
            "name",
            "country",
            "city",
            "address",
            "hospital_type",
            "language_code",
            "latitude",
            "longitude",
            "phone",
            "website",
            "description",
            "business_hours",
            "image_url",
            "specialties",
        )

        read_only_fields = (
            "hospital_id",
            "name",
            "specialties",
        )


# =========================================================
# 공통 회원가입
# =========================================================


class BaseSignUpSerializer(serializers.ModelSerializer):
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

    terms_agreed = serializers.BooleanField(
        write_only=True,
    )

    privacy_agreed = serializers.BooleanField(
        write_only=True,
    )

    overseas_info_agreed = serializers.BooleanField(
        write_only=True,
    )

    marketing_agreed = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
    )

    location_info_agreed = serializers.BooleanField(
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
            "terms_agreed",
            "privacy_agreed",
            "overseas_info_agreed",
            "marketing_agreed",
            "location_info_agreed",
            "preferred_language",
        )

        read_only_fields = (
            "id",
        )

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
            raise serializers.ValidationError(
                errors
            )

        return attrs


# =========================================================
# 일반회원 회원가입
# =========================================================


class PatientSignUpSerializer(
    BaseSignUpSerializer
):
    address = serializers.CharField(
        max_length=255,
        write_only=True,
    )

    phone = serializers.CharField(
        max_length=30,
        write_only=True,
    )

    birth_date = serializers.DateField(
        write_only=True,
    )

    passport_number = serializers.CharField(
        max_length=100,
        write_only=True,
    )

    class Meta(BaseSignUpSerializer.Meta):
        fields = (
            *BaseSignUpSerializer.Meta.fields,
            "address",
            "phone",
            "birth_date",
            "passport_number",
        )

    @transaction.atomic
    def create(self, validated_data):
        address = validated_data.pop(
            "address"
        )

        phone = validated_data.pop(
            "phone"
        )

        birth_date = validated_data.pop(
            "birth_date"
        )

        passport_number = validated_data.pop(
            "passport_number"
        )

        password = validated_data.pop(
            "password"
        )

        user = User.objects.create_user(
            password=password,
            user_type=User.UserType.PATIENT,
            **validated_data,
        )

        PatientProfile.objects.create(
            user=user,
            address=address,
            phone=phone,
            birth_date=birth_date,
            passport_number=passport_number,
        )

        return user


# =========================================================
# 병원회원 회원가입
# =========================================================


class HospitalSignUpSerializer(
    BaseSignUpSerializer
):
    specialty_name = serializers.CharField(
        max_length=100,
        write_only=True,
    )

    country = serializers.CharField(
        max_length=50,
        write_only=True,
    )

    city = serializers.CharField(
        max_length=100,
        write_only=True,
    )

    address = serializers.CharField(
        max_length=255,
        write_only=True,
    )

    phone = serializers.CharField(
        max_length=50,
        write_only=True,
    )

    website = serializers.URLField(
        max_length=500,
        write_only=True,
        required=False,
        allow_blank=True,
    )

    class Meta(BaseSignUpSerializer.Meta):
        fields = (
            *BaseSignUpSerializer.Meta.fields,
            "specialty_name",
            "country",
            "city",
            "address",
            "phone",
            "website",
        )

    @transaction.atomic
    def create(self, validated_data):
        specialty_name = validated_data.pop(
            "specialty_name"
        )

        country = validated_data.pop(
            "country"
        )

        city = validated_data.pop(
            "city"
        )

        address = validated_data.pop(
            "address"
        )

        phone = validated_data.pop(
            "phone"
        )

        website = validated_data.pop(
            "website",
            "",
        )

        password = validated_data.pop(
            "password"
        )

        user = User.objects.create_user(
            password=password,
            user_type=User.UserType.HOSPITAL,
            **validated_data,
        )

        hospital = HospitalProfile.objects.create(
            user=user,
            country=country,
            city=city,
            address=address,
            phone=phone,
            website=website or None,
        )

        MedicalSpecialty.objects.create(
            hospital=hospital,
            specialty_name=specialty_name,
        )

        return user


# =========================================================
# 로그인
# =========================================================


class UserLoginSerializer(serializers.Serializer):
    login_id = serializers.CharField(
        max_length=50,
    )

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
                    "detail": (
                        "아이디 또는 비밀번호가 "
                        "올바르지 않습니다."
                    )
                }
            )

        refresh_token = RefreshToken.for_user(
            user
        )

        response_data = {
            "id": user.id,
            "name": user.name,
            "login_id": user.username,
            "user_type": user.user_type,
            "access": str(
                refresh_token.access_token
            ),
            "refresh": str(
                refresh_token
            ),
        }

        if user.user_type == User.UserType.PATIENT:
            try:
                response_data["patient_id"] = (
                    user.patient_profile.patient_id
                )
            except PatientProfile.DoesNotExist:
                response_data["patient_id"] = None

        elif user.user_type == User.UserType.HOSPITAL:
            try:
                response_data["hospital_id"] = (
                    user.hospital_profile.hospital_id
                )
            except HospitalProfile.DoesNotExist:
                response_data["hospital_id"] = None

        return response_data