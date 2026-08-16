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
from .specialties import (
    MAX_SPECIALTY_SELECTIONS,
    SpecialtyCode,
    get_specialty_code_for_name,
    get_specialty_name,
    normalize_specialty_name,
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
            "city",
            "latitude",
            "longitude",
        )

        read_only_fields = (
            "patient_id",
            "name",
        )


# =========================================================
# 병원 진료과
# =========================================================


class MedicalSpecialtySerializer(serializers.ModelSerializer):
    is_custom = serializers.SerializerMethodField()

    class Meta:
        model = MedicalSpecialty

        fields = (
            "hospital_specialty_id",
            "specialty_code",
            "specialty_name",
            "is_custom",
        )

        read_only_fields = (
            "hospital_specialty_id",
            "specialty_code",
            "specialty_name",
            "is_custom",
        )

    def get_is_custom(self, obj):
        return obj.specialty_code == SpecialtyCode.CUSTOM


class HospitalSignUpSpecialtySerializer(serializers.Serializer):
    specialty_code = serializers.ChoiceField(
        choices=SpecialtyCode.choices,
    )
    specialty_name = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=False,
        trim_whitespace=True,
    )

    def validate(self, attrs):
        specialty_code = attrs["specialty_code"]
        specialty_name = attrs.get("specialty_name", "")

        if specialty_code == SpecialtyCode.CUSTOM:
            if not specialty_name:
                raise serializers.ValidationError(
                    {
                        "specialty_name": (
                            "직접 추가한 전문 분야명을 입력해 주세요."
                        )
                    }
                )

            matched_code = get_specialty_code_for_name(
                specialty_name
            )
            if matched_code != SpecialtyCode.CUSTOM:
                raise serializers.ValidationError(
                    {
                        "specialty_name": (
                            "기본 전문 분야는 해당 분야 코드로 선택해 주세요."
                        )
                    }
                )
        else:
            canonical_name = get_specialty_name(specialty_code)
            if (
                specialty_name
                and normalize_specialty_name(specialty_name)
                != normalize_specialty_name(canonical_name)
            ):
                raise serializers.ValidationError(
                    {
                        "specialty_name": (
                            "전문 분야 코드와 이름이 일치하지 않습니다."
                        )
                    }
                )
            specialty_name = canonical_name

        attrs["specialty_name"] = get_specialty_name(
            specialty_code,
            specialty_name,
        )
        return attrs


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

    website = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        allow_null=True,
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
    overseas_transfer_agreed = serializers.BooleanField(
        write_only=True,
    )

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
            "overseas_transfer_agreed",
            "address",
            "phone",
            "birth_date",
            "passport_number",
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)

        if not attrs.get("overseas_transfer_agreed"):
            raise serializers.ValidationError(
                {
                    "overseas_transfer_agreed": (
                        "개인정보 국외 이전 동의는 필수입니다."
                    )
                }
            )

        return attrs

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
    specialties = HospitalSignUpSpecialtySerializer(
        many=True,
        required=False,
        allow_empty=False,
        max_length=MAX_SPECIALTY_SELECTIONS,
        write_only=True,
    )

    specialty_name = serializers.CharField(
        max_length=100,
        required=False,
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

    website = serializers.CharField(
        max_length=500,
        write_only=True,
        required=False,
        allow_blank=True,
    )

    class Meta(BaseSignUpSerializer.Meta):
        fields = (
            *BaseSignUpSerializer.Meta.fields,
            "specialties",
            "specialty_name",
            "country",
            "city",
            "address",
            "phone",
            "website",
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        specialties = attrs.get("specialties")
        legacy_specialty_name = attrs.get("specialty_name")

        if specialties and legacy_specialty_name:
            raise serializers.ValidationError(
                {
                    "specialties": (
                        "specialties와 specialty_name을 함께 보낼 수 없습니다."
                    )
                }
            )

        if not specialties and not legacy_specialty_name:
            raise serializers.ValidationError(
                {
                    "specialties": (
                        "전문 분야를 한 개 이상 선택해 주세요."
                    )
                }
            )

        if legacy_specialty_name:
            specialty_code = get_specialty_code_for_name(
                legacy_specialty_name
            )
            specialties = [
                {
                    "specialty_code": specialty_code,
                    "specialty_name": get_specialty_name(
                        specialty_code,
                        legacy_specialty_name,
                    ),
                }
            ]
            attrs["specialties"] = specialties

        normalized_names = [
            normalize_specialty_name(item["specialty_name"])
            for item in specialties
        ]
        if len(normalized_names) != len(set(normalized_names)):
            raise serializers.ValidationError(
                {
                    "specialties": (
                        "같은 전문 분야를 중복 선택할 수 없습니다."
                    )
                }
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        specialties = validated_data.pop("specialties")
        validated_data.pop("specialty_name", None)

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

        MedicalSpecialty.objects.bulk_create(
            [
                MedicalSpecialty(
                    hospital=hospital,
                    specialty_code=item["specialty_code"],
                    specialty_name=item["specialty_name"],
                )
                for item in specialties
            ]
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
