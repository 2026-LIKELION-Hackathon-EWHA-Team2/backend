from django.utils import timezone
from rest_framework import serializers
from selfsymptoms.models import PatientSymptomCase
from matching.models import (
    HospitalMatchRequest,
    HospitalRecommendation,
)

from accounts.models import User
from .models import (
    CaseAgreement,
    CaseTransfer,
    CaseAgreementRevision,
    CaseIngredient,
    CaseChatMessage,
    CaseChatRoom,
    CaseCollaborationRequest,
    MedicalCase,
)


ADVERSE_EFFECT_LABELS = {
    "ko": {
        "SWELLING": "부종",
        "INFLAMMATION": "염증",
        "PAIN": "통증",
        "REDNESS": "붉어짐",
        "INFECTION": "감염 의심",
        "PIGMENTATION": "색소침착",
        "BRUISING_BLEEDING": "멍/출혈",
    },
    "en": {
        "SWELLING": "Swelling",
        "INFLAMMATION": "Inflammation",
        "PAIN": "Pain",
        "REDNESS": "Redness",
        "INFECTION": "Suspected infection",
        "PIGMENTATION": "Pigmentation",
        "BRUISING_BLEEDING": "Bruising/bleeding",
    },
    "ja": {
        "SWELLING": "腫れ",
        "INFLAMMATION": "炎症",
        "PAIN": "痛み",
        "REDNESS": "発赤",
        "INFECTION": "感染の疑い",
        "PIGMENTATION": "色素沈着",
        "BRUISING_BLEEDING": "あざ/出血",
    },
    "zh": {
        "SWELLING": "肿胀",
        "INFLAMMATION": "炎症",
        "PAIN": "疼痛",
        "REDNESS": "发红",
        "INFECTION": "疑似感染",
        "PIGMENTATION": "色素沉着",
        "BRUISING_BLEEDING": "淤青/出血",
    },
}


def format_medical_case_number(medical_case):
    return (
        f"CASE-{medical_case.created_at.year}-"
        f"{medical_case.id:06d}"
    )


class CaseIngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseIngredient
        fields = (
            "id",
            "ingredient_name",
        )


class MedicalCaseDetailSerializer(serializers.ModelSerializer):
    patient_id = serializers.IntegerField(
        source="patient.id",
        read_only=True,
    )

    patient_name = serializers.CharField(
        source="patient.name",
        read_only=True,
    )

    origin_hospital_name = serializers.CharField(
        source="origin_hospital.name",
        read_only=True,
    )

    partner_hospital_name = serializers.CharField(
        source="partner_hospital.name",
        read_only=True,
    )

    ingredients = CaseIngredientSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = MedicalCase
        fields = (
            "id",
            "patient_id",
            "patient_name",
            "origin_hospital_name",
            "partner_hospital_name",
            "procedure_name",
            "procedure_area",
            "procedure_date",
            "ingredients",
            "clinician_note",
            "ai_summary",
            "status",
            "transferred_at",
        )


