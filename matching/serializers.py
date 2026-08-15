from rest_framework import serializers

from accounts.models import HospitalProfile

from .models import (
    HospitalConnectionRequest,
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

    specialties = serializers.SerializerMethodField()

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

    def get_specialties(
        self,
        obj,
    ):
        return list(
            obj.specialties.values_list(
                "specialty_name",
                flat=True,
            )
        )

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


class HospitalConnectionRequestSerializer(
    serializers.ModelSerializer
):
    hospital = HospitalSimpleSerializer(
        read_only=True,
    )

    class Meta:
        model = HospitalConnectionRequest

        fields = [
            "connection_request_id",

            "recommendation",
            "hospital",

            "status",
            "request_message",

            "requested_at",
            "accepted_at",
            "rejected_at",
            "cancelled_at",
            "completed_at",

            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "connection_request_id",
            "hospital",
            "status",

            "requested_at",
            "accepted_at",
            "rejected_at",
            "cancelled_at",
            "completed_at",

            "created_at",
            "updated_at",
        ]
