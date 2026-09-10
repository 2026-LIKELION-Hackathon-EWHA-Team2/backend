from rest_framework import serializers

from ..models import (
    CaseAgreement,
    CaseAgreementRevision,
)
from ..services import normalize_agreement_language


def get_agreement_language_content(agreement, requested_language):
    language = normalize_agreement_language(requested_language)
    localized_content = agreement.localized_content or {}

    localized = localized_content.get(language)
    display_language = language

    if not isinstance(localized, dict):
        localized = localized_content.get("ko")
        display_language = "ko"

    if not isinstance(localized, dict):
        localized = {}
        for fallback_language, fallback_content in (
            localized_content.items()
        ):
            if isinstance(fallback_content, dict):
                localized = fallback_content
                display_language = normalize_agreement_language(
                    fallback_language
                )
                break

    return {
        "judgment_draft": localized.get(
            "judgment_draft",
            agreement.judgment_draft,
        ),
        "evidence_items": localized.get(
            "evidence_items",
            agreement.evidence_items,
        ),
        "display_language": display_language,
    }


def get_agreement_opinion_content(agreement, requested_language):
    language = normalize_agreement_language(requested_language)
    original_content = agreement.additional_opinion
    source_language = agreement.additional_opinion_source_language
    if source_language:
        source_language = normalize_agreement_language(source_language)
    translations = agreement.additional_opinion_translations or {}
    translated_content = None

    if (
        agreement.additional_opinion_translation_status
        == CaseAgreement.OpinionTranslationStatus.COMPLETED
    ):
        translated_content = translations.get(language)

    if source_language and language == source_language:
        display_content = original_content
        display_language = source_language
    elif translated_content:
        display_content = translated_content
        display_language = language
    else:
        display_content = original_content
        display_language = source_language

    return {
        "original_content": original_content,
        "source_language": source_language if original_content else None,
        "translated_content": translated_content,
        "translation_status": (
            agreement.additional_opinion_translation_status or None
        ),
        "display_content": display_content,
        "display_language": (
            display_language if original_content else None
        ),
    }


class EvidenceItemSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=100)
    content = serializers.CharField(max_length=1000)
    order = serializers.IntegerField(min_value=1)