class PatientProcedureHistoryListSerializer(
    serializers.ModelSerializer
):
    medical_case_id = serializers.IntegerField(
        source="id",
        read_only=True,
    )
    symptom_case_id = serializers.SerializerMethodField()
    case_number = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    procedure_hospital_name = serializers.CharField(
        source="origin_hospital.name",
        read_only=True,
    )
    finalized_at = serializers.DateTimeField(
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = MedicalCase
        fields = (
            "medical_case_id",
            "symptom_case_id",
            "case_number",
            "status",
            "procedure_name",
            "procedure_area",
            "procedure_date",
            "procedure_hospital_name",
            "finalized_at",
        )

    @staticmethod
    def get_completed_transfer(obj):
        transfers = getattr(obj, "completed_case_transfers", [])
        return transfers[0] if transfers else None

    def get_symptom_case_id(self, obj):
        transfer = self.get_completed_transfer(obj)
        return transfer.symptom_case_id if transfer else None

    def get_case_number(self, obj):
        return format_medical_case_number(obj)

    def get_status(self, obj):
        transfer = self.get_completed_transfer(obj)
        if transfer is None:
            return None
        return transfer.symptom_case.status


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
    procedure_name = serializers.CharField(
        source="medical_case.procedure_name",
        read_only=True,
    )
    procedure_area = serializers.CharField(
        source="medical_case.procedure_area",
        read_only=True,
    )
    consultation_title = serializers.SerializerMethodField()
    procedure_hospital_name = serializers.CharField(
        source="medical_case.origin_hospital.name",
        read_only=True,
    )

    class Meta(CaseCollaborationRequestSerializer.Meta):
        fields = CaseCollaborationRequestSerializer.Meta.fields + (
            "patient_name",
            "procedure_name",
            "procedure_area",
            "consultation_title",
            "procedure_hospital_name",
        )

    def get_consultation_title(self, obj):
        return (
            f"{obj.medical_case.procedure_area} "
            f"{obj.medical_case.procedure_name} 상담"
        )


class CaseChatMessageSerializer(serializers.ModelSerializer):
    sender_hospital_id = serializers.IntegerField(
        source="sender.id",
        read_only=True,
    )

    sender_hospital_name = serializers.CharField(
        source="sender.name",
        read_only=True,
    )

    translated_content = serializers.SerializerMethodField()
    translation_status = serializers.SerializerMethodField()
    display_content = serializers.SerializerMethodField()

    content = serializers.CharField(
        max_length=4000,
        trim_whitespace=True,
        error_messages={
            "required": "메시지 내용을 입력해 주세요.",
            "blank": "메시지 내용을 입력해 주세요.",
            "max_length": (
                "메시지는 4,000자 이하로 입력해 주세요."
            ),
        },
    )

    class Meta:
        model = CaseChatMessage
        fields = (
            "id",
            "sender_hospital_id",
            "sender_hospital_name",
            "content",
            "source_language",
            "translated_content",
            "translation_status",
            "display_content",
            "created_at",
        )
        read_only_fields = (
            "id",
            "sender_hospital_id",
            "sender_hospital_name",
            "source_language",
            "translated_content",
            "translation_status",
            "display_content",
            "created_at",
        )

    def get_selected_translation(self, obj):
        request = self.context.get("request")

        if request is None:
            return None

        if obj.sender_id == request.user.id:
            return None

        target_language = (
            request.user.preferred_language
        )

        return next(
            (
                translation
                for translation
                in obj.translations.all()
                if translation.target_language
                == target_language
            ),
            None,
        )

    def get_translated_content(self, obj):
        translation = self.get_selected_translation(obj)

        if (
            translation is not None
            and translation.status == "COMPLETED"
        ):
            return translation.translated_content

        return None

    def get_translation_status(self, obj):
        translation = self.get_selected_translation(obj)

        if translation is None:
            return None

        return translation.status

    def get_display_content(self, obj):
        translated_content = (
            self.get_translated_content(obj)
        )

        return translated_content or obj.content

class CaseChatRoomListSerializer(serializers.ModelSerializer):
    room_id = serializers.IntegerField(source="id", read_only=True)
    medical_case_id = serializers.IntegerField(read_only=True)
    case_number = serializers.SerializerMethodField()
    patient_id = serializers.IntegerField(
        source="medical_case.patient.id",
        read_only=True,
    )
    patient_name = serializers.CharField(
        source="medical_case.patient.name",
        read_only=True,
    )
    procedure_name = serializers.CharField(
        source="medical_case.procedure_name",
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
    partner_hospital_id = serializers.IntegerField(read_only=True)
    partner_hospital_name = serializers.CharField(
        source="partner_hospital.name",
        read_only=True,
    )
    counterpart_hospital_id = serializers.SerializerMethodField()
    counterpart_hospital_name = serializers.SerializerMethodField()
    collaboration_request_id = serializers.SerializerMethodField()
    collaboration_request_status = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    last_message_at = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = CaseChatRoom
        fields = (
            "room_id",
            "medical_case_id",
            "case_number",
            "patient_id",
            "patient_name",
            "procedure_name",
            "origin_hospital_id",
            "origin_hospital_name",
            "partner_hospital_id",
            "partner_hospital_name",
            "counterpart_hospital_id",
            "counterpart_hospital_name",
            "collaboration_request_id",
            "collaboration_request_status",
            "last_message",
            "last_message_at",
            "unread_count",
            "created_at",
        )
        read_only_fields = fields

    def get_case_number(self, obj):
        return format_medical_case_number(obj.medical_case)

    def get_counterpart_hospital(self, obj):
        request = self.context["request"]
        if request.user.id == obj.partner_hospital_id:
            return obj.medical_case.origin_hospital
        return obj.partner_hospital

    def get_counterpart_hospital_id(self, obj):
        return self.get_counterpart_hospital(obj).id

    def get_counterpart_hospital_name(self, obj):
        return self.get_counterpart_hospital(obj).name

    def get_collaboration_request(self, obj):
        try:
            return obj.medical_case.collaboration_request
        except CaseCollaborationRequest.DoesNotExist:
            return None

    def get_collaboration_request_id(self, obj):
        collaboration_request = self.get_collaboration_request(obj)
        return collaboration_request.id if collaboration_request else None

    def get_collaboration_request_status(self, obj):
        collaboration_request = self.get_collaboration_request(obj)
        return collaboration_request.status if collaboration_request else None

    def get_messages(self, obj):
        return getattr(obj, "chat_list_messages", [])

    def get_last_message(self, obj):
        messages = self.get_messages(obj)
        if not messages:
            return None

        return CaseChatMessageSerializer(
            messages[-1],
            context=self.context,
        ).data

    def get_last_message_at(self, obj):
        messages = self.get_messages(obj)
        return messages[-1].created_at if messages else None

    def get_unread_count(self, obj):
        request = self.context["request"]
        read_states = getattr(obj, "viewer_read_states", [])
        last_read_message_id = (
            read_states[0].last_read_message_id
            if read_states
            else None
        )

        return sum(
            1
            for message in self.get_messages(obj)
            if message.sender_id != request.user.id
            and (
                last_read_message_id is None
                or message.id > last_read_message_id
            )
        )


class EvidenceItemSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=100)
    content = serializers.CharField(max_length=1000)
    order = serializers.IntegerField(min_value=1)


class CaseAgreementSerializer(serializers.ModelSerializer):
    evidence_items = EvidenceItemSerializer(many=True)
    edited_by_name = serializers.CharField(
        source="edited_by.name",
        read_only=True,
        default=None,
    )
    reviews = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    requires_re_review = serializers.SerializerMethodField()
    latest_edit = serializers.SerializerMethodField()

    revision_requested_by_name = serializers.CharField(
        source="revision_requested_by.name",
        read_only=True,
        default=None,
    )

    class Meta:
        model = CaseAgreement
        fields = (
            "id",
            "chat_room",
            "judgment_draft",
            "evidence_items",
            "additional_opinion",
            "status",
            "version",
            "latest_edit",
            "edited_by_name",
            "edited_at",
            "finalized_at",
            "reviews",
            "can_edit",
            "requires_re_review",
            "created_at",
            "updated_at",
            "revision_requested_by_name",
            "revision_requested_at",
        )
        read_only_fields = (
            "id",
            "chat_room",
            "status",
            "version",
            "latest_edit",
            "edited_by_name",
            "edited_at",
            "finalized_at",
            "reviews",
            "can_edit",
            "requires_re_review",
            "created_at",
            "updated_at",
            "revision_requested_by_name",
            "revision_requested_at",
        )

    def validate_evidence_items(self, items):
        if not items:
            return []

        ids = [item["id"] for item in items]
        orders = [item["order"] for item in items]

        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                "주요 근거 ID는 중복될 수 없습니다."
            )

        if len(orders) != len(set(orders)):
            raise serializers.ValidationError(
                "주요 근거 순서는 중복될 수 없습니다."
            )

        expected_orders = list(range(1, len(items) + 1))

        if sorted(orders) != expected_orders:
            raise serializers.ValidationError(
                "주요 근거 순서는 1부터 연속되어야 합니다."
            )

        return sorted(items, key=lambda item: item["order"])

    def get_latest_edit(self, obj):
        if obj.edited_by_id is None or obj.edited_at is None:
            return None

        return {
            "hospital_name": obj.edited_by.name,
            "edited_at": serializers.DateTimeField().to_representation(
                obj.edited_at
            ),
        }

    def get_reviews(self, obj):
        return [
            {
                "hospital_id": review.hospital_id,
                "hospital_name": review.hospital.name,
                "reviewed_version": review.reviewed_version,
                "reviewed_at": review.reviewed_at,
                "is_current_version": (
                    review.reviewed_version == obj.version
                ),
            }
            for review in obj.reviews.all()
        ]

    def get_can_edit(self, obj):
        request = self.context.get("request")

        if request is None:
            return False

        participant_ids = {
            obj.chat_room.medical_case.origin_hospital_id,
            obj.chat_room.partner_hospital_id,
        }

        return (
            request.user.id in participant_ids
            and obj.status != CaseAgreement.Status.FINAL
        )

    def get_requires_re_review(self, obj):
        current_review_count = obj.reviews.filter(
            reviewed_version=obj.version,
        ).count()

        return (
            obj.status == CaseAgreement.Status.IN_REVIEW
            and current_review_count < 2
            and obj.version > 1
        )


