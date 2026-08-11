from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from selfsymptoms.models import PatientSymptomCase
from selfsymptoms.serializers import PatientSymptomCaseSerializer

from accounts.models import User
from .models import (
    CaseAgreement,
    CaseAgreementRevision,
    CaseAdverseEffect,
    CaseIngredient,
    CaseSyncRequest,
    CaseChatMessage,
    CaseCollaborationRequest,
    MedicalCase,
)


class CaseIngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseIngredient
        fields = (
            "id",
            "ingredient_name",
        )


class CaseAdverseEffectSerializer(serializers.ModelSerializer):
    effect_name = serializers.CharField(
        source="get_effect_type_display",
        read_only=True,
    )

    class Meta:
        model = CaseAdverseEffect
        fields = (
            "id",
            "effect_type",
            "effect_name",
        )


class MedicalCaseCreateSerializer(serializers.ModelSerializer):
    patient_id = serializers.PrimaryKeyRelatedField(
        source="patient",
        queryset=User.objects.filter(user_type="PATIENT"),
        write_only=True,
    )

    # AI 매칭 결과로 전달받은 병원 ID
    partner_hospital_id = serializers.PrimaryKeyRelatedField(
        source="partner_hospital",
        queryset=User.objects.filter(user_type="HOSPITAL"),
        write_only=True,
    )

    ingredients = serializers.ListField(
        child=serializers.CharField(max_length=150),
        allow_empty=False,
        write_only=True,
    )

    class Meta:
        model = MedicalCase
        fields = (
            "id",
            "patient_id",
            "partner_hospital_id",
            "procedure_name",
            "procedure_area",
            "procedure_date",
            "ingredients",
            "clinician_note",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        origin_hospital = self.context["request"].user
        partner_hospital = attrs["partner_hospital"]

        if origin_hospital == partner_hospital:
            raise serializers.ValidationError(
                {
                    "partner_hospital_id":
                        "기존 병원과 협진 병원은 달라야 합니다."
                }
            )

        # TODO: AI 매칭 기능과 연결한 뒤
        # 실제로 수락된 병원인지 검증

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        ingredient_names = validated_data.pop("ingredients")

        medical_case = MedicalCase.objects.create(
            **validated_data
        )

        CaseIngredient.objects.bulk_create(
            [
                CaseIngredient(
                    medical_case=medical_case,
                    ingredient_name=name,
                )
                for name in set(ingredient_names)
            ]
        )

        return medical_case


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

    adverse_effects = CaseAdverseEffectSerializer(
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
            "adverse_effects",
            "clinician_note",
            "ai_summary",
            "status",
            "transferred_at",
        )


class CaseCollaborationRequestSerializer(
    serializers.ModelSerializer
):
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

    class Meta:
        model = CaseCollaborationRequest

        fields = (
            "id",
            "medical_case_id",
            "medical_case",
            "origin_hospital_id",
            "origin_hospital_name",
            "partner_hospital_id",
            "partner_hospital_name",
            "status",
            "chat_room_id",
            "requested_at",
            "accepted_at",
            "rejected_at",
            "created_at",
            "updated_at",
        )

        read_only_fields = fields

    def get_chat_room_id(self, obj):
        room = obj.medical_case.chat_rooms.filter(
            partner_hospital_id=(
                obj.medical_case.partner_hospital_id
            ),
        ).first()

        return room.id if room else None




class AdverseEffectUpdateSerializer(serializers.Serializer):
    effect_types = serializers.ListField(
        child=serializers.ChoiceField(
            choices=CaseAdverseEffect.EffectType.choices,
        ),
        allow_empty=False,
    )

    def validate(self, attrs):
        medical_case = self.context["medical_case"]

        if medical_case.status == MedicalCase.Status.TRANSFERRED:
            raise serializers.ValidationError(
                {
                    "detail": "이미 전송된 케이스는 수정할 수 없습니다."
                }
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        medical_case = self.context["medical_case"]

        medical_case.adverse_effects.all().delete()

        CaseAdverseEffect.objects.bulk_create(
            [
                CaseAdverseEffect(
                    medical_case=medical_case,
                    effect_type=effect_type,
                )
                for effect_type in set(
                    validated_data["effect_types"]
                )
            ]
        )

        medical_case.status = (
            MedicalCase.Status.READY_TO_TRANSFER
        )
        medical_case.save(update_fields=["status"])

        return medical_case


class CaseTransferSerializer(serializers.ModelSerializer):
    procedure_info_agreed = serializers.BooleanField()
    adverse_effect_info_agreed = serializers.BooleanField()
    overseas_transfer_agreed = serializers.BooleanField()

    class Meta:
        model = MedicalCase
        fields = (
            "procedure_info_agreed",
            "adverse_effect_info_agreed",
            "overseas_transfer_agreed",
        )

    def validate(self, attrs):
        errors = {}

        if not attrs.get("procedure_info_agreed"):
            errors["procedure_info_agreed"] = (
                "시술 및 약물 정보 전송 동의는 필수입니다."
            )

        if not attrs.get("adverse_effect_info_agreed"):
            errors["adverse_effect_info_agreed"] = (
                "부작용 및 의료진 소견 전송 동의는 필수입니다."
            )

        if not attrs.get("overseas_transfer_agreed"):
            errors["overseas_transfer_agreed"] = (
                "국외 의료기관 정보 전송 동의는 필수입니다."
            )

        if (
            self.instance.status
            != MedicalCase.Status.READY_TO_TRANSFER
        ):
            errors["detail"] = (
                "부작용 입력을 먼저 완료해야 합니다."
            )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.status = MedicalCase.Status.TRANSFERRED
        instance.transferred_at = timezone.now()
        instance.save()

        return instance


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

    def validate_content(self, value):
        if not value:
            raise serializers.ValidationError(
                "메시지 내용을 입력해 주세요."
            )

        return value


class CaseSyncRequestCreateSerializer(
    serializers.ModelSerializer
):
    symptom_case_id = serializers.PrimaryKeyRelatedField(
        source="symptom_case",
        queryset=PatientSymptomCase.objects.all(),
    )

    origin_hospital_id = (
        serializers.PrimaryKeyRelatedField(
            source="origin_hospital",
            queryset=User.objects.filter(
                user_type=User.UserType.HOSPITAL,
            ),
        )
    )

    partner_hospital_id = (
        serializers.PrimaryKeyRelatedField(
            source="partner_hospital",
            queryset=User.objects.filter(
                user_type=User.UserType.HOSPITAL,
            ),
        )
    )

    class Meta:
        model = CaseSyncRequest
        fields = (
            "id",
            "patient_name",
            "patient_gender",
            "patient_birth_date",
            "symptom_case_id",
            "origin_hospital_id",
            "partner_hospital_id",
            "selection_source",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        request = self.context["request"]
        symptom_case = attrs["symptom_case"]
        origin_hospital = attrs["origin_hospital"]
        partner_hospital = attrs["partner_hospital"]

        if request.user.user_type != User.UserType.PATIENT:
            raise serializers.ValidationError(
                "환자만 동기화를 요청할 수 있습니다."
            )

        if (
            symptom_case.patient.user_id
            != request.user.id
        ):
            raise serializers.ValidationError(
                {
                    "symptom_case_id": (
                        "본인의 증상 케이스만 "
                        "선택할 수 있습니다."
                    )
                }
            )

        if origin_hospital == partner_hospital:
            raise serializers.ValidationError(
                {
                    "partner_hospital_id": (
                        "시술 병원과 상대 병원은 "
                        "달라야 합니다."
                    )
                }
            )

        duplicate_exists = (
            CaseSyncRequest.objects.filter(
                patient=request.user,
                symptom_case=symptom_case,
                status__in=[
                    CaseSyncRequest.Status.REQUESTED,
                    CaseSyncRequest.Status.HOSPITAL_REVIEWED,
                    CaseSyncRequest.Status.PATIENT_CONSENTED,
                    CaseSyncRequest.Status.SENT_TO_PARTNER,
                ],
            ).exists()
        )

        if duplicate_exists:
            raise serializers.ValidationError(
                "해당 증상에 대해 진행 중인 요청이 있습니다."
            )

        return attrs


class CaseSyncRequestDetailSerializer(
    serializers.ModelSerializer
):
    patient_id = serializers.IntegerField(
        source="patient.id",
        read_only=True,
    )

    symptom_case = PatientSymptomCaseSerializer(
        read_only=True,
    )

    origin_hospital_id = serializers.IntegerField(
        source="origin_hospital.id",
        read_only=True,
    )

    origin_hospital_name = serializers.CharField(
        source="origin_hospital.name",
        read_only=True,
    )

    partner_hospital_id = serializers.IntegerField(
        source="partner_hospital.id",
        read_only=True,
    )

    partner_hospital_name = serializers.CharField(
        source="partner_hospital.name",
        read_only=True,
    )

    medical_case_id = serializers.IntegerField(
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = CaseSyncRequest
        fields = (
            "id",
            "patient_id",
            "patient_name",
            "patient_gender",
            "patient_birth_date",
            "symptom_case",
            "origin_hospital_id",
            "origin_hospital_name",
            "partner_hospital_id",
            "partner_hospital_name",
            "medical_case_id",
            "selection_source",
            "status",
            "reviewed_at",
            "created_at",
            "updated_at",
        )


class CaseCollaborationRequestDetailSerializer(
    CaseCollaborationRequestSerializer
):
    sync_request = serializers.SerializerMethodField()

    class Meta(
        CaseCollaborationRequestSerializer.Meta
    ):
        fields = (
            CaseCollaborationRequestSerializer
            .Meta
            .fields
            + (
                "sync_request",
            )
        )

        read_only_fields = fields

    def get_sync_request(self, obj):
        try:
            sync_request = (
                obj.medical_case.sync_request
            )
        except CaseSyncRequest.DoesNotExist:
            return None

        return CaseSyncRequestDetailSerializer(
            sync_request,
            context=self.context,
        ).data


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
    changed_fields = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    requires_re_review = serializers.SerializerMethodField()

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
            "observation_days",
            "photo_upload_date",
            "follow_up_date",
            "precautions",
            "patient_message",
            "status",
            "version",
            "edited_by_name",
            "edited_at",
            "finalized_at",
            "reviews",
            "changed_fields",
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
            "edited_by_name",
            "edited_at",
            "finalized_at",
            "reviews",
            "changed_fields",
            "can_edit",
            "requires_re_review",
            "created_at",
            "updated_at",
            "revision_requested_by_name",
            "revision_requested_at",
        )

    def validate_evidence_items(self, items):
        if not items:
            raise serializers.ValidationError(
                "주요 근거를 한 개 이상 입력해주세요."
            )

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

    def validate(self, attrs):
        photo_date = attrs.get(
            "photo_upload_date",
            getattr(self.instance, "photo_upload_date", None),
        )
        follow_up_date = attrs.get(
            "follow_up_date",
            getattr(self.instance, "follow_up_date", None),
        )

        if (
            photo_date is not None
            and follow_up_date is not None
            and follow_up_date < photo_date
        ):
            raise serializers.ValidationError(
                {
                    "follow_up_date": (
                        "추가 확인일은 사진 재업로드일보다 "
                        "빠를 수 없습니다."
                    )
                }
            )

        return attrs

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

    def get_changed_fields(self, obj):
        latest_revision = obj.revisions.first()

        if latest_revision is None:
            return []

        return latest_revision.changed_fields

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