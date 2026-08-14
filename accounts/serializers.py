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


class UserSerializer(serializers.ModelSerializer):
    hospital_profile_id = serializers.IntegerField(
        source="hospital_profile.hospital_id",
        read_only=True,
    )
    patient_profile_id = serializers.IntegerField(
        source="patient_profile.patient_id",
        read_only=True,
    )
    country = serializers.CharField(write_only=True, required=False)
    city = serializers.CharField(write_only=True, required=False)
    address = serializers.CharField(write_only=True, required=False)
    hospital_type = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    language_code = serializers.CharField(
        write_only=True, required=False, default="en"
    )
    latitude = serializers.DecimalField(
        max_digits=10, decimal_places=7, write_only=True, required=False
    )
    longitude = serializers.DecimalField(
        max_digits=10, decimal_places=7, write_only=True, required=False
    )
    phone = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    website = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    description = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    business_hours = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    image_url = serializers.URLField(
        write_only=True, required=False, allow_blank=True
    )
    medical_specialty = serializers.CharField(
        max_length=100,
        write_only=True,
        required=False,
    )
    birth_date = serializers.DateField(write_only=True, required=False)
    passport_number = serializers.CharField(
        max_length=100,
        write_only=True,
        required=False,
    )
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
    overseas_transfer_agreed = serializers.BooleanField(
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
            "overseas_transfer_agreed",
            "marketing_agreed",
            "preferred_language",
            "location_info_agreed",
            "hospital_profile_id",
            "patient_profile_id",
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
            "medical_specialty",
            "birth_date",
            "passport_number",
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

        if attrs.get("user_type") == User.UserType.HOSPITAL:
            required_fields = (
                "country",
                "city",
                "address",
                "latitude",
                "longitude",
                "medical_specialty",
            )
            for field in required_fields:
                if not attrs.get(field):
                    errors[field] = "병원 회원가입 시 필수 입력값입니다."

            if not attrs.get("location_info_agreed"):
                errors["location_info_agreed"] = (
                    "위치정보 이용 동의는 필수입니다."
                )

        if attrs.get("user_type") == User.UserType.PATIENT:
            for field in (
                "address",
                "phone",
                "birth_date",
                "passport_number",
            ):
                if not attrs.get(field):
                    errors[field] = "환자 회원가입 시 필수 입력값입니다."

            if not attrs.get("overseas_transfer_agreed"):
                errors["overseas_transfer_agreed"] = (
                    "개인정보 국외 이전 동의는 필수입니다."
                )

        if errors:
            raise serializers.ValidationError(
                errors
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop(
            "password"
        )
        hospital_field_names = (
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
        )
        profile_data = {
            field: validated_data.pop(field)
            for field in hospital_field_names
            if field in validated_data
        }
        specialty = validated_data.pop("medical_specialty", None)
        birth_date = validated_data.pop("birth_date", None)
        passport_number = validated_data.pop("passport_number", None)

        user = User.objects.create_user(
            password=password,
            **validated_data,
        )

        if user.user_type == User.UserType.HOSPITAL:
            hospital = HospitalProfile.objects.create(
                user=user,
                **profile_data,
            )
            MedicalSpecialty.objects.create(
                hospital=hospital,
                specialty_name=specialty,
            )

        elif user.user_type == User.UserType.PATIENT:
            PatientProfile.objects.create(
                user=user,
                address=profile_data.get("address", ""),
                phone=profile_data.get("phone"),
                birth_date=birth_date,
                passport_number=passport_number,
                residence_country="",
            )

        return user


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

        return {
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


class PatientProfileSerializer(
    serializers.ModelSerializer
):
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

        read_only_fields = fields


class HospitalProfileSerializer(
    serializers.ModelSerializer
):
    name = serializers.CharField(
        source="user.name",
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
        )

        read_only_fields = fields