class CaseAgreementRevisionSerializer(
    serializers.ModelSerializer
):
    edited_by_name = serializers.CharField(
        source="edited_by.name",
        read_only=True,
    )

    class Meta:
        model = CaseAgreementRevision
        fields = (
            "id",
            "version",
            "previous_data",
            "changed_fields",
            "edited_by_name",
            "edited_at",
        )


class CaseTransferCreateSerializer(serializers.ModelSerializer):
    symptom_case_id = serializers.PrimaryKeyRelatedField(
        source="symptom_case",
        queryset=PatientSymptomCase.objects.select_related(
            "patient__user",
            "diagnosed_hospital__user",
        ),
    )
    recommendation_id = serializers.PrimaryKeyRelatedField(
        source="recommendation",
        queryset=HospitalRecommendation.objects.select_related(
            "hospital__user",
            "match_request__patient__user",
            "match_request__symptom_case",
        ),
    )

    class Meta:
        model = CaseTransfer
        fields = (
            "id",
            "symptom_case_id",
            "recommendation_id",
            "patient_name",
            "patient_gender",
            "patient_birth_date",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        request = self.context["request"]
        symptom_case = attrs["symptom_case"]
        recommendation = attrs["recommendation"]
        partner_hospital = recommendation.hospital.user

        if request.user.user_type != User.UserType.PATIENT:
            raise serializers.ValidationError(
                "환자만 전송 건을 생성할 수 있습니다."
            )

        if symptom_case.patient.user_id != request.user.id:
            raise serializers.ValidationError(
                "본인의 증상 케이스만 선택할 수 있습니다."
            )

        if (
            symptom_case.status
            != PatientSymptomCase.Status.HOSPITAL_SELECTED
        ):
            raise serializers.ValidationError(
                "병원 선택이 완료된 증상 케이스만 전송할 수 있습니다."
            )

        if (
            recommendation.match_request.symptom_case_id
            != symptom_case.symptom_case_id
            or recommendation.match_request.patient.user_id
            != request.user.id
        ):
            raise serializers.ValidationError(
                {
                    "recommendation_id": (
                        "해당 증상 케이스의 추천 결과가 아닙니다."
                    )
                }
            )

        if (
            not recommendation.is_selected
            or recommendation.match_request.status
            != HospitalMatchRequest.Status.SELECTED
        ):
            raise serializers.ValidationError(
                {
                    "recommendation_id": (
                        "환자가 선택한 추천 병원만 전송할 수 있습니다."
                    )
                }
            )

        match_request = recommendation.match_request
        if (
            match_request.agreed_at is None
            or not all([
                match_request.personal_information_provision_agreed,
                match_request.information_items_purpose_confirmed,
                match_request.medical_consultation_use_agreed,
                match_request.withdrawal_right_confirmed,
            ])
        ):
            raise serializers.ValidationError(
                "병원 매칭 동의를 먼저 완료해 주세요."
            )

        if CaseTransfer.objects.filter(symptom_case=symptom_case).exists():
            raise serializers.ValidationError(
                "해당 증상 케이스의 전송 건이 이미 존재합니다."
            )

        if not symptom_case.diagnosis_document:
            raise serializers.ValidationError(
                "진단서가 등록된 증상 케이스만 전송할 수 있습니다."
            )

        if symptom_case.diagnosed_hospital is None:
            raise serializers.ValidationError(
                "시술받은 병원을 먼저 선택해주세요."
            )

        if (
            symptom_case.diagnosed_hospital.user_id
            == partner_hospital.id
        ):
            raise serializers.ValidationError(
                "시술 병원과 협력 병원은 달라야 합니다."
            )

        return attrs

    def create(self, validated_data):
        recommendation = validated_data["recommendation"]
        partner_hospital = recommendation.hospital.user
        validated_data.setdefault(
            "status",
            CaseTransfer.Status.PROCESSING,
        )

        return CaseTransfer.objects.create(
            **validated_data,
            patient=self.context["request"].user,
            partner_hospital=partner_hospital,
            target_language=(
                recommendation.hospital.language_code
            ),
        )


class CaseTransferDetailSerializer(serializers.ModelSerializer):
    case_number = serializers.SerializerMethodField()
    symptom_case_id = serializers.IntegerField(read_only=True)
    recommendation_id = serializers.IntegerField(read_only=True)
    medical_case_id = serializers.IntegerField(read_only=True)
    partner_hospital_id = serializers.IntegerField(read_only=True)
    partner_hospital_name = serializers.CharField(
        source="partner_hospital.name",
        read_only=True,
    )
    origin_hospital_name = serializers.CharField(
        source="medical_case.origin_hospital.name",
        read_only=True,
    )
    ai_translation_summary = serializers.CharField(
        source="medical_case.ai_summary",
        read_only=True,
    )
    collaboration_request_id = serializers.SerializerMethodField()
    collaboration_request_status = serializers.SerializerMethodField()

    class Meta:
        model = CaseTransfer
        fields = (
            "id",
            "case_number",
            "symptom_case_id",
            "recommendation_id",
            "medical_case_id",
            "partner_hospital_id",
            "partner_hospital_name",
            "origin_hospital_name",
            "ai_translation_summary",
            "patient_name",
            "patient_gender",
            "patient_birth_date",
            "target_language",
            "structured_data",
            "processing_error",
            "adverse_effects",
            "include_patient_info",
            "include_procedure_info",
            "include_adverse_effects",
            "include_clinician_note",
            "procedure_medication_agreed",
            "adverse_effect_clinician_note_agreed",
            "overseas_ai_processing_agreed",
            "agreed_at",
            "collaboration_request_id",
            "collaboration_request_status",
            "status",
            "transferred_at",
            "created_at",
        )
        read_only_fields = fields

    def get_case_number(self, obj):
        return format_medical_case_number(obj.medical_case)

    def get_collaboration_request(self, obj):
        try:
            return obj.medical_case.collaboration_request
        except CaseCollaborationRequest.DoesNotExist:
            return None

    def get_collaboration_request_id(self, obj):
        collaboration_request = self.get_collaboration_request(obj)
        return (
            collaboration_request.id
            if collaboration_request is not None
            else None
        )

    def get_collaboration_request_status(self, obj):
        collaboration_request = self.get_collaboration_request(obj)
        return (
            collaboration_request.status
            if collaboration_request is not None
            else None
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if instance.status != CaseTransfer.Status.PROCESSING_FAILED:
            data.pop("processing_error", None)

        return data


class CaseTransferListSerializer(serializers.ModelSerializer):
    case_number = serializers.SerializerMethodField()
    symptom_case_id = serializers.IntegerField(read_only=True)
    recommendation_id = serializers.IntegerField(read_only=True)
    medical_case_id = serializers.IntegerField(read_only=True)
    partner_hospital_id = serializers.IntegerField(read_only=True)
    partner_hospital_name = serializers.CharField(
        source="partner_hospital.name",
        read_only=True,
    )
    origin_hospital_name = serializers.CharField(
        source="medical_case.origin_hospital.name",
        read_only=True,
    )
    procedure_name = serializers.CharField(
        source="medical_case.procedure_name",
        read_only=True,
    )
    procedure_area = serializers.CharField(
        source="medical_case.procedure_area",
        read_only=True,
    )
    procedure_date = serializers.DateField(
        source="medical_case.procedure_date",
        read_only=True,
    )
    ai_translation_summary = serializers.CharField(
        source="medical_case.ai_summary",
        read_only=True,
    )

    class Meta:
        model = CaseTransfer
        fields = (
            "id",
            "case_number",
            "symptom_case_id",
            "recommendation_id",
            "medical_case_id",
            "patient_name",
            "partner_hospital_id",
            "partner_hospital_name",
            "origin_hospital_name",
            "procedure_name",
            "procedure_area",
            "procedure_date",
            "ai_translation_summary",
            "status",
            "created_at",
        )
        read_only_fields = fields

    def get_case_number(self, obj):
        return format_medical_case_number(obj.medical_case)


class PartnerCaseTransferSerializer(serializers.ModelSerializer):
    case_number = serializers.SerializerMethodField()
    partner_hospital_name = serializers.CharField(
        source="partner_hospital.name",
        read_only=True,
    )
    origin_hospital_name = serializers.CharField(
        source="medical_case.origin_hospital.name",
        read_only=True,
    )
    ai_translation_summary = serializers.CharField(
        source="medical_case.ai_summary",
        read_only=True,
    )
    transmitted_data = serializers.SerializerMethodField()
    agreements = serializers.SerializerMethodField()
    collaboration_request_id = serializers.SerializerMethodField()
    collaboration_request_status = serializers.SerializerMethodField()

    class Meta:
        model = CaseTransfer
        fields = (
            "id",
            "case_number",
            "symptom_case_id",
            "recommendation_id",
            "medical_case_id",
            "partner_hospital_id",
            "partner_hospital_name",
            "origin_hospital_name",
            "target_language",
            "ai_translation_summary",
            "transmitted_data",
            "agreements",
            "collaboration_request_id",
            "collaboration_request_status",
            "status",
            "transferred_at",
            "created_at",
        )
        read_only_fields = fields

    def get_case_number(self, obj):
        return format_medical_case_number(obj.medical_case)

    def get_collaboration_request(self, obj):
        try:
            return obj.medical_case.collaboration_request
        except CaseCollaborationRequest.DoesNotExist:
            return None

    def get_collaboration_request_id(self, obj):
        collaboration_request = self.get_collaboration_request(obj)
        return (
            collaboration_request.id
            if collaboration_request is not None
            else None
        )

    def get_collaboration_request_status(self, obj):
        collaboration_request = self.get_collaboration_request(obj)
        return (
            collaboration_request.status
            if collaboration_request is not None
            else None
        )

    def get_transmitted_data(self, obj):
        structured = obj.structured_data or {}
        data = {
            "symptoms": structured.get("symptoms", {}),
        }

        if obj.include_patient_info:
            data["patient_info"] = structured.get(
                "patient_info",
                {},
            )

        if obj.include_procedure_info:
            data["procedure"] = structured.get("procedure", {})
            data["ingredients"] = structured.get("ingredients", [])

        if obj.include_adverse_effects:
            names = ADVERSE_EFFECT_LABELS.get(
                obj.target_language,
                ADVERSE_EFFECT_LABELS["en"],
            )
            data["adverse_effects"] = [
                {
                    "code": effect,
                    "translated_name": names.get(effect, effect),
                }
                for effect in obj.adverse_effects
            ]

        if obj.include_clinician_note:
            data["clinician_note"] = structured.get(
                "clinician_note",
                "",
            )

        return data

    def get_agreements(self, obj):
        return {
            "procedure_medication": (
                obj.procedure_medication_agreed
            ),
            "adverse_effect_clinician_note": (
                obj.adverse_effect_clinician_note_agreed
            ),
            "overseas_ai_processing": (
                obj.overseas_ai_processing_agreed
            ),
            "agreed_at": obj.agreed_at,
        }


class CaseTransferReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseTransfer
        fields = (
            "procedure_medication_agreed",
            "adverse_effect_clinician_note_agreed",
            "overseas_ai_processing_agreed",
        )

    def validate(self, attrs):
        if self.instance.status != CaseTransfer.Status.REVIEW_REQUIRED:
            raise serializers.ValidationError(
                "번역·구조화 완료 후 입력할 수 있습니다."
            )

        if not all([
            attrs.get("procedure_medication_agreed", False),
            attrs.get(
                "adverse_effect_clinician_note_agreed",
                False,
            ),
            attrs.get("overseas_ai_processing_agreed", False),
        ]):
            raise serializers.ValidationError(
                "필수 동의가 필요합니다."
            )

        return attrs

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)

        structured_data = instance.structured_data or {}
        adverse_effects = list(
            instance.symptom_case.symptom_types.values_list(
                "symptom_type",
                flat=True,
            )
        )

        instance.adverse_effects = list(
            dict.fromkeys(adverse_effects)
        )
        instance.include_patient_info = bool(
            structured_data.get("patient_info")
        )
        instance.include_procedure_info = bool(
            structured_data.get("procedure")
            or structured_data.get("ingredients")
        )
        instance.include_adverse_effects = bool(
            instance.adverse_effects
        )
        instance.include_clinician_note = bool(
            structured_data.get("clinician_note")
        )

        instance.agreed_at = timezone.now()
        instance.status = CaseTransfer.Status.READY_TO_TRANSFER
        instance.save()

        return instance
