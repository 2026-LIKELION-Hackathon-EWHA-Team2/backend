from rest_framework import serializers

from ..models import CaseCollaborationRequest
from .transfers import (
    MedicalCaseDetailSerializer,
    PartnerCaseTransferSerializer,
    format_medical_case_number,
)


class CaseCollaborationRequestSerializer(
    serializers.ModelSerializer
):
    case_number = serializers.SerializerMethodField()

    medical_case = MedicalCaseDetailSerializer(
        read_only=True,
    )

    medical_case_id = serializers.IntegerField(
        source="medical_case.id",
        read_only=True,
    )

    origin_hospital_id = serializers.IntegerField(
        source="medical_case.origin_hospital.id",
        read_only=True,
    )

    origin_hospital_name = serializers.CharField(
        source="medical_case.origin_hospital.name",
        read_only=True,
    )

    partner_hospital_id = serializers.IntegerField(
        source="medical_case.partner_hospital.id",
        read_only=True,
    )

    partner_hospital_name = serializers.CharField(
        source="medical_case.partner_hospital.name",
        read_only=True,
    )

    chat_room_id = serializers.SerializerMethodField()
    case_transfer_id = serializers.SerializerMethodField()

    class Meta:
        model = CaseCollaborationRequest

        fields = (
            "id",
            "case_number",
            "medical_case_id",
            "medical_case",
            "origin_hospital_id",
            "origin_hospital_name",
            "partner_hospital_id",
            "partner_hospital_name",
            "status",
            "chat_room_id",
            "case_transfer_id",
            "requested_at",
            "accepted_at",
            "rejected_at",
            "completed_at",
            "created_at",
            "updated_at",
        )

        read_only_fields = fields

    def get_case_number(self, obj):
        return format_medical_case_number(obj.medical_case)

    def get_chat_room_id(self, obj):
        room = obj.medical_case.chat_rooms.filter(
            partner_hospital_id=(
                obj.medical_case.partner_hospital_id
            ),
        ).first()

        return room.id if room else None

    def get_case_transfer_id(self, obj):
        transfer = obj.medical_case.case_transfers.first()
        return transfer.id if transfer else None


class CaseCollaborationRequestDetailSerializer(
    CaseCollaborationRequestSerializer
):
    patient_name = serializers.CharField(
        source="medical_case.patient.name",
        read_only=True,
    )
    procedure_name = serializers.SerializerMethodField()
    procedure_area = serializers.SerializerMethodField()
    consultation_title = serializers.SerializerMethodField()
    procedure_hospital_name = serializers.CharField(
        source="medical_case.origin_hospital.name",
        read_only=True,
    )

    patient_provided_data = serializers.SerializerMethodField()

    ai_translation_summary = serializers.SerializerMethodField()


    class Meta(CaseCollaborationRequestSerializer.Meta):
        fields = CaseCollaborationRequestSerializer.Meta.fields + (
            "patient_name",
            "procedure_name",
            "procedure_area",
            "consultation_title",
            "procedure_hospital_name",
            "patient_provided_data",
            "ai_translation_summary",
        )
        read_only_fields = fields

    def get_display_structured_data(self, obj):
        transfer = obj.medical_case.case_transfers.first()
        if transfer is None:
            return {}

        request = self.context.get("request")
        display_language = (
            request.user.preferred_language
            if request is not None
            else transfer.target_language
        )
        return (transfer.translated_data or {}).get(
            display_language,
            transfer.structured_data or {},
        )

    def get_procedure_name(self, obj):
        procedure = self.get_display_structured_data(obj).get(
            "procedure", {}
        )
        return procedure.get("name") or obj.medical_case.procedure_name

    def get_procedure_area(self, obj):
        procedure = self.get_display_structured_data(obj).get(
            "procedure", {}
        )
        return procedure.get("area") or obj.medical_case.procedure_area

    def get_ai_translation_summary(self, obj):
        return self.get_display_structured_data(obj).get(
            "ai_summary"
        ) or obj.medical_case.ai_summary

    def get_consultation_title(self, obj):
        return (
            f"{self.get_procedure_area(obj)} "
            f"{self.get_procedure_name(obj)} 상담"
        )
    
    def get_patient_provided_data(self, obj):
        transfer = obj.medical_case.case_transfers.first()

        if transfer is None:
            return {}

        request = self.context.get("request")
        display_language = (
            request.user.preferred_language
            if request is not None
            else transfer.target_language
        )

        return PartnerCaseTransferSerializer(
            transfer,
            context={
                **self.context,
                "display_language": display_language,
            },
        ).data["transmitted_data"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        structured = self.get_display_structured_data(instance)
        procedure = structured.get("procedure") or {}

        medical_case = data.get("medical_case") or {}
        medical_case["procedure_name"] = (
            procedure.get("name")
            or medical_case.get("procedure_name")
        )
        medical_case["procedure_area"] = (
            procedure.get("area")
            or medical_case.get("procedure_area")
        )
        medical_case["clinician_note"] = (
            structured.get("clinician_note")
            or medical_case.get("clinician_note")
        )
        medical_case["ai_summary"] = (
            structured.get("ai_summary")
            or medical_case.get("ai_summary")
        )

        translated_ingredients = structured.get("ingredients") or []
        existing_ingredients = medical_case.get("ingredients") or []
        medical_case["ingredients"] = [
            {
                "id": (
                    existing_ingredients[index].get("id")
                    if index < len(existing_ingredients)
                    else None
                ),
                "ingredient_name": ingredient,
            }
            for index, ingredient in enumerate(translated_ingredients)
        ]

        data["medical_case"] = medical_case
        return data
