from rest_framework import serializers
from accounts.serializers import MedicalSpecialtySerializer
from accounts.models import HospitalProfile

from .models import (
    HospitalMatchRequest,
    HospitalRecommendation,
)


class HospitalSimpleSerializer(
    serializers.ModelSerializer
):
    name = serializers.CharField(
        source="user.name",
        read_only=True,
    )

    specialties = MedicalSpecialtySerializer(
        many = True,
        read_only=True,
    )

    collaboration_count = serializers.SerializerMethodField()

    class Meta:
        model = HospitalProfile

        fields = [
            "hospital_id",
            "name",

            "country",
            "city",
            "address",

            "hospital_type",

            "latitude",
            "longitude",

            "phone",
            "website",

            "description",
            "business_hours",
            "image_url",

            "specialties",
            "collaboration_count",
        ]

    def get_collaboration_count(
        self,
        obj,
    ):
        from cases.models import MedicalCase

        return (
            MedicalCase.objects
            .filter(
                partner_hospital=obj.user,
                status=MedicalCase.Status.TRANSFERRED,
            )
            .count()
        )


class HospitalMatchRequestSerializer(
    serializers.ModelSerializer
):
    patient_id = serializers.IntegerField(
        source="patient.patient_id",
        read_only=True,
    )

    required_specialty = serializers.CharField(
        read_only=True,
    )

    required_specialty_code = serializers.CharField(
        read_only=True,
    )

    search_country = serializers.CharField(
        max_length=50,
        required=False,
    )

    search_city = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    search_address = serializers.CharField(
            max_length=255,
            required=False,
            allow_blank=True,
            allow_null=True,
        )

    search_latitude = serializers.DecimalField(
            max_digits=10,
            decimal_places=7,
            required=False,
            allow_null=True,
        )

    search_longitude = serializers.DecimalField(
            max_digits=10,
            decimal_places=7,
            required=False,
            allow_null=True,
        )

    class Meta:
        model = HospitalMatchRequest

        fields = [
            "match_request_id",

            "symptom_case",
            "patient_id",

            "required_specialty",
            "required_specialty_code",

            "specialty_weight",
            "distance_weight",
            "collaboration_weight",

            "location_source",

            "search_country",
            "search_city",
            "search_address",

            "search_latitude",
            "search_longitude",

            "status",

            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "match_request_id",
            "patient_id",
            "required_specialty",
            "required_specialty_code",
            "status",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):

        specialty_weight = attrs.get(
            "specialty_weight",
            50,
        )

        distance_weight = attrs.get(
            "distance_weight",
            50,
        )

        collaboration_weight = attrs.get(
            "collaboration_weight",
            50,
        )

        weights = [
            specialty_weight,
            distance_weight,
            collaboration_weight,
        ]

        for weight in weights:
            if not 0 <= weight <= 100:
                raise serializers.ValidationError(
                    "가중치는 0~100 사이여야 합니다."
                )

        if sum(weights) == 0:
            raise serializers.ValidationError(
                "최소 한 개의 추천 기준을 선택해야 합니다."
            )

        location_source = attrs.get(
            "location_source",
            HospitalMatchRequest.LocationSource.PROFILE,
        )

        if location_source == HospitalMatchRequest.LocationSource.PROFILE:
            patient = self.context.get("patient")
            if patient is None:
                raise serializers.ValidationError(
                    {
                        "location_source": (
                            "환자 프로필을 확인할 수 없습니다."
                        )
                    }
                )
            profile_errors = {}

            if not patient.residence_country : 
                profile_errors["search_country"] = (
                    "프로필에 거주 국가를 등록해 주세요."
                )

            if patient.latitude is None or patient.longitude is None:
                profile_errors["search_latitude"] = (
                    "프로필에 거주지 좌표를 등록해 주세요."
                )
                profile_errors["search_longitude"] = (
                    "프로필에 거주지 좌표를 등록해 주세요."
                )
            if profile_errors:
                raise serializers.ValidationError(
                    profile_errors
            )

            # 클라이언트가 보낸 search_*보다 프로필 값을 우선합니다.
            attrs["search_country"] = (
                patient.residence_country
            )
            attrs["search_city"] = patient.city
            attrs["search_address"] = patient.address
            attrs["search_latitude"] = patient.latitude
            attrs["search_longitude"] = patient.longitude

        elif location_source == HospitalMatchRequest.LocationSource.CUSTOM:
            custom_errors = {}

            if not attrs.get("search_country"):
                custom_errors["search_country"] = (
                    "직접 위치 사용 시 국가가 필요합니다."
                )

            if attrs.get("search_latitude") is None:
                custom_errors["search_latitude"] = (
                    "직접 위치 사용 시 위도가 필요합니다."
                )

            if attrs.get("search_longitude") is None:
                custom_errors["search_longitude"] = (
                    "직접 위치 사용 시 경도가 필요합니다."
                )

            if custom_errors:
                raise serializers.ValidationError(
                    custom_errors
                )
        return attrs


class HospitalRecommendationSerializer(
    serializers.ModelSerializer
):
    hospital = HospitalSimpleSerializer(
        read_only=True,
    )

    class Meta:
        model = HospitalRecommendation

        fields = [
            "recommendation_id",

            "rank_number",
            "batch_number",

            "hospital",

            "specialty_score",
            "distance_score",
            "collaboration_score",

            "total_score",
            "distance_km",

            "is_selected",

            "created_at",
        ]
