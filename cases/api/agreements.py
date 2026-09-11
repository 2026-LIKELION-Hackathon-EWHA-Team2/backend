import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import (
    PermissionDenied,
    ValidationError,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import (
    CaseAgreement,
    CaseAgreementReview,
    CaseAgreementRevision,
    CaseChatRoom,
    CaseCollaborationRequest,
    CaseTransfer,
)
from ..selectors.agreement_queries import (
    get_agreement_chat_room_queryset,
    get_agreement_detail_queryset,
    get_agreement_revisions,
)
from ..services import (
    SUPPORTED_AGREEMENT_LANGUAGES,
    generate_case_agreement,
    normalize_agreement_language,
    translate_case_agreement_content,
    translate_case_agreement_opinion,
)
from ..serializers import (
    CaseAgreementSerializer,
    CaseAgreementRevisionSerializer,
    get_agreement_language_content,
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

def get_agreement_chat_room(request, case_id, room_id):
    if request.user.user_type != "HOSPITAL":
        raise PermissionDenied("병원 회원만 이용할 수 있습니다.")

    chat_room = get_object_or_404(
        get_agreement_chat_room_queryset(),
        id=room_id,
        medical_case_id=case_id,
    )

    participant_ids = {
        chat_room.medical_case.origin_hospital_id,
        chat_room.partner_hospital_id,
    }

    if request.user.id not in participant_ids:
        raise PermissionDenied(
            "해당 협진 합의에 접근할 권한이 없습니다."
        )

    return chat_room

class CaseAgreementDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        agreement = get_object_or_404(
            get_agreement_detail_queryset(),
            chat_room=chat_room,
        )

        serializer = CaseAgreementSerializer(
            agreement,
            context={"request": request},
        )
        return Response(serializer.data)

    def post(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        if CaseAgreement.objects.filter(
            chat_room=chat_room
        ).exists():
            raise ValidationError(
                "이미 생성된 협진 합의안이 있습니다."
            )

        serializer = CaseAgreementSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        opinion_translation_values = (
            build_additional_opinion_translation_values(
                serializer.validated_data.get(
                    "additional_opinion",
                    "",
                ),
                request.user.preferred_language,
            )
        )

        agreement = serializer.save(
            chat_room=chat_room,
            status=CaseAgreement.Status.AI_DRAFT,
            **opinion_translation_values,
        )

        return Response(
            CaseAgreementSerializer(
                agreement,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def patch(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        with transaction.atomic():
            agreement = get_object_or_404(
                CaseAgreement.objects.select_for_update(),
                chat_room=chat_room,
            )

            if agreement.status == CaseAgreement.Status.FINAL:
                raise ValidationError(
                    {
                        "detail": (
                            "최종 합의가 완료된 후에는 "
                            "수정할 수 없습니다."
                        )
                    }
                )

            serializer = CaseAgreementSerializer(
                agreement,
                data=request.data,
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
                request.user.preferred_language
            )
            current_localized = get_agreement_language_content(
                agreement,
                source_language,
            )
            current_values = {
                "judgment_draft": current_localized[
                    "judgment_draft"
                ],
                "evidence_items": current_localized[
                    "evidence_items"
                ],
                "additional_opinion": agreement.additional_opinion,
            }

            changed_fields = [
                field
                for field in editable_fields
                if field in serializer.validated_data
                and current_values[field]
                != serializer.validated_data[field]
            ]

            if not changed_fields:
                response_data = CaseAgreementSerializer(
                    agreement,
                    context={"request": request},
                ).data
                response_data["changed_fields"] = []
                return Response(response_data)

            def date_value(value):
                return (
                    value.isoformat()
                    if hasattr(value, "isoformat")
                    else value
                )

            previous_data = {
                field: date_value(getattr(agreement, field))
                for field in editable_fields
            }

            CaseAgreementRevision.objects.create(
                agreement=agreement,
                version=agreement.version,
                previous_data=previous_data,
                changed_fields=changed_fields,
                edited_by=request.user,
            )

            save_values = {}
            localized_fields_changed = any(
                field in changed_fields
                for field in (
                    "judgment_draft",
                    "evidence_items",
                )
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
                    localized_content = (
                        translate_case_agreement_content(
                            candidate_judgment,
                            candidate_evidence,
                            source_language,
                        )
                    )
                except Exception:
                    logger.exception(
                        "Case agreement content translation failed"
                    )
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
                        "judgment_draft": canonical_content[
                            "judgment_draft"
                        ],
                        "evidence_items": canonical_content[
                            "evidence_items"
                        ],
                        "localized_content": localized_content,
                    }
                )

            if "additional_opinion" in changed_fields:
                save_values.update(
                    build_additional_opinion_translation_values(
                        serializer.validated_data[
                            "additional_opinion"
                        ],
                        source_language,
                    )
                )

            agreement = serializer.save(
                version=agreement.version + 1,
                status=CaseAgreement.Status.IN_REVIEW,
                edited_by=request.user,
                edited_at=timezone.now(),
                finalized_at=None,
                **save_values,
            )

        response_data = CaseAgreementSerializer(
            agreement,
            context={"request": request},
        ).data
        response_data["changed_fields"] = changed_fields

        return Response(response_data)



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
        collaboration_request.status = (
            CaseCollaborationRequest.Status.COMPLETED
        )
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
        symptom_case.save(
            update_fields=["status", "updated_at"]
        )


class CaseAgreementReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        with transaction.atomic():
            agreement = get_object_or_404(
                CaseAgreement.objects.select_for_update(),
                chat_room=chat_room,
            )

            if agreement.status == CaseAgreement.Status.FINAL:
                raise ValidationError(
                    "이미 최종 합의가 완료되었습니다."
                )

            CaseAgreementReview.objects.update_or_create(
                agreement=agreement,
                hospital=request.user,
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
                agreement.save(
                    update_fields=(
                        "status",
                        "updated_at",
                    )
                )

        return Response(
            CaseAgreementSerializer(
                agreement,
                context={"request": request},
            ).data
        )

class CaseAgreementRevisionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        agreement = get_object_or_404(
            CaseAgreement,
            chat_room=chat_room,
        )

        revisions = get_agreement_revisions(agreement)

        serializer = CaseAgreementRevisionSerializer(
            revisions,
            many=True,
        )

        return Response(
            {
                "agreement_id": agreement.id,
                "current_version": agreement.version,
                "revisions": serializer.data,
            }
        )

class CaseAgreementGenerateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, case_id, room_id):
        chat_room = get_agreement_chat_room(
            request,
            case_id,
            room_id,
        )

        if CaseAgreement.objects.filter(
            chat_room=chat_room,
        ).exists():
            raise ValidationError(
                {
                    "detail": (
                        "이미 생성된 협진 합의안이 있습니다."
                    )
                }
            )

        messages = list(
            chat_room.messages
            .select_related("sender")
            .order_by("id")
        )

        medical_case = chat_room.medical_case
        case_transfer = (
            medical_case.case_transfers
            .filter(status=CaseTransfer.Status.TRANSFERRED)
            .first()
        )
        adverse_effects = (
            case_transfer.adverse_effects
            if case_transfer is not None
            else []
        )

        case_data = {
            "procedure_name": medical_case.procedure_name,
            "procedure_area": medical_case.procedure_area,
            "procedure_date": (
                medical_case.procedure_date.isoformat()
            ),
            "ingredients": list(
                medical_case.ingredients.values_list(
                    "ingredient_name",
                    flat=True,
                )
            ),
            "adverse_effects": adverse_effects,
            "clinician_note": medical_case.clinician_note,
        }

        try:
            generated_data = generate_case_agreement(
                case_data=case_data,
                messages=messages,
            )
        except Exception:
            logger.exception(
                "OpenAI agreement generation failed"
            )
            return Response(
                {
                    "detail": (
                        "AI 합의안 초안을 생성하지 못했습니다."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        localized_content = {
            language: {
                "judgment_draft": generated_data[language][
                    "judgment_draft"
                ],
                "evidence_items": generated_data[language][
                    "evidence_items"
                ],
            }
            for language in SUPPORTED_AGREEMENT_LANGUAGES
            if (
                isinstance(generated_data.get(language), dict)
                and "judgment_draft" in generated_data[language]
                and "evidence_items" in generated_data[language]
            )
        }

        if localized_content:
            canonical_content = (
                localized_content.get("ko")
                or next(iter(localized_content.values()))
            )
            generated_data = dict(canonical_content)
        else:
            # 기존 호출자와 테스트 payload는 한국어 원본으로 호환합니다.
            localized_content = {
                "ko": {
                    "judgment_draft": generated_data.get(
                        "judgment_draft",
                        "",
                    ),
                    "evidence_items": generated_data.get(
                        "evidence_items",
                        [],
                    ),
                }
            }

        # 추가 소견은 AI가 아니라 참여 의료진이 직접 작성합니다.
        generated_data["additional_opinion"] = ""

        serializer = CaseAgreementSerializer(
            data=generated_data,
            context={"request": request},
        )
        if not serializer.is_valid():
            logger.error(
                "Invalid AI agreement payload: %s",
                serializer.errors,
            )
            return Response(
                {
                    "detail": (
                        "AI 합의안 초안을 생성하지 못했습니다."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # AI 호출 중 다른 요청이 합의안을 만들었는지 재확인합니다.
        with transaction.atomic():
            locked_room = (
                CaseChatRoom.objects
                .select_for_update()
                .get(id=chat_room.id)
            )

            if CaseAgreement.objects.filter(
                chat_room=locked_room,
            ).exists():
                raise ValidationError(
                    {
                        "detail": (
                            "이미 생성된 협진 합의안이 있습니다."
                        )
                    }
                )

            agreement = serializer.save(
                chat_room=locked_room,
                status=CaseAgreement.Status.AI_DRAFT,
                version=1,
                localized_content=localized_content,
            )

        return Response(
            CaseAgreementSerializer(
                agreement,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )
