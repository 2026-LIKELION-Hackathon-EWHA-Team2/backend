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

        read_only_fields = (
            "patient_id",
            "name",
        )


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

    patient_profile = PatientProfileSerializer(
        required=False,
        write_only=True,
    )

    hospital_profile = HospitalProfileSerializer(
        required=False,
        write_only=True,
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
            "patient_profile",
            "hospital_profile",
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

        user_type = attrs.get("user_type")

        patient_profile = attrs.get("patient_profile")
        hospital_profile = attrs.get("hospital_profile")

        if user_type == User.UserType.PATIENT:
            if not patient_profile:
                errors["patient_profile"] = (
                    "환자 프로필 정보가 필요합니다."
                )

            if hospital_profile:
                errors["hospital_profile"] = (
                    "환자 계정에는 병원 프로필을 등록할 수 없습니다."
                )

        elif user_type == User.UserType.HOSPITAL:
            if not hospital_profile:
                errors["hospital_profile"] = (
                    "병원 프로필 정보가 필요합니다."
                )

            if patient_profile:
                errors["patient_profile"] = (
                    "병원 계정에는 환자 프로필을 등록할 수 없습니다."
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

        patient_profile_data = validated_data.pop(
            "patient_profile",
            None,
        )

        hospital_profile_data = validated_data.pop(
            "hospital_profile",
            None,
        )

        user = User.objects.create_user(
            password=password,
            **validated_data,
        )

        if user.user_type == User.UserType.PATIENT:
            PatientProfile.objects.create(
                user=user,
                **patient_profile_data,
            )

        elif user.user_type == User.UserType.HOSPITAL:
            HospitalProfile.objects.create(
                user=user,
                **hospital_profile_data,
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