import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ..models import (
    CaseAgreement,
    CaseAgreementRevision,
    CaseAgreementReview,
    CaseCollaborationRequest,
    CaseTransfer,
)
from ..serializers import (
    CaseAgreementSerializer,
    get_agreement_language_content,
)
from .ai import (
    normalize_agreement_language,
    translate_case_agreement_content,
    translate_case_agreement_opinion,
)

logger = logging.getLogger(__name__)


def build_additional_opinion_translation_values(
    additional_opinion,
    source_language,
):
    if not additional_opinion:
        return {
            "additional_opinion_source_language": "",
            "additional_opinion_translations": {},
            "additional_opinion_translation_status": (
                CaseAgreement.OpinionTranslationStatus.NOT_REQUESTED
            ),
            "additional_opinion_translation_error_code": "",
        }

    source_language = normalize_agreement_language(source_language)
    try:
        translations = translate_case_agreement_opinion(
            additional_opinion,
            source_language,
        )
    except Exception:
        logger.exception("Case agreement opinion translation failed")
        return {
            "additional_opinion_source_language": source_language,
            "additional_opinion_translations": {
                source_language: additional_opinion,
            },
            "additional_opinion_translation_status": (
                CaseAgreement.OpinionTranslationStatus.FAILED
            ),
            "additional_opinion_translation_error_code": (
                "OPENAI_TRANSLATION_FAILED"
            ),
        }

    return {
        "additional_opinion_source_language": source_language,
        "additional_opinion_translations": translations,
        "additional_opinion_translation_status": (
            CaseAgreement.OpinionTranslationStatus.COMPLETED
        ),
        "additional_opinion_translation_error_code": "",
    }


@transaction.atomic
def edit_case_agreement(*, chat_room, hospital, data, request):
    agreement = get_object_or_404(
        CaseAgreement.objects.select_for_update(),
        chat_room=chat_room,
    )
    if agreement.status == CaseAgreement.Status.FINAL:
        raise ValidationError(
            {"detail": "최종 합의가 완료된 후에는 수정할 수 없습니다."}
        )

    serializer = CaseAgreementSerializer(
        agreement,
        data=data,
        partial=True,
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)

    editable_fields = (
        "judgment_draft",
        "evidence_items",
        "additional_opinion",
    )
    source_language = normalize_agreement_language(
        hospital.preferred_language
    )
    current_localized = get_agreement_language_content(
        agreement,
        source_language,
    )
    current_values = {
        "judgment_draft": current_localized["judgment_draft"],
        "evidence_items": current_localized["evidence_items"],
        "additional_opinion": agreement.additional_opinion,
    }
    changed_fields = [
        field
        for field in editable_fields
        if field in serializer.validated_data
        and current_values[field] != serializer.validated_data[field]
    ]
    if not changed_fields:
        return agreement, []

    def date_value(value):
        return value.isoformat() if hasattr(value, "isoformat") else value

    previous_data = {
        field: date_value(getattr(agreement, field))
        for field in editable_fields
    }
    CaseAgreementRevision.objects.create(
        agreement=agreement,
        version=agreement.version,
        previous_data=previous_data,
        changed_fields=changed_fields,
        edited_by=hospital,
    )

    save_values = {}
    localized_fields_changed = any(
        field in changed_fields
        for field in ("judgment_draft", "evidence_items")
    )
    if localized_fields_changed:
        candidate_judgment = serializer.validated_data.get(
            "judgment_draft",
            current_values["judgment_draft"],
        )
        candidate_evidence = serializer.validated_data.get(
            "evidence_items",
            current_values["evidence_items"],
        )
        try:
            localized_content = translate_case_agreement_content(
                candidate_judgment,
                candidate_evidence,
                source_language,
            )
        except Exception:
            logger.exception("Case agreement content translation failed")
            localized_content = {
                source_language: {
                    "judgment_draft": candidate_judgment,
                    "evidence_items": candidate_evidence,
                }
            }

        canonical_content = localized_content.get(
            "ko",
            localized_content[source_language],
        )
        save_values.update(
            {
                "judgment_draft": canonical_content["judgment_draft"],
                "evidence_items": canonical_content["evidence_items"],
                "localized_content": localized_content,
            }
        )

    if "additional_opinion" in changed_fields:
        save_values.update(
            build_additional_opinion_translation_values(
                serializer.validated_data["additional_opinion"],
                source_language,
            )
        )

    agreement = serializer.save(
        version=agreement.version + 1,
        status=CaseAgreement.Status.IN_REVIEW,
        edited_by=hospital,
        edited_at=timezone.now(),
        finalized_at=None,
        **save_values,
    )
    return agreement, changed_fields


def complete_case_agreement(agreement, chat_room):
    completed_at = timezone.now()
    agreement.status = CaseAgreement.Status.FINAL
    agreement.finalized_at = completed_at
    agreement.revision_requested_by = None
    agreement.revision_requested_at = None
    agreement.save(
        update_fields=(
            "status",
            "finalized_at",
            "revision_requested_by",
            "revision_requested_at",
            "updated_at",
        )
    )

    collaboration_request = (
        CaseCollaborationRequest.objects
        .filter(medical_case=chat_room.medical_case)
        .first()
    )
    if collaboration_request is not None:
        collaboration_request.status = CaseCollaborationRequest.Status.COMPLETED
        collaboration_request.completed_at = completed_at
        collaboration_request.save(
            update_fields=(
                "status",
                "completed_at",
                "updated_at",
            )
        )

    transfer = (
        chat_room.medical_case.case_transfers
        .select_related("symptom_case")
        .filter(status=CaseTransfer.Status.TRANSFERRED)
        .first()
    )
    if transfer is not None:
        symptom_case = transfer.symptom_case
        symptom_case.status = symptom_case.Status.COMPLETED
        symptom_case.save(update_fields=["status", "updated_at"])


@transaction.atomic
def review_case_agreement(*, chat_room, hospital):
    agreement = get_object_or_404(
        CaseAgreement.objects.select_for_update(),
        chat_room=chat_room,
    )
    if agreement.status == CaseAgreement.Status.FINAL:
        raise ValidationError("이미 최종 합의가 완료되었습니다.")

    CaseAgreementReview.objects.update_or_create(
        agreement=agreement,
        hospital=hospital,
        defaults={
            "reviewed_version": agreement.version,
            "reviewed_at": timezone.now(),
        },
    )

    participant_ids = {
        chat_room.medical_case.origin_hospital_id,
        chat_room.partner_hospital_id,
    }
    reviewed_ids = set(
        agreement.reviews.filter(
            reviewed_version=agreement.version,
        ).values_list("hospital_id", flat=True)
    )

    if reviewed_ids == participant_ids:
        complete_case_agreement(agreement, chat_room)
    else:
        agreement.status = CaseAgreement.Status.IN_REVIEW
        agreement.save(update_fields=("status", "updated_at"))

    return agreement
