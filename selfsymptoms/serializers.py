from django.db import transaction
from rest_framework import serializers

from accounts.models import HospitalProfile

from .models import (
    DiagnosisAnalysis,
    PatientSymptomArea,
    PatientSymptomCase,
    PatientSymptomImage,
    PatientSymptomType,
)


class DiagnosisAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosisAnalysis
        fields = [
            "diagnosis_analysis_id",
            "extracted_text",
            "analysis_result",
            "analyzed_at",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


class PatientSymptomImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField(
        read_only=True,
    )

    class Meta:
        model = PatientSymptomImage
        fields = [
            "symptom_image_id",
            "symptom_case",
            "image",
            "image_url",
            "display_order",
            "created_at",
        ]

        read_only_fields = [
            "symptom_image_id",
            "image_url",
            "created_at",
        ]

        extra_kwargs = {
            "symptom_case": {
                "required": False,
            }
        }

    def get_image_url(self, obj):
        if not obj.image:
            return None

        request = self.context.get("request")

        if request:
            return request.build_absolute_uri(
                obj.image.url
            )

        return obj.image.url

    def validate_display_order(self, value):
        if value < 1 or value > 6:
            raise serializers.ValidationError(
                "사진 순서는 1부터 6 사이여야 합니다."
            )

        return value

    def validate(self, attrs):
        symptom_case = attrs.get("symptom_case")

        if not symptom_case and self.instance:
            symptom_case = self.instance.symptom_case

        if symptom_case:
            image_queryset = (
                PatientSymptomImage.objects
                .filter(symptom_case=symptom_case)
            )

            if self.instance:
                image_queryset = image_queryset.exclude(
                    pk=self.instance.pk
                )

            if image_queryset.count() >= 6:
                raise serializers.ValidationError(
                    {
                        "image": (
                            "한 증상 기록에는 사진을 "
                            "최대 6장까지 등록할 수 있습니다."
                        )
                    }
                )

            display_order = attrs.get("display_order")

            if (
                display_order is not None
                and image_queryset.filter(
                    display_order=display_order
                ).exists()
            ):
                raise serializers.ValidationError(
                    {
                        "display_order": (
                            "이미 사용 중인 사진 순서입니다."
                        )
                    }
                )

        return attrs


class PatientSymptomAreaSerializer(
    serializers.ModelSerializer
):
    area_name = serializers.CharField(
        source="get_area_type_display",
        read_only=True,
    )

    class Meta:
        model = PatientSymptomArea
        fields = [
            "symptom_area_id",
            "area_type",
            "area_name",
            "created_at",
        ]

        read_only_fields = [
            "symptom_area_id",
            "area_name",
            "created_at",
        ]

class PatientSymptomTypeSerializer(
    serializers.ModelSerializer
):
    symptom_name = serializers.CharField(
        source="get_symptom_type_display",
        read_only=True,
    )

    class Meta:
        model = PatientSymptomType
        fields = [
            "symptom_type_id",
            "symptom_type",
            "symptom_name",
            "custom_symptom",
            "created_at",
        ]

        read_only_fields = [
            "symptom_type_id",
            "symptom_name",
            "created_at",
        ]

    def validate(self, attrs):
        symptom_type = attrs.get("symptom_type")
        custom_symptom = attrs.get("custom_symptom")

        if (
            symptom_type
            == PatientSymptomType.SymptomType.OTHER
            and not custom_symptom
        ):
            raise serializers.ValidationError(
                {
                    "custom_symptom": (
                        "기타 증상을 선택한 경우 "
                        "증상을 직접 입력해야 합니다."
                    )
                }
            )

        if (
            symptom_type
            != PatientSymptomType.SymptomType.OTHER
            and custom_symptom
        ):
            raise serializers.ValidationError(
                {
                    "custom_symptom": (
                        "기타 증상을 선택한 경우에만 "
                        "직접 입력할 수 있습니다."
                    )
                }
            )

        return attrs


class PatientSymptomCaseSerializer(
    serializers.ModelSerializer
):
    patient_id = serializers.IntegerField(
        source="patient.patient_id",
        read_only=True,
    )

    patient_name = serializers.CharField(
        source="patient.user.name",
        read_only=True,
    )

    diagnosed_hospital = serializers.PrimaryKeyRelatedField(
        queryset=HospitalProfile.objects.all(),
        required=True,
    )

    diagnosed_hospital_name = serializers.CharField(
        source="diagnosed_hospital.user.name",
        read_only=True,
    )

    diagnosis_document = serializers.FileField(
        required=True,
        allow_null=False,
    )

    diagnosis_document_url = serializers.SerializerMethodField(
        read_only=True,
    )

    diagnosis_analysis = DiagnosisAnalysisSerializer(
        read_only=True,
    )

    images = PatientSymptomImageSerializer(
        many=True,
        read_only=True,
    )

    areas = PatientSymptomAreaSerializer(
        many=True,
        required=False,
    )

    symptom_types = PatientSymptomTypeSerializer(
        many=True,
        required=False,
    )

    class Meta:
        model = PatientSymptomCase
        fields = [
            "symptom_case_id",
            "patient_id",
            "patient_name",
            "diagnosed_hospital",
            "diagnosed_hospital_name",
            "diagnosis_document",
            "diagnosis_document_url",
            "diagnosis_analysis",
            "symptom_start_date",
            "onset_timing",
            "description",
            "pain_level",
            "status",
            "images",
            "areas",
            "symptom_types",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "symptom_case_id",
            "patient_id",
            "patient_name",
            "diagnosed_hospital_name",
            "diagnosis_document_url",
            "diagnosis_analysis",
            "status",
            "images",
            "created_at",
            "updated_at",
        ]

    def get_diagnosis_document_url(self, obj):
        if not obj.diagnosis_document:
            return None

        request = self.context.get("request")

        if request:
            return request.build_absolute_uri(
                obj.diagnosis_document.url
            )

        return obj.diagnosis_document.url

    def validate_pain_level(self, value):
        if value is not None:
            if value < 1 or value > 5:
                raise serializers.ValidationError(
                    "통증 정도는 1부터 5 사이여야 합니다."
                )

        return value

    def validate_areas(self, value):
        area_types = [
            item["area_type"]
            for item in value
        ]

        if len(area_types) != len(set(area_types)):
            raise serializers.ValidationError(
                "같은 증상 부위를 중복 선택할 수 없습니다."
            )

        return value

    def validate_symptom_types(self, value):
        symptom_types = [
            item["symptom_type"]
            for item in value
        ]

        if len(symptom_types) != len(set(symptom_types)):
            raise serializers.ValidationError(
                "같은 증상 종류를 중복 선택할 수 없습니다."
            )

        return value

    @transaction.atomic
    def create(self, validated_data):
        areas_data = validated_data.pop(
            "areas",
            [],
        )

        symptom_types_data = validated_data.pop(
            "symptom_types",
            [],
        )

        patient = self.context.get("patient")

        if not patient:
            raise serializers.ValidationError(
                {
                    "patient": (
                        "환자 프로필을 확인할 수 없습니다."
                    )
                }
            )

        symptom_case = PatientSymptomCase.objects.create(
            patient=patient,
            **validated_data,
        )

        for area_data in areas_data:
            PatientSymptomArea.objects.create(
                symptom_case=symptom_case,
                **area_data,
            )

        for symptom_type_data in symptom_types_data:
            PatientSymptomType.objects.create(
                symptom_case=symptom_case,
                **symptom_type_data,
            )

        return symptom_case

    @transaction.atomic
    def update(self, instance, validated_data):
        areas_data = validated_data.pop(
            "areas",
            None,
        )

        symptom_types_data = validated_data.pop(
            "symptom_types",
            None,
        )

        for field, value in validated_data.items():
            setattr(
                instance,
                field,
                value,
            )

        instance.save()

        if areas_data is not None:
            instance.areas.all().delete()

            for area_data in areas_data:
                PatientSymptomArea.objects.create(
                    symptom_case=instance,
                    **area_data,
                )

        if symptom_types_data is not None:
            instance.symptom_types.all().delete()

            for symptom_type_data in symptom_types_data:
                PatientSymptomType.objects.create(
                    symptom_case=instance,
                    **symptom_type_data,
                )

        return instance
