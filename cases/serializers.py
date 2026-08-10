from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.models import User
from .models import (
    CaseAdverseEffect,
    CaseChatMessage,
    CaseIngredient,
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