class CaseAgreementSerializer(serializers.ModelSerializer):
    evidence_items = EvidenceItemSerializer(many=True)
    additional_opinion_original_content = serializers.CharField(
        source="additional_opinion",
        read_only=True,
    )
    additional_opinion_translated_content = (
        serializers.SerializerMethodField()
    )
    additional_opinion_translation_status = (
        serializers.SerializerMethodField()
    )
    additional_opinion_display_content = (
        serializers.SerializerMethodField()
    )
    additional_opinion_display_language = (
        serializers.SerializerMethodField()
    )
    edited_by_name = serializers.CharField(
        source="edited_by.name",
        read_only=True,
        default=None,
    )
    reviews = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    requires_re_review = serializers.SerializerMethodField()
    latest_edit = serializers.SerializerMethodField()
    my_review_completed = serializers.SerializerMethodField()
    counterpart_review_completed = serializers.SerializerMethodField()
    all_reviews_completed = serializers.SerializerMethodField()
    can_finalize = serializers.SerializerMethodField()
    primary_action = serializers.SerializerMethodField()

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
            "additional_opinion_original_content",
            "additional_opinion_source_language",
            "additional_opinion_translated_content",
            "additional_opinion_translation_status",
            "additional_opinion_display_content",
            "additional_opinion_display_language",
            "status",
            "version",
            "latest_edit",
            "edited_by_name",
            "edited_at",
            "finalized_at",
            "reviews",
            "can_edit",
            "requires_re_review",
            "my_review_completed",
            "counterpart_review_completed",
            "all_reviews_completed",
            "can_finalize",
            "primary_action",
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
            "additional_opinion_original_content",
            "additional_opinion_source_language",
            "additional_opinion_translated_content",
            "additional_opinion_translation_status",
            "additional_opinion_display_content",
            "additional_opinion_display_language",
            "latest_edit",
            "edited_by_name",
            "edited_at",
            "finalized_at",
            "reviews",
            "can_edit",
            "requires_re_review",
            "my_review_completed",
            "counterpart_review_completed",
            "all_reviews_completed",
            "can_finalize",
            "primary_action",
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

    @staticmethod
    def get_current_reviewed_hospital_ids(obj):
        cache_name = "_current_reviewed_hospital_ids"
        if hasattr(obj, cache_name):
            return getattr(obj, cache_name)

        reviewed_ids = {
            review.hospital_id
            for review in obj.reviews.all()
            if review.reviewed_version == obj.version
        }
        setattr(obj, cache_name, reviewed_ids)
        return reviewed_ids

    def get_participant_ids(self, obj):
        return {
            obj.chat_room.medical_case.origin_hospital_id,
            obj.chat_room.partner_hospital_id,
        }

    def get_my_review_completed(self, obj):
        request = self.context.get("request")
        if request is None:
            return False
        return request.user.id in self.get_current_reviewed_hospital_ids(obj)

    def get_counterpart_review_completed(self, obj):
        request = self.context.get("request")
        if request is None:
            return False

        counterpart_ids = self.get_participant_ids(obj) - {request.user.id}
        return counterpart_ids.issubset(
            self.get_current_reviewed_hospital_ids(obj)
        )

    def get_all_reviews_completed(self, obj):
        return self.get_current_reviewed_hospital_ids(
            obj
        ) == self.get_participant_ids(obj)

    def get_can_finalize(self, obj):
        request = self.context.get("request")
        if request is None or obj.status == CaseAgreement.Status.FINAL:
            return False

        reviewed_ids = self.get_current_reviewed_hospital_ids(obj)
        counterpart_ids = self.get_participant_ids(obj) - {request.user.id}
        return bool(
            request.user.id in self.get_participant_ids(obj)
            and request.user.id not in reviewed_ids
            and counterpart_ids.issubset(reviewed_ids)
        )

    def get_primary_action(self, obj):
        if obj.status == CaseAgreement.Status.FINAL:
            return {
                "code": "VIEW_FINAL",
                "label": "최종 합의안 보기",
                "enabled": True,
            }

        if not self.get_my_review_completed(obj):
            if self.get_counterpart_review_completed(obj):
                return {
                    "code": "FINALIZE",
                    "label": "최종 합의 완료",
                    "enabled": True,
                }
            return {
                "code": "REVIEW",
                "label": "검토 완료",
                "enabled": True,
            }

        return {
            "code": "WAITING_FOR_COUNTERPART",
            "label": "상대 검토 대기",
            "enabled": False,
        }

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
        return (
            obj.status == CaseAgreement.Status.IN_REVIEW
            and any(
                review.reviewed_version != obj.version
                for review in obj.reviews.all()
            )
        )

    def get_opinion_content(self, obj):
        request = self.context.get("request")
        requested_language = (
            request.user.preferred_language
            if request is not None
            else "ko"
        )
        return get_agreement_opinion_content(
            obj,
            requested_language,
        )

    def get_additional_opinion_translated_content(self, obj):
        return self.get_opinion_content(obj)["translated_content"]

    def get_additional_opinion_translation_status(self, obj):
        return self.get_opinion_content(obj)["translation_status"]

    def get_additional_opinion_display_content(self, obj):
        return self.get_opinion_content(obj)["display_content"]

    def get_additional_opinion_display_language(self, obj):
        return self.get_opinion_content(obj)["display_language"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")

        if request is None:
            return data

        localized = get_agreement_language_content(
            instance,
            request.user.preferred_language,
        )
        data["judgment_draft"] = localized["judgment_draft"]
        data["evidence_items"] = localized["evidence_items"]
        data["display_language"] = localized["display_language"]
        return data


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
